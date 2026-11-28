import logging
from datetime import datetime
from database.connection import get_db
from permissions.rbac import Role, normalize_role, can_access_employee_record
from services.notification_service import NotificationService
from services.audit_service import AuditService
from utils.serializers import serialize_doc, serialize_docs
from utils.timezone import now_utc, get_local_date_str

logger = logging.getLogger(__name__)

SHIFT_DEFINITIONS = {
    "General": {"name": "General Shift", "timing": "09:30 - 18:30"},
    "Morning": {"name": "Morning Shift", "timing": "07:00 - 15:30"},
    "Evening": {"name": "Evening Shift", "timing": "14:30 - 23:00"},
    "Night": {"name": "Night Shift", "timing": "22:30 - 07:00"},
    "Weekly Off": {"name": "Weekly Off", "timing": "OFF"}
}


class RosterService:
    """
    Shift Rostering Service for AISamrat HRMS:
    Approved Workflow:
    Team Lead proposes/updates roster -> Manager approves & publishes -> Employees notified.
    """

    @classmethod
    def propose_roster(cls, tl_user: dict, data: dict) -> tuple[dict | None, str | None]:
        db = get_db()
        tl_id = tl_user.get("employee_id")
        tl_name = tl_user.get("full_name", tl_id)
        role = tl_user.get("role")

        if role not in (Role.TEAM_LEAD, Role.MANAGER, Role.HR, Role.HR_MANAGER, Role.ADMIN, "trainer", "organization"):
            return None, "Unauthorized: Only Team Leads, Managers, or HR can create shift rosters."

        team_id = (data.get("team_id") or tl_user.get("team_id") or "").strip()
        week_start = (data.get("week_start_date") or data.get("week_start") or data.get("start_date") or "").strip()
        week_end = (data.get("week_end_date") or data.get("week_end") or data.get("end_date") or "").strip()
        shifts = data.get("shifts") or []

        if not week_start or not week_end:
            return None, "Week start date and end date are required."

        if not shifts or not isinstance(shifts, list):
            return None, "A list of shift schedule assignments is required."

        try:
            ws = datetime.strptime(week_start, "%Y-%m-%d").date()
            we = datetime.strptime(week_end, "%Y-%m-%d").date()
            if we < ws:
                return None, "Week end date cannot be earlier than start date."
            month = ws.month
            year = ws.year
        except ValueError:
            return None, "Invalid date format. Use YYYY-MM-DD."

        count = db.team_rosters.count_documents({})
        roster_id = f"ROST-{1001 + count}"

        doc = {
            "roster_id": roster_id,
            "team_id": team_id,
            "team_name": data.get("team_name") or f"Team {team_id}",
            "week_start_date": week_start,
            "week_end_date": week_end,
            "month": month,
            "year": year,
            "shifts": shifts,
            "status": "PROPOSED",
            "proposed_by_id": tl_id,
            "proposed_by_name": tl_name,
            "proposed_at": now_utc(),
            "reviewed_by_id": None,
            "reviewed_by_name": None,
            "review_remarks": None,
            "reviewed_at": None,
            "created_at": now_utc(),
            "updated_at": now_utc()
        }

        db.team_rosters.insert_one(doc)
        logger.info("Proposed roster %s for team %s by %s", roster_id, team_id, tl_id)

        # Notify Manager
        mgr = db.users.find_one({"role": Role.MANAGER, "is_active": True})
        if mgr:
            try:
                NotificationService.create_notification(
                    title=f"Shift Roster Proposed: {team_id}",
                    message=f"Team Lead {tl_name} proposed shift roster ({roster_id}) for {week_start} to {week_end} awaiting your review and publication.",
                    category="ROSTER",
                    recipient_id=mgr["employee_id"],
                    link=f"/roster?roster_id={roster_id}"
                )
            except Exception as e:
                logger.warning("Failed to notify manager for proposed roster: %s", e)

        # Audit
        try:
            AuditService.log_action(
                actor=tl_user,
                action="PROPOSE_ROSTER",
                target_type="team_roster",
                target_id=roster_id,
                details={"team_id": team_id, "week_start": week_start, "week_end": week_end, "total_shifts": len(shifts)}
            )
        except Exception as e:
            logger.warning("Failed to log roster audit: %s", e)

        return serialize_doc(doc), None

    @classmethod
    def review_roster(cls, reviewer: dict, roster_id: str, decision: str, remarks: str = "") -> tuple[dict | None, str | None]:
        decision = decision.capitalize()
        if decision not in ("Approved", "Rejected"):
            return None, "Invalid decision. Must be 'Approved' or 'Rejected'."

        clean_remarks = (remarks or "").strip()
        if decision == "Rejected" and not clean_remarks:
            return None, "A rejection reason is required."

        db = get_db()
        roster = db.team_rosters.find_one({"roster_id": roster_id})
        if not roster:
            return None, f"Roster '{roster_id}' not found."

        role = reviewer.get("role")
        reviewer_id = reviewer.get("employee_id")
        reviewer_name = reviewer.get("full_name", reviewer_id)

        if role not in (Role.MANAGER, Role.HR, Role.HR_MANAGER, Role.ADMIN, "organization"):
            return None, "Unauthorized: Only Managers, HR, and Administrators can review and publish shift rosters."

        if roster.get("status") not in ("PROPOSED", "Pending"):
            return None, f"Roster is in '{roster.get('status')}' status and cannot be reviewed."

        next_status = "PUBLISHED" if decision == "Approved" else "REJECTED"
        update_fields = {
            "status": next_status,
            "reviewed_by_id": reviewer_id,
            "reviewed_by_name": reviewer_name,
            "review_remarks": clean_remarks,
            "reviewed_at": now_utc(),
            "updated_at": now_utc()
        }

        db.team_rosters.update_one({"roster_id": roster_id}, {"$set": update_fields})

        # 1. Notify Proposer (Team Lead)
        try:
            NotificationService.create_notification(
                title=f"Shift Roster {decision}",
                message=f"Roster ({roster_id}) for {roster.get('week_start_date')} to {roster.get('week_end_date')} has been {decision.lower()} by Manager {reviewer_name}. Remarks: {clean_remarks}",
                category="ROSTER",
                recipient_id=roster.get("proposed_by_id"),
                link=f"/roster?roster_id={roster_id}"
            )
        except Exception as e:
            logger.warning("Failed to notify proposer: %s", e)

        # 2. If Published, notify all scheduled team members
        if decision == "Approved":
            notified_emps = set()
            for s in roster.get("shifts", []):
                emp_id = s.get("employee_id")
                if emp_id and emp_id not in notified_emps:
                    notified_emps.add(emp_id)
                    try:
                        NotificationService.create_notification(
                            title="New Shift Roster Published",
                            message=f"Your shift roster ({roster_id}) for {roster.get('week_start_date')} to {roster.get('week_end_date')} has been published by Manager {reviewer_name}.",
                            category="ROSTER",
                            recipient_id=emp_id,
                            link=f"/roster?roster_id={roster_id}"
                        )
                    except Exception as ex:
                        logger.warning("Failed to notify scheduled employee %s: %s", emp_id, ex)

        # Audit
        try:
            AuditService.log_action(
                actor=reviewer,
                action=f"MANAGER_ROSTER_{decision.upper()}",
                target_type="team_roster",
                target_id=roster_id,
                details={"decision": decision, "remarks": clean_remarks}
            )
        except Exception as e:
            logger.warning("Failed to log roster review audit: %s", e)

        updated = db.team_rosters.find_one({"roster_id": roster_id})
        return serialize_doc(updated), None

    @classmethod
    def get_pending_rosters_for_manager(cls, manager: dict) -> list[dict]:
        db = get_db()
        rosters = list(db.team_rosters.find({"status": "PROPOSED"}).sort("created_at", -1))
        return serialize_docs(rosters)

    @classmethod
    def get_team_rosters(cls, team_id: str = None) -> list[dict]:
        db = get_db()
        query = {}
        if team_id:
            query["team_id"] = team_id
        rosters = list(db.team_rosters.find(query).sort("created_at", -1))
        return serialize_docs(rosters)

    @classmethod
    def get_employee_schedule(cls, employee_id: str, start_date: str = None, end_date: str = None) -> list[dict]:
        db = get_db()
        # Find published rosters that contain this employee's schedule
        rosters = list(db.team_rosters.find({"status": "PUBLISHED"}).sort("week_start_date", -1))
        matching_shifts = []
        for r in rosters:
            for s in r.get("shifts", []):
                if s.get("employee_id") == employee_id:
                    shift_date = s.get("date")
                    if start_date and shift_date < start_date:
                        continue
                    if end_date and shift_date > end_date:
                        continue
                    shift_item = dict(s)
                    shift_item["roster_id"] = r.get("roster_id")
                    shift_item["week_start_date"] = r.get("week_start_date")
                    shift_item["week_end_date"] = r.get("week_end_date")
                    matching_shifts.append(shift_item)
        matching_shifts.sort(key=lambda x: x.get("date", ""))
        return matching_shifts

    @classmethod
    def update_roster(cls, actor: dict, roster_id: str, data: dict) -> tuple[dict | None, str | None]:
        role = actor.get("role")
        if role not in (Role.TEAM_LEAD, Role.MANAGER, Role.HR, Role.HR_MANAGER, Role.ADMIN, "organization"):
            return None, "Unauthorized: Only Team Leads, Managers, or HR can modify shift rosters."

        db = get_db()
        roster = db.team_rosters.find_one({"roster_id": roster_id})
        if not roster:
            return None, f"Roster '{roster_id}' not found."

        update_fields = {"updated_at": now_utc()}
        if "shifts" in data and isinstance(data["shifts"], list):
            update_fields["shifts"] = data["shifts"]
        if "team_name" in data:
            update_fields["team_name"] = data["team_name"]
        if "week_start_date" in data:
            update_fields["week_start_date"] = data["week_start_date"]
        if "week_end_date" in data:
            update_fields["week_end_date"] = data["week_end_date"]

        db.team_rosters.update_one({"roster_id": roster_id}, {"$set": update_fields})
        updated = db.team_rosters.find_one({"roster_id": roster_id})
        return serialize_doc(updated), None

    @classmethod
    def delete_roster(cls, actor: dict, roster_id: str) -> tuple[bool, str | None]:
        role = actor.get("role")
        if role not in (Role.MANAGER, Role.HR, Role.HR_MANAGER, Role.ADMIN, "organization"):
            return False, "Unauthorized: Only Managers or HR can delete shift rosters."

        db = get_db()
        res = db.team_rosters.delete_one({"roster_id": roster_id})
        if res.deleted_count == 0:
            return False, f"Roster '{roster_id}' not found."
        return True, None

    # =========================================================================
    # MULTIPLE SHIFT ROSTERS & EMPLOYEE SHIFT ALLOCATION (ORGANIZATION SETTINGS)
    # =========================================================================

    @classmethod
    def ensure_default_shifts(cls):
        db = get_db()
        defaults = [
            {
                "shift_id": "SHIFT-GEN",
                "name": "General Corporate Shift",
                "code": "GEN",
                "start_time": "09:30",
                "end_time": "18:30",
                "cutoff_time": "19:30",
                "grace_minutes": 15,
                "work_days": "Mon - Fri",
                "color": "primary",
                "description": "Standard enterprise core hours and corporate operations."
            },
            {
                "shift_id": "SHIFT-MORN",
                "name": "Early Morning Shift",
                "code": "MORN",
                "start_time": "07:00",
                "end_time": "15:30",
                "cutoff_time": "16:30",
                "grace_minutes": 10,
                "work_days": "Mon - Fri",
                "color": "info",
                "description": "Early morning client deliverables, sprint support and infrastructure readiness."
            },
            {
                "shift_id": "SHIFT-EVE",
                "name": "Afternoon / Evening Shift",
                "code": "EVE",
                "start_time": "14:30",
                "end_time": "23:00",
                "cutoff_time": "00:00",
                "grace_minutes": 15,
                "work_days": "Mon - Fri",
                "color": "warning",
                "description": "EMEA timezone operations, secondary sprint coverage and delivery handovers."
            },
            {
                "shift_id": "SHIFT-NIGHT",
                "name": "Global Night Shift",
                "code": "NIGHT",
                "start_time": "22:30",
                "end_time": "07:00",
                "cutoff_time": "08:00",
                "grace_minutes": 15,
                "work_days": "Mon - Fri",
                "color": "purple",
                "description": "US timezone client support, overnight builds, and 24/7 telemetry monitoring."
            }
        ]
        for s in defaults:
            if not db.shift_profiles.find_one({"shift_id": s["shift_id"]}):
                doc = dict(s)
                doc["created_at"] = now_utc()
                doc["updated_at"] = now_utc()
                db.shift_profiles.insert_one(doc)

    @classmethod
    def get_shift_profiles(cls, actor: dict = None) -> list[dict]:
        db = get_db()
        cls.ensure_default_shifts()
        shifts = list(db.shift_profiles.find({}).sort("created_at", 1))

        actor_role = normalize_role(actor.get("role")) if actor else None
        # Query all active employees and map to shifts (roster visibility scoped by role)
        users = list(db.users.find({"status": {"$ne": "offboarded"}}, {"employee_id": 1, "full_name": 1, "name": 1, "department": 1, "designation": 1, "shift_id": 1, "role": 1}))

        res = []
        for s in shifts:
            sid = s["shift_id"]
            if sid == "SHIFT-GEN":
                assigned = [u for u in users if u.get("shift_id") == sid or not u.get("shift_id")]
            else:
                assigned = [u for u in users if u.get("shift_id") == sid]

            s_copy = serialize_doc(s)
            if actor_role == Role.EMPLOYEE:
                s_copy["assigned_count"] = None
                s_copy["assigned_employees"] = []
            elif actor_role in (Role.TL, Role.MANAGER):
                scoped = [u for u in assigned if can_access_employee_record(actor, u.get("employee_id"))]
                s_copy["assigned_count"] = len(scoped)
                s_copy["assigned_employees"] = [
                    {
                        "employee_id": u.get("employee_id"),
                        "name": u.get("full_name") or u.get("name") or u.get("employee_id"),
                        "department": u.get("department", "General"),
                        "designation": u.get("designation", "Staff"),
                        "role": u.get("role", "employee")
                    }
                    for u in scoped[:30]
                ]
            else:
                s_copy["assigned_count"] = len(assigned)
                s_copy["assigned_employees"] = [
                    {
                        "employee_id": u.get("employee_id"),
                        "name": u.get("full_name") or u.get("name") or u.get("employee_id"),
                        "department": u.get("department", "General"),
                        "designation": u.get("designation", "Staff"),
                        "role": u.get("role", "employee")
                    }
                    for u in assigned[:30]
                ]
            res.append(s_copy)
        return res

    @classmethod
    def save_shift_profile(cls, actor: dict, data: dict) -> tuple[dict | None, str | None]:
        role = normalize_role(actor.get("role"))
        if role not in (Role.HR, Role.ADMIN):
            return None, "Unauthorized: Only HR or Administrators can configure shift rosters."

        db = get_db()
        cls.ensure_default_shifts()

        name = (data.get("name") or "").strip()
        start_time = (data.get("start_time") or "").strip()
        end_time = (data.get("end_time") or "").strip()
        if not name or not start_time or not end_time:
            return None, "Shift name, start time, and end time are required."

        shift_id = (data.get("shift_id") or "").strip()
        code = (data.get("code") or name[:4].upper()).strip()
        cutoff_time = (data.get("cutoff_time") or "").strip()
        if not cutoff_time:
            try:
                eh, em = map(int, end_time.split(":"))
                cutoff_time = f"{(eh + 1) % 24:02d}:{em:02d}"
            except Exception:
                cutoff_time = "20:00"

        grace_minutes = int(data.get("grace_minutes") or 15)
        work_days = (data.get("work_days") or "Mon - Fri").strip()
        color = (data.get("color") or "primary").strip()
        description = (data.get("description") or "").strip()

        if shift_id and db.shift_profiles.find_one({"shift_id": shift_id}):
            update_data = {
                "name": name,
                "code": code,
                "start_time": start_time,
                "end_time": end_time,
                "cutoff_time": cutoff_time,
                "grace_minutes": grace_minutes,
                "work_days": work_days,
                "color": color,
                "description": description,
                "updated_at": now_utc()
            }
            db.shift_profiles.update_one({"shift_id": shift_id}, {"$set": update_data})
            action = "UPDATE_SHIFT_PROFILE"
        else:
            if not shift_id:
                count = db.shift_profiles.count_documents({})
                shift_id = f"SHIFT-{code.upper()}"
                if db.shift_profiles.find_one({"shift_id": shift_id}):
                    shift_id = f"SHIFT-{code.upper()}-{count + 1}"

            new_doc = {
                "shift_id": shift_id,
                "name": name,
                "code": code,
                "start_time": start_time,
                "end_time": end_time,
                "cutoff_time": cutoff_time,
                "grace_minutes": grace_minutes,
                "work_days": work_days,
                "color": color,
                "description": description,
                "created_at": now_utc(),
                "updated_at": now_utc()
            }
            db.shift_profiles.insert_one(new_doc)
            action = "CREATE_SHIFT_PROFILE"

        try:
            AuditService.log_action(
                actor=actor,
                action=action,
                target_type="shift_profile",
                target_id=shift_id,
                details={"name": name, "start": start_time, "end": end_time}
            )
        except Exception:
            pass

        saved = db.shift_profiles.find_one({"shift_id": shift_id})
        return serialize_doc(saved), None

    @classmethod
    def delete_shift_profile(cls, actor: dict, shift_id: str) -> tuple[bool, str | None]:
        role = normalize_role(actor.get("role"))
        if role not in (Role.HR, Role.ADMIN):
            return False, "Unauthorized: Only HR or Administrators can delete shift profiles."

        if shift_id in ("SHIFT-GEN", "SHIFT-MORN", "SHIFT-EVE", "SHIFT-NIGHT"):
            return False, "Standard system shift templates cannot be deleted."

        db = get_db()
        res = db.shift_profiles.delete_one({"shift_id": shift_id})
        if res.deleted_count == 0:
            return False, f"Shift profile '{shift_id}' not found."

        # Reassign any users with this shift back to General
        db.users.update_many(
            {"shift_id": shift_id},
            {"$set": {"shift_id": "SHIFT-GEN", "shift_name": "General Corporate Shift"}}
        )
        return True, None

    @classmethod
    def assign_employees_to_shift(cls, actor: dict, shift_id: str, employee_ids: list = None, department: str = None) -> tuple[dict | None, str | None]:
        role = normalize_role(actor.get("role"))
        if role not in (Role.HR, Role.ADMIN, Role.MANAGER):
            return None, "Unauthorized: Only HR, Managers, or Administrators can assign shifts."

        if role == Role.MANAGER and department:
            actor_dept = actor.get("department")
            if not actor_dept or actor_dept in ("Management", "Executive", "Executive HR") or actor_dept != department:
                return None, "Access Denied: Managers can only assign shifts within their own department."

        db = get_db()
        cls.ensure_default_shifts()
        shift = db.shift_profiles.find_one({"shift_id": shift_id})
        if not shift:
            return None, f"Shift profile '{shift_id}' not found."

        query = {}
        if employee_ids and len(employee_ids) > 0:
            query["employee_id"] = {"$in": employee_ids}
        elif department:
            query["department"] = department
        else:
            return None, "Please select at least one employee or a department."

        users = list(db.users.find(query, {"employee_id": 1, "full_name": 1, "name": 1}))
        if not users:
            return None, "No matching active employees found for shift assignment."

        matched_ids = [u["employee_id"] for u in users]
        if role == Role.MANAGER:
            if not all(can_access_employee_record(actor, eid) for eid in matched_ids):
                return None, "Access Denied: You can only assign shifts to employees within your reporting scope."
        db.users.update_many(
            {"employee_id": {"$in": matched_ids}},
            {"$set": {"shift_id": shift_id, "shift_name": shift["name"]}}
        )

        # Notify employees
        for emp_id in matched_ids:
            try:
                NotificationService.create_notification(
                    title="Shift Schedule Updated",
                    message=f"You have been assigned to {shift['name']} ({shift['start_time']} – {shift['end_time']}).",
                    category="ROSTER",
                    recipient_id=emp_id,
                    link="/attendance"
                )
            except Exception:
                pass

        try:
            AuditService.log_action(
                actor=actor,
                action="ASSIGN_SHIFT",
                target_type="shift_profile",
                target_id=shift_id,
                details={"assigned_count": len(matched_ids), "shift_name": shift["name"], "target_employees": matched_ids[:10]}
            )
        except Exception:
            pass

        return {"success": True, "shift_id": shift_id, "shift_name": shift["name"], "assigned_count": len(matched_ids)}, None
