import uuid
import logging
from datetime import datetime, timezone
from typing import Optional, Tuple, List, Dict
from backend.database.connection import get_db
from backend.permissions.rbac import Role, normalize_role, can_access_employee_record
from backend.services.audit_service import AuditService
from backend.services.notification_service import NotificationService
from backend.services.external_notification_service import ExternalNotificationService
from backend.utils.serializers import serialize_doc, serialize_docs

logger = logging.getLogger(__name__)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


class AttendanceCorrectionService:
    VALID_CORRECTION_TYPES = [
        "MISSED_PUNCH_IN",
        "MISSED_PUNCH_OUT",
        "LATE_REGULARIZATION",
        "ON_DUTY",
        "STATUS_DISPUTE"
    ]

    @classmethod
    def request_correction(
        cls,
        employee_user: dict,
        target_date: str,
        correction_type: str,
        requested_in_time: str = None,
        requested_out_time: str = None,
        reason: str = None,
        requested_status: str = "PRESENT",
        deficit_hours: float = None
    ) -> Tuple[Optional[dict], Optional[str]]:
        """
        Employee submits an attendance regularization/correction request.
        Workflow: Employee -> Manager Approves/Rejects -> HR Intimated.
        Team Lead is NOT a mandatory approval step.
        """
        if not employee_user:
            return None, "Authentication required."

        employee_id = employee_user.get("employee_id")
        if not employee_id:
            return None, "Invalid employee identifier."

        if not target_date or not target_date.strip():
            return None, "Target date is required."

        if not reason or not reason.strip():
            return None, "A valid reason must be provided for attendance regularizations."

        corr_type = (correction_type or "MISSED_PUNCH_IN").upper().strip()
        if corr_type not in cls.VALID_CORRECTION_TYPES:
            corr_type = "MISSED_PUNCH_IN"

        req_status = (requested_status or "PRESENT").upper().strip()
        if req_status not in ("PRESENT", "ABSENT"):
            req_status = "PRESENT"

        db = get_db()

        # Check for duplicate pending request for same date
        existing_pending = db.attendance_corrections.find_one({
            "employee_id": employee_id,
            "target_date": target_date.strip(),
            "status": {"$in": ["PENDING_MANAGER", "PENDING_TEAM_LEAD", "PENDING_TEAM_LEAD_REVIEW"]}
        })
        if existing_pending:
            return None, f"An attendance correction request is already pending for date {target_date}."

        # Calculate or determine attendance shortage deficit
        if deficit_hours is None:
            deficit_hours = 0.5
            daily = db.attendance_daily.find_one({"employee_id": employee_id, "attendance_date": target_date.strip()})
            if daily:
                active_sec = daily.get("active_seconds") or daily.get("official_working_duration_seconds") or 0
                if active_sec > 0 and active_sec < 28800:
                    deficit_hours = round((28800 - active_sec) / 3600.0, 2)
                elif active_sec == 0:
                    deficit_hours = 8.0

        user_role = employee_user.get("role", Role.EMPLOYEE)
        team_lead_id = employee_user.get("team_lead_id") or employee_user.get("assigned_tl_id")
        manager_id = employee_user.get("reporting_manager_id") or employee_user.get("manager_id")

        if not team_lead_id and user_role == Role.EMPLOYEE:
            team_id = employee_user.get("team_id")
            if team_id:
                team_doc = db.teams.find_one({"team_id": team_id})
                if team_doc and (team_doc.get("lead_employee_id") or team_doc.get("lead_id")):
                    team_lead_id = team_doc.get("lead_employee_id") or team_doc.get("lead_id")
            if not team_lead_id:
                dept = employee_user.get("department")
                tl = db.users.find_one({"department": dept, "role": {"$in": [Role.TEAM_LEAD, "tl"]}, "is_active": True})
                if tl:
                    team_lead_id = tl.get("emp_id") or tl.get("employee_id")

        # Multi-Tier Routing:
        # Minor Shortage (Deficit <= 1.0h): Direct Team Lead Approval Authority. Manager & HR notified on approval.
        # Major Shortage (Deficit > 1.0h): TL reviews & endorses -> Manager gives final sign-off -> HR audit trail.
        if user_role in (Role.MANAGER, Role.ADMIN, Role.TEAM_LEAD, "tl") or not team_lead_id:
            shortage_tier = "MINOR" if deficit_hours <= 1.0 else "MAJOR"
            initial_status = "PENDING_MANAGER"
            target_approver = manager_id or "MANAGER"
        elif deficit_hours <= 1.0:
            shortage_tier = "MINOR"
            initial_status = "PENDING_TEAM_LEAD"
            target_approver = team_lead_id
        else:
            shortage_tier = "MAJOR"
            initial_status = "PENDING_TEAM_LEAD_REVIEW"
            target_approver = team_lead_id

        # Automatically determine fallback assigned Manager
        if not manager_id:
            dept = employee_user.get("department")
            if dept:
                mgr = db.users.find_one({"department": dept, "role": Role.MANAGER, "is_active": True})
                if mgr:
                    manager_id = mgr.get("emp_id") or mgr.get("employee_id")
        if not manager_id:
            any_mgr = db.users.find_one({"role": Role.MANAGER, "is_active": True})
            manager_id = (any_mgr.get("emp_id") or any_mgr.get("employee_id")) if any_mgr else "ADMIN-1001"

        request_id = f"AC-{uuid.uuid4().hex[:8].upper()}"
        doc = {
            "request_id": request_id,
            "employee_id": employee_id,
            "employee_name": employee_user.get("full_name", ""),
            "department": employee_user.get("department", ""),
            "team_id": employee_user.get("team_id", ""),
            "target_date": target_date.strip(),
            "correction_type": corr_type,
            "requested_status": req_status,
            "requested_in_time": (requested_in_time or "10:00").strip(),
            "requested_out_time": (requested_out_time or "18:00").strip(),
            "deficit_hours": deficit_hours,
            "shortage_tier": shortage_tier,
            "reason": reason.strip(),
            "status": initial_status,
            "assigned_tl_id": team_lead_id,
            "assigned_manager_id": manager_id,
            "tl_endorsed": False,
            "tl_remarks": None,
            "reviewed_by_id": None,
            "reviewed_by_name": None,
            "review_remarks": None,
            "reviewed_at": None,
            "hr_notified": False,
            "created_at": now_utc(),
            "updated_at": now_utc()
        }

        db.attendance_corrections.insert_one(doc)

        # Notify initial approver / reviewer
        tier_label = f"Minor Shortage (<=1h)" if shortage_tier == "MINOR" else f"Major Shortage ({deficit_hours}h)"
        NotificationService.create_notification(
            title=f"Pending Attendance Regularization ({tier_label})",
            message=f"{employee_user.get('full_name')} submitted a {tier_label} regularization for {target_date}.",
            category="ATTENDANCE",
            recipient_id=target_approver,
            link=f"/attendance?tab=corrections&id={request_id}"
        )

        AuditService.log_action(
            actor=employee_user,
            action="ATTENDANCE_CORRECTION_REQUEST",
            target_type="attendance_correction",
            target_id=request_id,
            details={"target_date": target_date, "correction_type": corr_type, "shortage_tier": shortage_tier, "deficit_hours": deficit_hours}
        )

        return doc, None

    @classmethod
    def review_correction(
        cls,
        reviewer_user: dict,
        request_id: str,
        decision: str,
        remarks: str = None
    ) -> Tuple[Optional[dict], Optional[str]]:
        """
        Multi-tier review of attendance regularization requests:
        - Minor Shortage (<= 1h): Team Lead directly approves; Manager & HR receive automatic notifications.
        - Major Shortage (> 1h): Team Lead reviews and endorses (advances to PENDING_MANAGER); Manager provides final sign-off with HR audit trail.
        """
        if not reviewer_user:
            return None, "Authentication required."

        role = normalize_role(reviewer_user.get("role"))
        if not request_id:
            return None, "Request identifier is required."

        dec = (decision or "").upper().strip()
        if dec not in ("APPROVED", "REJECTED", "ENDORSED"):
            return None, "Decision must be 'APPROVED', 'ENDORSED', or 'REJECTED'."

        db = get_db()
        req = db.attendance_corrections.find_one({"request_id": request_id})
        if not req:
            return None, f"Correction request '{request_id}' not found."

        current_status = req.get("status")
        if current_status not in ("PENDING_TEAM_LEAD", "PENDING_TEAM_LEAD_REVIEW", "PENDING_MANAGER"):
            return None, f"Request has already been reviewed (Current Status: {current_status})."

        reviewer_id = reviewer_user.get("employee_id") or reviewer_user.get("emp_id")
        if reviewer_id and req.get("employee_id") and str(reviewer_id).strip().upper() == str(req.get("employee_id")).strip().upper():
            return None, "Unauthorized: Employees cannot approve or review their own attendance correction requests."

        reviewer_name = reviewer_user.get("full_name") or reviewer_user.get("name") or reviewer_id
        current_time = now_utc()
        shortage_tier = req.get("shortage_tier", "MINOR")
        deficit_hours = req.get("deficit_hours", 0.5)

        # 0. HR / ADMIN DIRECT REVIEW & APPROVAL AUTHORITY
        if role in (Role.HR, Role.ADMIN):
            updates = {
                "status": dec,
                "reviewed_by_id": reviewer_id,
                "reviewed_by_name": reviewer_name,
                "review_remarks": remarks or f"{dec.title()} under HR / Admin governance authority",
                "reviewed_at": current_time,
                "updated_at": current_time,
                "hr_notified": True,
                "hr_notified_at": current_time
            }
            if dec == "APPROVED":
                cls._reconcile_attendance(db, req, reviewer_name, reviewer_id, remarks, current_time)
            db.attendance_corrections.update_one({"request_id": request_id}, {"$set": updates})

            NotificationService.create_notification(
                title=f"Attendance Regularization {dec.title()}",
                message=f"Your attendance regularization for {req.get('target_date')} was {dec.lower()} by HR/Admin {reviewer_name}.",
                category="ATTENDANCE",
                recipient_id=req["employee_id"],
                link=f"/attendance?date={req.get('target_date')}"
            )
            AuditService.log_action(
                actor=reviewer_user,
                action=f"ATTENDANCE_CORRECTION_HR_{dec}",
                target_type="attendance_correction",
                target_id=request_id,
                details={"target_date": req.get("target_date"), "decision": dec}
            )
            return db.attendance_corrections.find_one({"request_id": request_id}), None

        # 1. TEAM LEAD REVIEW STAGE
        if current_status in ("PENDING_TEAM_LEAD", "PENDING_TEAM_LEAD_REVIEW"):
            if role not in (Role.TL, Role.MANAGER, Role.ADMIN):
                return None, "Access Denied: Only Team Leads, Managers, or Administrators can review this request."
            if role == Role.TL:
                assigned_tl = req.get("assigned_tl_id")
                if assigned_tl and str(assigned_tl).strip().upper() != str(reviewer_id or "").strip().upper():
                    return None, "Access Denied: This attendance correction is assigned to another Team Lead."
                if not can_access_employee_record(reviewer_user, req.get("employee_id")):
                    return None, "Access Denied: You can only review attendance corrections within your assigned team."
            elif role == Role.MANAGER and not can_access_employee_record(reviewer_user, req.get("employee_id")):
                return None, "Access Denied: You can only review attendance corrections within your reporting scope."

            if dec == "REJECTED":
                updates = {
                    "status": "REJECTED",
                    "reviewed_by_id": reviewer_id,
                    "reviewed_by_name": reviewer_name,
                    "review_remarks": remarks or "Rejected by Team Lead",
                    "reviewed_at": current_time,
                    "updated_at": current_time
                }
                db.attendance_corrections.update_one({"request_id": request_id}, {"$set": updates})
                NotificationService.create_notification(
                    title="Attendance Regularization Rejected",
                    message=f"Your attendance regularization for {req.get('target_date')} was rejected by TL {reviewer_name}.",
                    category="ATTENDANCE",
                    recipient_id=req["employee_id"],
                    link="/attendance?tab=corrections"
                )
                return db.attendance_corrections.find_one({"request_id": request_id}), None

            # Minor shortage (<= 1h): Team Lead has Direct Approval Authority!
            if shortage_tier == "MINOR" and current_status == "PENDING_TEAM_LEAD":
                updates = {
                    "status": "APPROVED",
                    "reviewed_by_id": reviewer_id,
                    "reviewed_by_name": reviewer_name,
                    "review_remarks": remarks or "Approved under TL minor shortage authority (<= 1h deficit)",
                    "reviewed_at": current_time,
                    "hr_notified": True,
                    "hr_notified_at": current_time,
                    "updated_at": current_time
                }
                # Reconcile attendance
                cls._reconcile_attendance(db, req, reviewer_name, reviewer_id, remarks, current_time)
                db.attendance_corrections.update_one({"request_id": request_id}, {"$set": updates})

                # Notify employee
                NotificationService.create_notification(
                    title="Minor Shortage Regularization Approved",
                    message=f"Your minor attendance regularization ({deficit_hours}h) for {req.get('target_date')} was approved by TL {reviewer_name}.",
                    category="ATTENDANCE",
                    recipient_id=req["employee_id"],
                    link=f"/attendance?date={req.get('target_date')}"
                )

                # Simultaneously notify Manager & HR
                mgr_id = req.get("assigned_manager_id")
                if mgr_id:
                    NotificationService.create_notification(
                        title="Minor Shortage Approved by TL",
                        message=f"TL {reviewer_name} approved minor shortage regularization ({deficit_hours}h) for {req.get('employee_name')} ({req.get('employee_id')}) on {req.get('target_date')}.",
                        category="ATTENDANCE_FYI",
                        recipient_id=mgr_id,
                        link=f"/attendance?tab=corrections&id={request_id}"
                    )
                for hr in db.users.find({"role": Role.HR, "is_active": True}, {"employee_id": 1}):
                    NotificationService.create_notification(
                        title="Minor Shortage Regularization Approved",
                        message=f"TL {reviewer_name} approved minor shortage ({deficit_hours}h) for {req.get('employee_name')} on {req.get('target_date')}.",
                        category="ATTENDANCE_FYI",
                        recipient_id=hr["employee_id"],
                        link=f"/attendance?tab=hr-monitor&date={req.get('target_date')}"
                    )

                AuditService.log_action(
                    actor=reviewer_user,
                    action="ATTENDANCE_CORRECTION_TL_APPROVED",
                    target_type="attendance_correction",
                    target_id=request_id,
                    details={"target_date": req.get("target_date"), "deficit_hours": deficit_hours, "shortage_tier": "MINOR"}
                )
                return db.attendance_corrections.find_one({"request_id": request_id}), None

            # Major shortage (> 1h): TL Endorses and routes to Manager!
            updates = {
                "status": "PENDING_MANAGER",
                "tl_endorsed": True,
                "tl_endorsed_by_id": reviewer_id,
                "tl_endorsed_by_name": reviewer_name,
                "tl_endorsed_at": current_time,
                "tl_remarks": remarks or "Endorsed by Team Lead; routed for Manager sign-off",
                "updated_at": current_time
            }
            db.attendance_corrections.update_one({"request_id": request_id}, {"$set": updates})

            # Notify Manager for final sign-off
            mgr_id = req.get("assigned_manager_id") or "MANAGER"
            NotificationService.create_notification(
                title=f"Major Shortage Endorsement ({deficit_hours}h)",
                message=f"TL {reviewer_name} endorsed major shortage for {req.get('employee_name')}. Requires your final manager sign-off.",
                category="ATTENDANCE",
                recipient_id=mgr_id,
                link=f"/attendance?tab=corrections&id={request_id}"
            )
            return db.attendance_corrections.find_one({"request_id": request_id}), None

        # 2. MANAGER FINAL REVIEW STAGE
        if role not in (Role.MANAGER, Role.ADMIN):
            return None, "Access Denied: Only authorized Managers or Administrators can give final sign-off on attendance regularizations."
        if role == Role.MANAGER and not can_access_employee_record(reviewer_user, req.get("employee_id")):
            return None, "Access Denied: You can only approve attendance corrections within your reporting scope."

        updates = {
            "status": dec,
            "reviewed_by_id": reviewer_id,
            "reviewed_by_name": reviewer_name,
            "review_remarks": remarks or ("Approved by Manager" if dec == "APPROVED" else "Rejected by Manager"),
            "reviewed_at": current_time,
            "updated_at": current_time
        }

        if dec == "APPROVED":
            updates["hr_notified"] = True
            updates["hr_notified_at"] = current_time
            cls._reconcile_attendance(db, req, reviewer_name, reviewer_id, remarks, current_time)
            db.attendance_corrections.update_one({"request_id": request_id}, {"$set": updates})

            # Notify Employee
            NotificationService.create_notification(
                title="Attendance Regularization Approved",
                message=f"Your attendance regularization for {req.get('target_date')} was granted final approval by Manager {reviewer_name}.",
                category="ATTENDANCE",
                recipient_id=req["employee_id"],
                link=f"/attendance?date={req.get('target_date')}"
            )

            # Auditable trail to HR
            for hr in db.users.find({"role": Role.HR, "is_active": True}, {"employee_id": 1}):
                NotificationService.create_notification(
                    title="Major Attendance Shortage Sign-Off",
                    message=f"Manager {reviewer_name} approved major attendance shortage for {req.get('employee_name')} on {req.get('target_date')}. Auditable record generated.",
                    category="ATTENDANCE_AUDIT",
                    recipient_id=hr["employee_id"],
                    link=f"/attendance?tab=hr-monitor&date={req.get('target_date')}"
                )
        else:
            db.attendance_corrections.update_one({"request_id": request_id}, {"$set": updates})
            NotificationService.create_notification(
                title="Attendance Regularization Rejected",
                message=f"Your attendance regularization for {req.get('target_date')} was rejected by Manager {reviewer_name}.",
                category="ATTENDANCE",
                recipient_id=req["employee_id"],
                link="/attendance?tab=corrections"
            )

        AuditService.log_action(
            actor=reviewer_user,
            action=f"ATTENDANCE_CORRECTION_MGR_{dec}",
            target_type="attendance_correction",
            target_id=request_id,
            details={"decision": dec, "target_date": req.get("target_date"), "shortage_tier": shortage_tier, "remarks": remarks}
        )
        return db.attendance_corrections.find_one({"request_id": request_id}), None

    @classmethod
    def _reconcile_attendance(cls, db, req: dict, reviewer_name: str, reviewer_id: str, remarks: str, current_time: datetime):
        """Helper to reconcile daily attendance record upon regularization approval."""
        target_date = req["target_date"]
        emp_id = req["employee_id"]
        req_status = (req.get("requested_status") or "PRESENT").upper().strip()
        user_doc = db.users.find_one({"employee_id": emp_id})
        emp_dept = user_doc.get("department", "") if user_doc else req.get("department", "")
        emp_role = user_doc.get("role", Role.EMPLOYEE) if user_doc else Role.EMPLOYEE
        correction_note = f"Dispute regularized by {reviewer_name} ({reviewer_id}): {remarks or req.get('reason')}"

        if req_status == "ABSENT":
            daily_updates = {
                "employee_id": emp_id,
                "employee_name": req.get("employee_name", ""),
                "department": emp_dept,
                "user_role": emp_role,
                "attendance_date": target_date,
                "status": "ABSENT",
                "late_arrival_status": "N/A",
                "delay_minutes": 0,
                "is_manually_corrected": True,
                "correction_reason": correction_note,
                "clock_out_state": "Disputed Absent",
                "updated_at": current_time
            }
        else:
            daily_updates = {
                "employee_id": emp_id,
                "employee_name": req.get("employee_name", ""),
                "department": emp_dept,
                "user_role": emp_role,
                "attendance_date": target_date,
                "status": "PRESENT",
                "late_arrival_status": "ON_TIME",
                "delay_minutes": 0,
                "is_manually_corrected": True,
                "correction_reason": correction_note,
                "clock_out_state": "Regularized",
                "elapsed_seconds": 28800,
                "elapsed_display": "08h 00m",
                "active_working_seconds": 28800,
                "active_working_display": "08h 00m",
                "official_working_duration_seconds": 28800,
                "official_working_duration_display": "08h 00m",
                "total_break_seconds": 0,
                "total_break_display": "00m 00s",
                "updated_at": current_time
            }

        db.attendance_daily.update_one(
            {"employee_id": emp_id, "attendance_date": target_date},
            {"$set": daily_updates, "$setOnInsert": {"created_at": current_time}},
            upsert=True
        )


    @classmethod
    def get_my_corrections(cls, employee_id: str) -> List[dict]:
        db = get_db()
        return list(db.attendance_corrections.find(
            {"employee_id": employee_id}
        ).sort("created_at", -1))

    @classmethod
    def get_pending_corrections_for_team_lead(cls, team_lead_id: str = None, department: str = None) -> List[dict]:
        """Fetches pending attendance corrections for Team Lead queue (Minor shortages for direct approval and Major shortages for endorsement)."""
        db = get_db()
        if not team_lead_id:
            return []
        statuses = ["PENDING_TEAM_LEAD", "PENDING_TEAM_LEAD_REVIEW"]
        clauses = [{"assigned_tl_id": team_lead_id}]
        teams_led = [t["team_id"] for t in db.teams.find({"$or": [{"lead_employee_id": team_lead_id}, {"lead_id": team_lead_id}]}, {"team_id": 1}) if t.get("team_id")]
        tl_user = db.users.find_one({"$or": [{"employee_id": team_lead_id}, {"emp_id": team_lead_id}]}, {"team_id": 1})
        if tl_user and tl_user.get("team_id"):
            teams_led.append(tl_user["team_id"])
        if teams_led:
            clauses.append({"team_id": {"$in": list(set(teams_led))}})
        query = {
            "status": {"$in": statuses},
            "$or": clauses
        }
        return list(db.attendance_corrections.find(query).sort("created_at", -1))

    @classmethod
    def get_pending_corrections_for_manager(cls, manager_id: str = None, department: str = None) -> List[dict]:
        db = get_db()
        statuses = ["PENDING_MANAGER"]
        clauses = []
        if manager_id:
            clauses.append({"assigned_manager_id": manager_id})
            # Subordinates reporting directly to this manager
            sub_docs = db.users.find({"$or": [{"manager_id": manager_id}, {"reporting_manager_id": manager_id}]}, {"employee_id": 1, "emp_id": 1})
            subordinates = []
            for u in sub_docs:
                sid = u.get("employee_id") or u.get("emp_id")
                if sid:
                    subordinates.append(sid)
            if subordinates:
                clauses.append({"employee_id": {"$in": subordinates}})
        if department and department not in ("Management", "Executive", "Executive HR"):
            clauses.append({"department": department})
        if not clauses:
            return []
        query = {
            "status": {"$in": statuses},
            "$or": clauses
        }
        return list(db.attendance_corrections.find(query).sort("created_at", -1))

    @classmethod
    def get_all_corrections_for_hr(cls, limit: int = 50) -> List[dict]:
        db = get_db()
        return list(db.attendance_corrections.find({}).sort("created_at", -1).limit(limit))

    @classmethod
    def get_all_pending_corrections_for_hr(cls) -> List[dict]:
        db = get_db()
        statuses = ["PENDING_TEAM_LEAD", "PENDING_TEAM_LEAD_REVIEW", "PENDING_MANAGER", "PENDING_HR"]
        return list(db.attendance_corrections.find({"status": {"$in": statuses}}).sort("created_at", -1))

    @classmethod
    def cancel_correction(cls, actor: dict, request_id: str) -> tuple[bool, str | None]:
        db = get_db()
        req = db.attendance_corrections.find_one({"request_id": request_id})
        if not req:
            return False, f"Attendance correction '{request_id}' not found."

        role = normalize_role(actor.get("role"))
        emp_id = (actor.get("employee_id") or actor.get("emp_id") or "").strip().upper()
        req_emp_id = (req.get("employee_id") or "").strip().upper()

        if req_emp_id != emp_id and role not in (Role.HR, Role.ADMIN):
            return False, "Access Denied: You cannot cancel another employee's correction request."

        if req.get("status") in ("APPROVED", "Approved") and role not in (Role.HR, Role.ADMIN):
            return False, "Approved attendance corrections cannot be cancelled by employees. Contact HR."

        db.attendance_corrections.delete_one({"request_id": request_id})
        return True, None
