import logging
from datetime import datetime, timedelta
from backend.database.connection import get_db
from backend.permissions.rbac import Role
from backend.services.notification_service import NotificationService
from backend.services.audit_service import AuditService
from backend.utils.serializers import serialize_doc, serialize_docs
from backend.utils.timezone import now_utc, get_local_date_str

logger = logging.getLogger(__name__)


class PIPService:
    """
    Performance Improvement Plan (PIP) & Probation Governance Service for AISamrat HRMS.
    Approved 5-Stage Governance Workflow:
    1. Team Lead initiates proposal
    2. Manager approves initiation
    3. HR notified & governs process (kicks off active plan)
    4. Employee acknowledges and participates
    5. Team Lead monitors & logs milestone check-ins
    6. Manager evaluates final outcome
    7. HR verifies process compliance & closes record
    """

    @classmethod
    def initiate_proposal(cls, initiator: dict, data: dict) -> tuple[dict | None, str | None]:
        db = get_db()
        emp_id = (data.get("employee_id") or "").strip().upper()
        reason = (data.get("reason") or "").strip()
        performance_gaps = (data.get("performance_gaps") or "").strip()
        target_objectives = data.get("target_objectives") or []
        duration_days = int(data.get("duration_days", 30))
        start_date = (data.get("start_date") or get_local_date_str()).strip()

        if not emp_id:
            return None, "Target employee ID is required."
        if not reason or not performance_gaps:
            return None, "Reason and identified performance gaps are required."

        target_emp = db.users.find_one({"employee_id": emp_id})
        if not target_emp:
            return None, f"Employee '{emp_id}' not found."

        role = initiator.get("role")
        init_id = initiator.get("employee_id")

        if role not in (Role.TEAM_LEAD, Role.MANAGER, Role.ADMIN, "trainer", "organization"):
            return None, "Unauthorized: Only Team Leads and Managers can initiate PIP proposals."

        if emp_id == init_id:
            return None, "Invalid action: You cannot initiate a PIP on yourself."

        # Calculate end date
        try:
            sd = datetime.strptime(start_date, "%Y-%m-%d").date()
            ed = sd + timedelta(days=duration_days)
            end_date = ed.strftime("%Y-%m-%d")
        except ValueError:
            return None, "Invalid date format. Use YYYY-MM-DD."

        count = db.pip_records.count_documents({})
        pip_id = f"PIP-{1001 + count}"

        doc = {
            "pip_id": pip_id,
            "employee_id": emp_id,
            "employee_name": target_emp.get("full_name", emp_id),
            "department": target_emp.get("department", "General"),
            "team_id": target_emp.get("team_id", ""),
            "initiated_by_id": init_id,
            "initiated_by_name": initiator.get("full_name", init_id),
            "initiated_by_role": role,
            "reason": reason,
            "performance_gaps": performance_gaps,
            "target_objectives": target_objectives,
            "duration_days": duration_days,
            "start_date": start_date,
            "end_date": end_date,
            "status": "PROPOSED",
            "manager_approval": None,
            "hr_governance": None,
            "employee_acknowledgement": None,
            "milestone_checkins": [],
            "final_evaluation": None,
            "hr_closure": None,
            "created_at": now_utc(),
            "updated_at": now_utc()
        }

        db.pip_records.insert_one(doc)
        logger.info("Created PIP proposal %s for %s by %s", pip_id, emp_id, init_id)

        # Notify Manager
        mgr = db.users.find_one({"role": Role.MANAGER, "is_active": True})
        if mgr:
            try:
                NotificationService.create_notification(
                    title=f"PIP Proposal: {target_emp.get('full_name')}",
                    message=f"Team Lead {initiator.get('full_name')} proposed PIP ({pip_id}) for {target_emp.get('full_name')} ({emp_id}) awaiting manager approval.",
                    category="PIP",
                    recipient_id=mgr["employee_id"],
                    link=f"/pip?pip_id={pip_id}"
                )
            except Exception as e:
                logger.warning("Failed to notify manager for PIP proposal: %s", e)

        # Audit
        try:
            AuditService.log_action(
                actor=initiator,
                action="PROPOSE_PIP",
                target_type="pip_record",
                target_id=pip_id,
                details={"employee_id": emp_id, "duration": duration_days}
            )
        except Exception as e:
            logger.warning("Failed to log PIP audit: %s", e)

        return serialize_doc(doc), None

    @classmethod
    def manager_review_proposal(cls, manager: dict, pip_id: str, decision: str, remarks: str = "") -> tuple[dict | None, str | None]:
        decision = decision.capitalize()
        if decision not in ("Approved", "Rejected"):
            return None, "Invalid decision. Must be 'Approved' or 'Rejected'."

        clean_remarks = (remarks or "").strip()
        db = get_db()
        pip = db.pip_records.find_one({"pip_id": pip_id})
        if not pip:
            return None, f"PIP record '{pip_id}' not found."

        role = manager.get("role")
        if role not in (Role.MANAGER, Role.ADMIN, "organization"):
            return None, "Unauthorized: Only Managers can review PIP initiation proposals."

        if pip.get("status") != "PROPOSED":
            return None, f"PIP is in '{pip.get('status')}' status and cannot be reviewed by Manager."

        next_status = "MANAGER_APPROVED" if decision == "Approved" else "REJECTED"
        update_fields = {
            "status": next_status,
            "manager_approval": {
                "decision": decision,
                "reviewed_by_id": manager.get("employee_id"),
                "reviewed_by_name": manager.get("full_name"),
                "remarks": clean_remarks,
                "timestamp": now_utc()
            },
            "updated_at": now_utc()
        }

        db.pip_records.update_one({"pip_id": pip_id}, {"$set": update_fields})

        # If approved, notify HR to govern and kick off official plan
        if decision == "Approved":
            hr_users = list(db.users.find({"role": Role.HR, "is_active": True}))
            for hr in hr_users:
                try:
                    NotificationService.create_notification(
                        title=f"PIP Approved for Kickoff: {pip.get('employee_name')}",
                        message=f"Manager {manager.get('full_name')} approved PIP proposal ({pip_id}) for {pip.get('employee_name')}. HR governance kickoff required.",
                        category="PIP",
                        recipient_id=hr["employee_id"],
                        link=f"/pip?pip_id={pip_id}"
                    )
                except Exception as e:
                    logger.warning("Failed to notify HR: %s", e)

        # Notify initiator (Team Lead)
        try:
            NotificationService.create_notification(
                title=f"PIP Proposal {decision}",
                message=f"Your PIP proposal ({pip_id}) for {pip.get('employee_name')} was {decision.lower()} by Manager {manager.get('full_name')}.",
                category="PIP",
                recipient_id=pip.get("initiated_by_id"),
                link=f"/pip?pip_id={pip_id}"
            )
        except Exception as e:
            logger.warning("Failed to notify initiator: %s", e)

        updated = db.pip_records.find_one({"pip_id": pip_id})
        return serialize_doc(updated), None

    @classmethod
    def hr_kickoff(cls, hr_user: dict, pip_id: str, guidelines: str = "") -> tuple[dict | None, str | None]:
        db = get_db()
        pip = db.pip_records.find_one({"pip_id": pip_id})
        if not pip:
            return None, f"PIP record '{pip_id}' not found."

        role = hr_user.get("role")
        if role not in (Role.HR, Role.ADMIN, "organization", "hr_manager"):
            return None, "Unauthorized: Only HR personnel can govern and kick off official PIPs."

        if pip.get("status") != "MANAGER_APPROVED":
            return None, f"PIP must be in 'MANAGER_APPROVED' status to be kicked off by HR (currently '{pip.get('status')}')."

        update_fields = {
            "status": "ACTIVE",
            "hr_governance": {
                "kickoff_by_id": hr_user.get("employee_id"),
                "kickoff_by_name": hr_user.get("full_name"),
                "guidelines": guidelines.strip() or "Standard HR PIP Governance Protocol applied.",
                "kicked_off_at": now_utc()
            },
            "updated_at": now_utc()
        }

        db.pip_records.update_one({"pip_id": pip_id}, {"$set": update_fields})

        # Notify Employee to participate & acknowledge
        try:
            NotificationService.create_notification(
                title="Performance Improvement Plan Initiated",
                message=f"Official Performance Improvement Plan ({pip_id}) has been activated. Please review your objectives and submit acknowledgement.",
                category="PIP",
                recipient_id=pip.get("employee_id"),
                link=f"/pip?pip_id={pip_id}"
            )
        except Exception as e:
            logger.warning("Failed to notify employee: %s", e)

        updated = db.pip_records.find_one({"pip_id": pip_id})
        return serialize_doc(updated), None

    @classmethod
    def employee_acknowledge(cls, employee: dict, pip_id: str, comments: str = "") -> tuple[dict | None, str | None]:
        db = get_db()
        pip = db.pip_records.find_one({"pip_id": pip_id})
        if not pip:
            return None, f"PIP record '{pip_id}' not found."

        if pip.get("employee_id") != employee.get("employee_id"):
            return None, "Unauthorized: You can only acknowledge your own PIP plan."

        if pip.get("status") != "ACTIVE":
            return None, f"PIP is not in 'ACTIVE' status (currently '{pip.get('status')}')."

        ack_data = {
            "acknowledged_at": now_utc(),
            "comments": (comments or "").strip() or "Acknowledged by employee."
        }

        db.pip_records.update_one(
            {"pip_id": pip_id},
            {"$set": {"employee_acknowledgement": ack_data, "updated_at": now_utc()}}
        )

        # Notify Team Lead and HR
        try:
            NotificationService.create_notification(
                title="PIP Acknowledged by Employee",
                message=f"{employee.get('full_name')} acknowledged PIP ({pip_id}) objectives.",
                category="PIP",
                recipient_id=pip.get("initiated_by_id"),
                link=f"/pip?pip_id={pip_id}"
            )
        except Exception as e:
            logger.warning("Failed to notify TL: %s", e)

        updated = db.pip_records.find_one({"pip_id": pip_id})
        return serialize_doc(updated), None

    @classmethod
    def log_checkin(cls, reviewer: dict, pip_id: str, notes: str, rating: str = "Satisfactory") -> tuple[dict | None, str | None]:
        db = get_db()
        pip = db.pip_records.find_one({"pip_id": pip_id})
        if not pip:
            return None, f"PIP record '{pip_id}' not found."

        role = reviewer.get("role")
        rev_id = reviewer.get("employee_id")

        if role not in (Role.TEAM_LEAD, Role.MANAGER, Role.ADMIN, "trainer", "organization"):
            return None, "Unauthorized: Only Team Leads or Managers can log milestone check-ins."

        if pip.get("status") != "ACTIVE":
            return None, f"Check-ins can only be logged on ACTIVE PIPs (currently '{pip.get('status')}')."

        clean_notes = (notes or "").strip()
        if not clean_notes:
            return None, "Milestone check-in notes are required."

        checkin_entry = {
            "checkin_id": f"CHK-{101 + len(pip.get('milestone_checkins', []))}",
            "logged_by_id": rev_id,
            "logged_by_name": reviewer.get("full_name", rev_id),
            "logged_by_role": role,
            "notes": clean_notes,
            "rating": rating,
            "timestamp": now_utc()
        }

        db.pip_records.update_one(
            {"pip_id": pip_id},
            {
                "$push": {"milestone_checkins": checkin_entry},
                "$set": {"updated_at": now_utc()}
            }
        )

        updated = db.pip_records.find_one({"pip_id": pip_id})
        return serialize_doc(updated), None

    @classmethod
    def manager_evaluate(cls, manager: dict, pip_id: str, outcome: str, evaluation_notes: str) -> tuple[dict | None, str | None]:
        outcome = outcome.upper()
        if outcome not in ("SUCCESSFUL", "EXTENDED", "FAILED"):
            return None, "Invalid outcome. Must be 'SUCCESSFUL', 'EXTENDED', or 'FAILED'."

        clean_notes = (evaluation_notes or "").strip()
        if not clean_notes:
            return None, "Evaluation notes and justification are required."

        db = get_db()
        pip = db.pip_records.find_one({"pip_id": pip_id})
        if not pip:
            return None, f"PIP record '{pip_id}' not found."

        role = manager.get("role")
        if role not in (Role.MANAGER, Role.ADMIN, "organization"):
            return None, "Unauthorized: Only Managers can evaluate final PIP outcomes."

        if pip.get("status") != "ACTIVE":
            return None, f"PIP must be ACTIVE to evaluate (currently '{pip.get('status')}')."

        eval_data = {
            "evaluated_by_id": manager.get("employee_id"),
            "evaluated_by_name": manager.get("full_name"),
            "outcome": outcome,
            "notes": clean_notes,
            "evaluated_at": now_utc()
        }

        db.pip_records.update_one(
            {"pip_id": pip_id},
            {
                "$set": {
                    "status": "EVALUATED",
                    "final_evaluation": eval_data,
                    "updated_at": now_utc()
                }
            }
        )

        # Notify HR for final compliance check and closure
        hr_users = list(db.users.find({"role": Role.HR, "is_active": True}))
        for hr in hr_users:
            try:
                NotificationService.create_notification(
                    title=f"PIP Evaluated: {pip.get('employee_name')} ({outcome})",
                    message=f"Manager {manager.get('full_name')} evaluated PIP ({pip_id}) outcome as {outcome}. Please verify compliance and close.",
                    category="PIP",
                    recipient_id=hr["employee_id"],
                    link=f"/pip?pip_id={pip_id}"
                )
            except Exception as e:
                logger.warning("Failed to notify HR: %s", e)

        updated = db.pip_records.find_one({"pip_id": pip_id})
        return serialize_doc(updated), None

    @classmethod
    def hr_verify_compliance_and_close(cls, hr_user: dict, pip_id: str, compliance_notes: str = "") -> tuple[dict | None, str | None]:
        db = get_db()
        pip = db.pip_records.find_one({"pip_id": pip_id})
        if not pip:
            return None, f"PIP record '{pip_id}' not found."

        role = hr_user.get("role")
        if role not in (Role.HR, Role.ADMIN, "organization", "hr_manager"):
            return None, "Unauthorized: Only HR personnel can verify compliance and close PIPs."

        if pip.get("status") != "EVALUATED":
            return None, f"PIP must be in 'EVALUATED' status to verify compliance (currently '{pip.get('status')}')."

        closure_data = {
            "closed_by_id": hr_user.get("employee_id"),
            "closed_by_name": hr_user.get("full_name"),
            "is_compliant": True,
            "compliance_notes": (compliance_notes or "").strip() or "Process fully compliant with company policy.",
            "closed_at": now_utc()
        }

        db.pip_records.update_one(
            {"pip_id": pip_id},
            {
                "$set": {
                    "status": "CLOSED_COMPLIANT",
                    "hr_closure": closure_data,
                    "updated_at": now_utc()
                }
            }
        )

        # Notify Employee of final closure
        outcome = pip.get("final_evaluation", {}).get("outcome", "COMPLETED")
        try:
            NotificationService.create_notification(
                title=f"PIP Concluded: {outcome}",
                message=f"Your Performance Improvement Plan ({pip_id}) has been formally concluded with outcome: {outcome}.",
                category="PIP",
                recipient_id=pip.get("employee_id"),
                link=f"/pip?pip_id={pip_id}"
            )
        except Exception as e:
            logger.warning("Failed to notify employee: %s", e)

        updated = db.pip_records.find_one({"pip_id": pip_id})
        return serialize_doc(updated), None

    @classmethod
    def get_pip(cls, pip_id: str) -> dict | None:
        db = get_db()
        doc = db.pip_records.find_one({"pip_id": pip_id})
        return serialize_doc(doc) if doc else None

    @classmethod
    def list_pips_for_user(cls, user: dict) -> list[dict]:
        db = get_db()
        role = user.get("role")
        emp_id = user.get("employee_id")

        if role in (Role.ADMIN, "organization", Role.HR, "hr_manager"):
            # Full organization view
            pips = list(db.pip_records.find().sort("created_at", -1))
        elif role == Role.MANAGER:
            # Manager sees department or managed employees
            pips = list(db.pip_records.find({
                "$or": [
                    {"department": user.get("department")},
                    {"initiated_by_id": emp_id}
                ]
            }).sort("created_at", -1))
        elif role in (Role.TEAM_LEAD, "trainer"):
            # Team Lead sees initiated or team members
            pips = list(db.pip_records.find({
                "$or": [
                    {"initiated_by_id": emp_id},
                    {"team_id": user.get("team_id")}
                ]
            }).sort("created_at", -1))
        else:
            # Employee sees only their own PIP
            pips = list(db.pip_records.find({"employee_id": emp_id}).sort("created_at", -1))

        return serialize_docs(pips)

