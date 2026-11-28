import logging
from datetime import datetime
from database.connection import get_db
from permissions.rbac import Role
from services.notification_service import NotificationService
from services.audit_service import AuditService
from utils.serializers import serialize_doc, serialize_docs
from utils.timezone import now_utc, get_local_date_str

logger = logging.getLogger(__name__)


class WFHService:
    """
    Work From Home (WFH) Service for AISamrat HRMS:
    Approved Workflow:
    Employee Request -> Manager Approval -> Employee and HR Notified.
    (Team Leads have visibility over their team members' WFH status).
    """

    @classmethod
    def request_wfh(cls, employee: dict, data: dict) -> tuple[dict | None, str | None]:
        db = get_db()
        emp_id = employee.get("employee_id")
        start_date = (data.get("start_date") or "").strip()
        end_date = (data.get("end_date") or start_date).strip()
        reason = (data.get("reason") or "").strip()

        if not start_date:
            return None, "Start date is required."
        if not end_date:
            end_date = start_date
        if not reason:
            return None, "Reason for Work From Home is required."

        try:
            sd = datetime.strptime(start_date, "%Y-%m-%d").date()
            ed = datetime.strptime(end_date, "%Y-%m-%d").date()
            if ed < sd:
                return None, "End date cannot be earlier than start date."
            days_count = (ed - sd).days + 1
        except ValueError:
            return None, "Invalid date format. Use YYYY-MM-DD."

        # Determine manager
        manager_id = employee.get("reporting_manager_id")
        if not manager_id:
            mgr = db.users.find_one({"role": Role.MANAGER, "is_active": True})
            manager_id = mgr["employee_id"] if mgr else None

        count = db.wfh_requests.count_documents({})
        request_id = f"WFH-{1001 + count}"

        doc = {
            "request_id": request_id,
            "employee_id": emp_id,
            "employee_name": employee.get("full_name", emp_id),
            "applicant_role": employee.get("role", Role.EMPLOYEE),
            "department": employee.get("department", "General"),
            "team_id": employee.get("team_id", ""),
            "start_date": start_date,
            "end_date": end_date,
            "days_count": days_count,
            "reason": reason,
            "status": "PENDING_MANAGER",
            "assigned_manager_id": manager_id,
            "reviewed_by_id": None,
            "reviewed_by_name": None,
            "review_remarks": None,
            "reviewed_at": None,
            "created_at": now_utc(),
            "updated_at": now_utc()
        }

        db.wfh_requests.insert_one(doc)
        logger.info("Created WFH request %s for %s", request_id, emp_id)

        # Notify Manager
        try:
            NotificationService.create_notification(
                title=f"New WFH Request: {employee.get('full_name')}",
                message=f"{employee.get('full_name')} ({emp_id}) requested WFH from {start_date} to {end_date}. Reason: {reason}",
                category="ATTENDANCE",
                recipient_id=manager_id,
                link=f"/attendance?tab=wfh&request_id={request_id}"
            )
        except Exception as e:
            logger.warning("Failed to notify manager for WFH request: %s", e)

        # Audit
        try:
            AuditService.log_action(
                actor=employee,
                action="REQUEST_WFH",
                target_type="wfh_request",
                target_id=request_id,
                details={"start_date": start_date, "end_date": end_date, "days": days_count}
            )
        except Exception as e:
            logger.warning("Failed to log WFH audit: %s", e)

        return serialize_doc(doc), None

    @classmethod
    def review_wfh(cls, reviewer: dict, request_id: str, decision: str, remarks: str = "") -> tuple[dict | None, str | None]:
        decision = decision.capitalize()
        if decision not in ("Approved", "Rejected"):
            return None, "Invalid decision. Must be 'Approved' or 'Rejected'."

        clean_remarks = (remarks or "").strip()
        if decision == "Rejected" and not clean_remarks:
            return None, "A rejection reason is required."

        db = get_db()
        req = db.wfh_requests.find_one({"request_id": request_id})
        if not req:
            return None, f"WFH request '{request_id}' not found."

        reviewer_id = reviewer.get("employee_id")
        reviewer_name = reviewer.get("full_name", reviewer_id)
        role = reviewer.get("role")

        if req.get("employee_id") == reviewer_id:
            return None, "Unauthorized: Self-approval of WFH requests is strictly forbidden."

        if role not in (Role.MANAGER, Role.ADMIN, "organization"):
            return None, "Unauthorized: Only Managers and Administrators have authority to review WFH requests."

        curr_status = req.get("status")
        if curr_status != "PENDING_MANAGER":
            return None, f"Request is in '{curr_status}' status and cannot be reviewed."

        next_status = "APPROVED" if decision == "Approved" else "REJECTED"
        update_fields = {
            "status": next_status,
            "reviewed_by_id": reviewer_id,
            "reviewed_by_name": reviewer_name,
            "review_remarks": clean_remarks,
            "reviewed_at": now_utc(),
            "updated_at": now_utc()
        }

        db.wfh_requests.update_one({"request_id": request_id}, {"$set": update_fields})

        # 1. Notify Employee
        try:
            NotificationService.create_notification(
                title=f"WFH Request {decision}",
                message=f"Your WFH request ({request_id}) for {req.get('start_date')} to {req.get('end_date')} has been {decision.lower()} by Manager {reviewer_name}. Remarks: {clean_remarks}",
                category="ATTENDANCE",
                recipient_id=req["employee_id"],
                link=f"/attendance?tab=wfh&request_id={request_id}"
            )
        except Exception as e:
            logger.warning("Failed to notify applicant for WFH: %s", e)

        # 2. Notify HR Intimation
        try:
            hr_users = list(db.users.find({"role": Role.HR, "is_active": True}))
            for hr in hr_users:
                NotificationService.create_notification(
                    title=f"WFH {decision}: {req.get('employee_name')}",
                    message=f"{req.get('employee_name')} ({req.get('employee_id')})'s WFH request ({request_id}) for {req.get('start_date')} to {req.get('end_date')} was {decision.lower()} by Manager {reviewer_name}.",
                    category="ATTENDANCE",
                    recipient_id=hr["employee_id"],
                    link=f"/attendance?tab=wfh&request_id={request_id}"
                )
        except Exception as e:
            logger.warning("Failed to notify HR for WFH intimation: %s", e)

        # Audit
        try:
            AuditService.log_action(
                actor=reviewer,
                action=f"MANAGER_WFH_{decision.upper()}",
                target_type="wfh_request",
                target_id=request_id,
                details={"decision": decision, "remarks": clean_remarks, "applicant_id": req["employee_id"]}
            )
        except Exception as e:
            logger.warning("Failed to log WFH audit: %s", e)

        updated = db.wfh_requests.find_one({"request_id": request_id})
        return serialize_doc(updated), None

    @classmethod
    def get_my_wfh(cls, employee_id: str) -> list[dict]:
        db = get_db()
        reqs = list(db.wfh_requests.find({"employee_id": employee_id}).sort("created_at", -1))
        return serialize_docs(reqs)

    @classmethod
    def get_pending_wfh_for_manager(cls, manager: dict) -> list[dict]:
        db = get_db()
        mgr_id = manager.get("employee_id")
        dept = manager.get("department")
        role = manager.get("role")

        query = {"status": "PENDING_MANAGER", "employee_id": {"$ne": mgr_id}}
        if role not in (Role.ADMIN, "organization"):
            # Department or assigned manager match
            query["$or"] = [
                {"assigned_manager_id": mgr_id},
                {"department": dept}
            ]

        reqs = list(db.wfh_requests.find(query).sort("created_at", -1))
        return serialize_docs(reqs)

    @classmethod
    def get_all_wfh(cls, status_filter: str = None) -> list[dict]:
        db = get_db()
        query = {}
        if status_filter and status_filter.upper() != "ALL":
            query["status"] = status_filter.upper()
        reqs = list(db.wfh_requests.find(query).sort("created_at", -1))
        return serialize_docs(reqs)

    @classmethod
    def get_team_wfh(cls, tl_user: dict) -> list[dict]:
        db = get_db()
        team_id = tl_user.get("team_id")
        query = {}
        if team_id:
            query["team_id"] = team_id
        reqs = list(db.wfh_requests.find(query).sort("created_at", -1))
        return serialize_docs(reqs)

