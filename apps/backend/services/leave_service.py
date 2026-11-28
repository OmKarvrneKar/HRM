import logging
import re
from datetime import datetime, timezone
from database.connection import get_db
from permissions.rbac import Role, normalize_role, can_access_employee_record
from services.notification_service import NotificationService
from services.external_notification_service import ExternalNotificationService
from services.audit_service import AuditService
from utils.serializers import serialize_doc, serialize_docs
from utils.timezone import now_utc, get_local_date_str
from config import Config

logger = logging.getLogger(__name__)

# Approved Standard Leave Policies for AISamrat HRMS:
# Financial Year: April to March.
STANDARD_LEAVE_POLICIES = [
    {
        "code": "CL",
        "name": "Casual Leave",
        "default_days": 12,
        "carry_forward": False
    },
    {
        "code": "SL",
        "name": "Sick Leave",
        "default_days": 10,
        "carry_forward": False
    },
    {
        "code": "EL",
        "name": "Earned Leave",
        "default_days": 15,
        "carry_forward": True
    },
    {
        "code": "COMP_OFF",
        "name": "Comp Off",
        "default_days": 0,
        "carry_forward": False
    },
    {
        "code": "LOP",
        "name": "Loss of Pay",
        "default_days": 0,
        "carry_forward": False
    },
    {
        "code": "ML",
        "name": "Maternity Leave",
        "default_days": 180,
        "carry_forward": False
    },
    {
        "code": "PL",
        "name": "Paternity Leave",
        "default_days": 15,
        "carry_forward": False
    }
]

# Progressive Leave Policies to add to your existing leave structures
PROGRESSIVE_LEAVE_POLICIES = [
    {
        "code": "WFA",
        "name": "Work from Anywhere (WFA) & Flexible Leave",
        "default_days": 12,
        "carry_forward": False
    },
    {
        "code": "MHL",
        "name": "Mental Health Leave",
        "default_days": 5,
        "carry_forward": False
    },
    {
        "code": "WND",
        "name": "Wellness Days",
        "default_days": 3,
        "carry_forward": False
    },
    {
        "code": "PCL",
        "name": "Pet Care Leave",
        "default_days": 3,
        "carry_forward": False
    },
    {
        "code": "NGL",
        "name": "Neutral Gender Leave",
        "default_days": 10,
        "carry_forward": True
    }
]

LEAVE_TYPE_MAP = {
    "CL": "Casual Leave",
    "CASUAL LEAVE": "Casual Leave",
    "CASUAL": "Casual Leave",
    "SL": "Sick Leave",
    "SICK LEAVE": "Sick Leave",
    "SICK": "Sick Leave",
    "EL": "Earned Leave",
    "EARNED LEAVE": "Earned Leave",
    "EARNED": "Earned Leave",
    "PL": "Earned Leave",
    "PRIVILEGE LEAVE": "Earned Leave",
    "LOP": "Loss of Pay",
    "LOSS OF PAY": "Loss of Pay",
    "UNPAID LEAVE": "Loss of Pay",
    "UNPAID": "Loss of Pay",
    "COMP OFF": "Comp Off",
    "COMPENSATORY OFF": "Comp Off",
    "COMPENSATION OFF": "Comp Off",
    "MATERNITY LEAVE": "Maternity Leave",
    "MATERNITY": "Maternity Leave",
    "PATERNITY LEAVE": "Paternity Leave",
    "PATERNITY": "Paternity Leave",
    "EMERGENCY LEAVE": "Casual Leave",
    "HALF DAY LEAVE": "Casual Leave",
    # Progressive Leave Policies
    "WFA": "Work from Anywhere (WFA) & Flexible Leave",
    "WORK FROM ANYWHERE": "Work from Anywhere (WFA) & Flexible Leave",
    "WORK FROM ANYWHERE (WFA) & FLEXIBLE LEAVE": "Work from Anywhere (WFA) & Flexible Leave",
    "WORK FROM ANYWHERE (WFA) AND FLEXIBLE LEAVE": "Work from Anywhere (WFA) & Flexible Leave",
    "WORK FROM ANYWHERE AND FLEXIBLE LEAVE": "Work from Anywhere (WFA) & Flexible Leave",
    "FLEXIBLE LEAVE": "Work from Anywhere (WFA) & Flexible Leave",
    "MHL": "Mental Health Leave",
    "MENTAL HEALTH LEAVE": "Mental Health Leave",
    "MENTAL HEALTH": "Mental Health Leave",
    "WND": "Wellness Days",
    "WELLNESS DAYS": "Wellness Days",
    "WELLNESS DAY": "Wellness Days",
    "WELLNESS": "Wellness Days",
    "PCL": "Pet Care Leave",
    "PET CARE LEAVE": "Pet Care Leave",
    "PET CARE": "Pet Care Leave",
    "NGL": "Neutral Gender Leave",
    "NEUTRAL GENDER LEAVE": "Neutral Gender Leave",
    "NEUTRAL GENDER": "Neutral Gender Leave"
}

VALID_LEAVE_TYPES = [
    "Casual Leave",
    "Sick Leave",
    "Earned Leave",
    "Loss of Pay",
    "Comp Off",
    "Maternity Leave",
    "Paternity Leave",
    "CL",
    "SL",
    "EL",
    "LOP",
    # Progressive Leave Policies
    "Work from Anywhere (WFA) & Flexible Leave",
    "Work from Anywhere (WFA) and Flexible Leave",
    "Mental Health Leave",
    "Wellness Days",
    "Pet Care Leave",
    "Neutral Gender Leave",
    "WFA",
    "MHL",
    "WND",
    "PCL",
    "NGL"
]

VALID_PERMISSION_TYPES = [
    "Early Exit",
    "Late In",
    "Work Permission"
]


class LeaveService:
    """
    Manages Leave and Permission workflow:
    - Employees and Team Leads submit leave and permission requests.
    - Managers review and approve/reject requests.
    - Requesters can track status and cancel pending requests.
    - Managers can prepare and manually dispatch notification emails to HR upon approval.
    - HR is strictly excluded from participating in this approval workflow.
    """

    @classmethod
    def normalize_leave_type(cls, raw_type: str) -> str:
        """Normalizes any leave type string or abbreviation to canonical type."""
        if not raw_type:
            return "Casual Leave"
        cleaned = raw_type.strip().upper()
        return LEAVE_TYPE_MAP.get(cleaned, raw_type.strip())

    @classmethod
    def get_financial_year(cls, date_val=None) -> str:
        """
        Returns the Indian Financial Year string (e.g. '2026-2027') for a given date.
        Financial Year runs from April 1 to March 31.
        """
        if isinstance(date_val, str):
            try:
                d = datetime.strptime(date_val[:10], "%Y-%m-%d").date()
            except Exception:
                d = datetime.now(timezone.utc).date()
        elif isinstance(date_val, datetime):
            d = date_val.date()
        elif hasattr(date_val, "month") and hasattr(date_val, "year"):
            d = date_val
        else:
            d = datetime.now(timezone.utc).date()

        if d.month >= 4:
            return f"{d.year}-{d.year + 1}"
        else:
            return f"{d.year - 1}-{d.year}"

    @classmethod
    def get_progressive_policies(cls) -> list:
        """Returns the configured progressive leave policies."""
        return list(PROGRESSIVE_LEAVE_POLICIES)

    @classmethod
    def get_all_leave_policies(cls) -> list:
        """Returns all standard and progressive leave policies with metadata."""
        combined = []
        for p in STANDARD_LEAVE_POLICIES:
            p_copy = dict(p)
            p_copy["category"] = "Standard"
            p_copy["is_progressive"] = False
            combined.append(p_copy)
        for p in PROGRESSIVE_LEAVE_POLICIES:
            p_copy = dict(p)
            p_copy["category"] = "Progressive"
            p_copy["is_progressive"] = True
            combined.append(p_copy)
        return combined

    @classmethod
    def _get_next_transaction_id(cls, db) -> str:
        """Generates a strictly collision-free unique LTXN-xxxx transaction ID."""
        highest = 1000
        for doc in db.leave_transactions.find({"transaction_id": {"$regex": r"^LTXN-\d+$"}}, {"transaction_id": 1}):
            try:
                num = int(doc["transaction_id"].split("-")[1])
                if num > highest:
                    highest = num
            except Exception:
                pass
        candidate = f"LTXN-{highest + 1}"
        while db.leave_transactions.find_one({"transaction_id": candidate}):
            highest += 1
            candidate = f"LTXN-{highest + 1}"
        return candidate

    @classmethod
    def get_or_create_leave_balance(cls, employee_id: str, financial_year: str = None) -> dict:
        """
        Retrieves or initializes leave balance document for the specified financial year.
        Initializes ledger credit entries for standard and progressive entitlements without hardcoded mock data.
        """
        db = get_db()
        fy = financial_year or cls.get_financial_year()
        bal = db.leave_balances.find_one({"employee_id": employee_id, "financial_year": fy})
        if not bal:
            # Baseline entitlements per AISamrat policy (FY April–March)
            default_balances = {
                "Casual Leave": {"total": 12.0, "used": 0.0, "available": 12.0},
                "Sick Leave": {"total": 10.0, "used": 0.0, "available": 10.0},
                "Earned Leave": {"total": 15.0, "used": 0.0, "available": 15.0},
                "Comp Off": {"total": 0.0, "used": 0.0, "available": 0.0},
                "Loss of Pay": {"total": 0.0, "used": 0.0, "available": 0.0},
                "Maternity Leave": {"total": 180.0, "used": 0.0, "available": 180.0},
                "Paternity Leave": {"total": 15.0, "used": 0.0, "available": 15.0},
                # Progressive Leave Policies
                "Work from Anywhere (WFA) & Flexible Leave": {"total": 12.0, "used": 0.0, "available": 12.0},
                "Mental Health Leave": {"total": 5.0, "used": 0.0, "available": 5.0},
                "Wellness Days": {"total": 3.0, "used": 0.0, "available": 3.0},
                "Pet Care Leave": {"total": 3.0, "used": 0.0, "available": 3.0},
                "Neutral Gender Leave": {"total": 10.0, "used": 0.0, "available": 10.0}
            }
            bal = {
                "employee_id": employee_id,
                "financial_year": fy,
                "balances": default_balances,
                "created_at": now_utc(),
                "updated_at": now_utc()
            }
            db.leave_balances.insert_one(bal)

            # Record initial entitlement credit transactions in ledger
            for ltype, vals in default_balances.items():
                if vals["total"] > 0:
                    txn_id = cls._get_next_transaction_id(db)
                    db.leave_transactions.insert_one({
                        "transaction_id": txn_id,
                        "employee_id": employee_id,
                        "financial_year": fy,
                        "leave_type": ltype,
                        "transaction_type": "CREDIT",
                        "days": vals["total"],
                        "balance_before": 0.0,
                        "balance_after": vals["total"],
                        "reference_request_id": None,
                        "remarks": f"Annual Entitlement Credit FY {fy}",
                        "performed_by": "SYSTEM",
                        "created_at": now_utc()
                    })
        else:
            # Backfill any progressive policies missing from an existing employee's balance record
            missing_updates = {}
            for pol in PROGRESSIVE_LEAVE_POLICIES:
                pol_name = pol["name"]
                if pol_name not in bal.get("balances", {}):
                    days = float(pol["default_days"])
                    bal.setdefault("balances", {})[pol_name] = {"total": days, "used": 0.0, "available": days}
                    missing_updates[f"balances.{pol_name}"] = {"total": days, "used": 0.0, "available": days}

                    txn_id = cls._get_next_transaction_id(db)
                    db.leave_transactions.insert_one({
                        "transaction_id": txn_id,
                        "employee_id": employee_id,
                        "financial_year": fy,
                        "leave_type": pol_name,
                        "transaction_type": "CREDIT",
                        "days": days,
                        "balance_before": 0.0,
                        "balance_after": days,
                        "reference_request_id": None,
                        "remarks": f"Progressive Entitlement Credit FY {fy}",
                        "performed_by": "SYSTEM",
                        "created_at": now_utc()
                    })
            if missing_updates:
                missing_updates["updated_at"] = now_utc()
                db.leave_balances.update_one({"_id": bal["_id"]}, {"$set": missing_updates})

        return bal

    @classmethod
    def get_leave_ledger(cls, employee_id: str, financial_year: str = None) -> dict:
        """
        Retrieves leave ledger transactions and current balances for an employee.
        """
        db = get_db()
        fy = financial_year or cls.get_financial_year()
        bal_doc = cls.get_or_create_leave_balance(employee_id, fy)
        query = {"employee_id": employee_id}
        if fy:
            query["financial_year"] = fy
        transactions = list(db.leave_transactions.find(query).sort("created_at", -1))
        return {
            "employee_id": employee_id,
            "financial_year": fy,
            "balances": bal_doc.get("balances", {}),
            "transactions": serialize_docs(transactions)
        }

    @classmethod
    def determine_approver_and_initial_status(cls, employee: dict) -> tuple[str, str | None, str | None]:
        """
        Determines initial status and assigned approvers based on actual database reporting relationships.
        Returns: (status, assigned_tl_id, assigned_manager_id)
        """
        db = get_db()
        emp_id = employee.get("employee_id")
        role = employee.get("role", Role.EMPLOYEE)
        team_id = employee.get("team_id")
        reporting_mgr_id = employee.get("reporting_manager_id")

        if role in (Role.MANAGER, Role.ADMIN, "organization"):
            # Manager cannot approve their own leave. Pending authorization state.
            return "PENDING_AUTHORIZATION", None, None

        if role in (Role.TEAM_LEAD, Role.TL, "tl", "trainer", "team_lead"):
            # Team Lead personal leave goes directly to assigned Manager
            manager_id = reporting_mgr_id
            if not manager_id:
                mgr = db.users.find_one({"role": {"$in": [Role.MANAGER, "manager", "organization"]}, "is_active": True})
                manager_id = mgr["employee_id"] if mgr else None
            return "PENDING_MANAGER", None, manager_id

        # Normal Employee: check for assigned Team Lead
        tl_id = None
        # 1. Check reporting_manager_id if it's a team lead
        if reporting_mgr_id:
            rep_user = db.users.find_one({"employee_id": reporting_mgr_id})
            if rep_user and rep_user.get("role") in (Role.TEAM_LEAD, Role.TL, "tl", "trainer", "team_lead"):
                tl_id = reporting_mgr_id

        # 2. Check assigned_tl field if present
        if not tl_id and (employee.get("assigned_tl") or employee.get("assigned_tl_id")):
            tl_id = employee.get("assigned_tl") or employee.get("assigned_tl_id")

        # 3. Check team_id in teams collection
        if not tl_id and team_id:
            team_doc = db.teams.find_one({"team_id": team_id})
            if team_doc:
                lead_id = team_doc.get("lead_employee_id") or team_doc.get("lead_id")
                if lead_id and lead_id != emp_id:
                    tl_id = lead_id

        # 4. Check users collection for team lead in same team
        if not tl_id and team_id:
            tl_user = db.users.find_one({"team_id": team_id, "role": {"$in": [Role.TEAM_LEAD, Role.TL, "tl", "team_lead", "trainer"]}, "is_active": True})
            if tl_user and tl_user.get("employee_id") != emp_id:
                tl_id = tl_user.get("employee_id")

        # 5. Check if employee is in members list of any team
        if not tl_id:
            team_doc = db.teams.find_one({"members": emp_id})
            if team_doc:
                lead_id = team_doc.get("lead_employee_id") or team_doc.get("lead_id")
                if lead_id and lead_id != emp_id:
                    tl_id = lead_id

        # 6. Check active projects where employee is an assigned member
        if not tl_id:
            proj = db.projects.find_one({"$or": [{"members": emp_id}, {"assigned_members": emp_id}], "is_approved": True})
            if proj:
                p_lead = proj.get("lead_id") or proj.get("project_lead")
                if p_lead and p_lead != emp_id:
                    lead_user = db.users.find_one({"employee_id": p_lead})
                    if lead_user and lead_user.get("role") in (Role.TEAM_LEAD, Role.TL, "tl", "trainer", "team_lead"):
                        tl_id = p_lead

        # 7. Check department for a team lead
        if not tl_id and employee.get("department"):
            tl_user = db.users.find_one({"department": employee.get("department"), "role": {"$in": [Role.TEAM_LEAD, Role.TL, "tl", "team_lead", "trainer"]}, "is_active": True})
            if tl_user and tl_user.get("employee_id") != emp_id:
                tl_id = tl_user.get("employee_id")

        # 8. Check for company's active Team Lead fallback for real employees
        if not tl_id and not employee.get("email", "").endswith(".local"):
            tl_user = db.users.find_one({"role": {"$in": [Role.TEAM_LEAD, Role.TL, "tl", "team_lead", "trainer"]}, "is_active": True})
            if tl_user and tl_user.get("employee_id") != emp_id:
                tl_id = tl_user.get("employee_id")

        # Determine manager id
        manager_id = None
        if reporting_mgr_id:
            rep_user = db.users.find_one({"employee_id": reporting_mgr_id})
            if rep_user and rep_user.get("role") in (Role.MANAGER, Role.ADMIN, "organization"):
                manager_id = reporting_mgr_id
        if not manager_id and tl_id:
            tl_user = db.users.find_one({"employee_id": tl_id})
            if tl_user and tl_user.get("reporting_manager_id"):
                manager_id = tl_user.get("reporting_manager_id")
        if not manager_id and employee.get("department"):
            dept_mgr = db.users.find_one({"department": employee.get("department"), "role": Role.MANAGER, "is_active": True})
            if dept_mgr and dept_mgr.get("employee_id") != emp_id:
                manager_id = dept_mgr["employee_id"]
        if not manager_id and db.users.count_documents({"role": Role.MANAGER, "is_active": True}) == 1:
            mgr = db.users.find_one({"role": Role.MANAGER, "is_active": True})
            if mgr and mgr.get("employee_id") != emp_id:
                manager_id = mgr["employee_id"]

        if tl_id:
            return "PENDING_TEAM_LEAD", tl_id, manager_id
        else:
            # If no Team Lead configured/assigned, moves directly to Manager
            return "PENDING_MANAGER", None, manager_id

    @classmethod
    def apply_leave(cls, employee: dict, data: dict) -> tuple[dict | None, str | None]:
        """
        Employee or Team Lead applies for a leave of absence.
        Follows two-stage approval: Employee -> Team Lead -> Manager.
        Team Lead personal leave goes directly to Manager.
        Manager personal leave enters PENDING_AUTHORIZATION.
        """
        db = get_db()
        raw_leave_type = (data.get("leave_type") or "Casual Leave").strip()
        leave_type = cls.normalize_leave_type(raw_leave_type)
        start_date = (data.get("start_date") or "").strip()
        end_date = (data.get("end_date") or start_date).strip()
        reason = (data.get("reason") or "").strip()
        is_half_day = bool(data.get("is_half_day", False))

        if not start_date:
            return None, "Start date is required."
        if not end_date:
            end_date = start_date
        if not reason:
            return None, "Reason for leave is required."

        # Date validation & days calculation
        try:
            sd = datetime.strptime(start_date, "%Y-%m-%d").date()
            ed = datetime.strptime(end_date, "%Y-%m-%d").date()
            if ed < sd:
                return None, "End date cannot be prior to start date."
            diff = (ed - sd).days + 1
            days_count = 0.5 if is_half_day else float(diff)
        except ValueError:
            return None, "Invalid date format. Use YYYY-MM-DD."

        count = db.leave_requests.count_documents({})
        num = 1001 + count
        while db.leave_requests.find_one({"request_id": f"LR-{num}"}):
            num += 1
        request_id = f"LR-{num}"

        initial_status, assigned_tl_id, assigned_manager_id = cls.determine_approver_and_initial_status(employee)

        doc = {
            "request_id": request_id,
            "request_type": "LEAVE",
            "employee_id": employee["employee_id"],
            "employee_name": employee.get("full_name", "Employee"),
            "applicant_role": employee.get("role", Role.EMPLOYEE),
            "department": employee.get("department", "General"),
            "team_id": employee.get("team_id", ""),
            "leave_type": leave_type,
            "start_date": start_date,
            "end_date": end_date,
            "days_count": days_count,
            "is_half_day": is_half_day,
            "reason": reason,
            "status": initial_status,
            "assigned_tl_id": assigned_tl_id,
            "assigned_manager_id": assigned_manager_id,
            "reviewed_by_id": None,
            "reviewed_by_name": None,
            "review_remarks": None,
            "reviewed_at": None,
            "rejection_reason": None,
            "approval_history": [],
            "email_history": [],
            "created_at": now_utc(),
            "updated_at": now_utc()
        }

        db.leave_requests.insert_one(doc)
        logger.info("Created leave request '%s' (status: %s) for employee '%s'", request_id, initial_status, employee["employee_id"])

        # Approver notifications strictly routed by hierarchy stage
        try:
            if initial_status == "PENDING_TEAM_LEAD":
                # Actionable notification strictly to assigned Team Lead
                NotificationService.create_notification(
                    title=f"New Leave Request from {employee.get('full_name')}",
                    message=f"{employee.get('full_name')} ({employee['employee_id']}) applied for {leave_type} ({days_count} day(s)) from {start_date} to {end_date}. Reason: {reason}",
                    category="LEAVE",
                    recipient_id=assigned_tl_id,
                    link=f"/leaves?request_id={request_id}"
                )
            elif initial_status == "PENDING_MANAGER":
                NotificationService.create_notification(
                    title=f"New Leave Request from {employee.get('full_name')}",
                    message=f"{employee.get('full_name')} ({employee['employee_id']}) applied for {leave_type} ({days_count} day(s)) from {start_date} to {end_date}. Reason: {reason}",
                    category="LEAVE",
                    recipient_group="MANAGER",
                    link=f"/leaves?request_id={request_id}"
                )
        except Exception as e:
            logger.warning("Failed to create approver notification: %s", str(e))

        # Log audit trail
        try:
            AuditService.log_action(
                actor=employee,
                action="APPLY_LEAVE",
                target_type="leave_request",
                target_id=request_id,
                details={"leave_type": leave_type, "days": days_count, "start": start_date, "end": end_date, "status": initial_status}
            )
        except Exception as e:
            logger.warning("Failed to log audit action: %s", str(e))

        return serialize_doc(doc), None

    @classmethod
    def apply_permission(cls, employee: dict, data: dict) -> tuple[dict | None, str | None]:
        """
        Employee or Team Lead applies for early exit or permission.
        Follows two-stage approval: Employee -> Team Lead -> Manager.
        """
        db = get_db()
        permission_date = (data.get("permission_date") or get_local_date_str()).strip()
        early_exit_time = (data.get("early_exit_time") or "").strip()
        permission_type = (data.get("permission_type") or "Early Exit").strip()
        reason = (data.get("reason") or "").strip()

        if not permission_date:
            return None, "Permission date is required."
        if not early_exit_time:
            return None, "Requested early exit time is required (e.g. 16:30)."
        if not reason:
            return None, "Reason for early exit permission is required."

        count = db.leave_requests.count_documents({})
        request_id = f"PR-{1001 + count}"

        initial_status, assigned_tl_id, assigned_manager_id = cls.determine_approver_and_initial_status(employee)

        doc = {
            "request_id": request_id,
            "request_type": "PERMISSION",
            "employee_id": employee["employee_id"],
            "employee_name": employee.get("full_name", "Employee"),
            "applicant_role": employee.get("role", Role.EMPLOYEE),
            "department": employee.get("department", "General"),
            "team_id": employee.get("team_id", ""),
            "permission_type": permission_type,
            "permission_date": permission_date,
            "early_exit_time": early_exit_time,
            "reason": reason,
            "status": initial_status,
            "assigned_tl_id": assigned_tl_id,
            "assigned_manager_id": assigned_manager_id,
            "reviewed_by_id": None,
            "reviewed_by_name": None,
            "review_remarks": None,
            "reviewed_at": None,
            "rejection_reason": None,
            "approval_history": [],
            "email_history": [],
            "created_at": now_utc(),
            "updated_at": now_utc()
        }

        db.leave_requests.insert_one(doc)
        logger.info("Created permission request '%s' (status: %s) for employee '%s'", request_id, initial_status, employee["employee_id"])

        # Approver notifications
        try:
            if initial_status == "PENDING_TEAM_LEAD":
                # Strictly target the assigned Team Lead; do not broadcast to all Team Leads
                NotificationService.create_notification(
                    title=f"Early Exit Request from {employee.get('full_name')}",
                    message=f"{employee.get('full_name')} requested permission to leave early at {early_exit_time} on {permission_date}. Reason: {reason}",
                    category="PERMISSION",
                    recipient_id=assigned_tl_id,
                    link=f"/leaves?request_id={request_id}"
                )
            elif initial_status == "PENDING_MANAGER":
                NotificationService.create_notification(
                    title=f"Early Exit Request from {employee.get('full_name')}",
                    message=f"{employee.get('full_name')} requested permission to leave early at {early_exit_time} on {permission_date}. Reason: {reason}",
                    category="PERMISSION",
                    recipient_group="MANAGER",
                    link=f"/leaves?request_id={request_id}"
                )
        except Exception as e:
            logger.warning("Failed to create approver notification: %s", str(e))

        # Log audit trail
        try:
            AuditService.log_action(
                actor=employee,
                action="APPLY_PERMISSION",
                target_type="permission_request",
                target_id=request_id,
                details={"date": permission_date, "time": early_exit_time, "type": permission_type, "status": initial_status}
            )
        except Exception as e:
            logger.warning("Failed to log audit action: %s", str(e))

        return serialize_doc(doc), None

    @classmethod
    def get_employee_requests(cls, employee_id: str, status_filter: str = None) -> dict:
        """
        Retrieves all leave and early exit requests for a specific employee or team lead.
        Supports both legacy status conventions and two-stage workflow statuses.
        """
        db = get_db()
        query = {"employee_id": employee_id}
        if status_filter and status_filter.upper() != "ALL":
            if status_filter in ("Pending", "PENDING"):
                query["status"] = {"$in": ["Pending", "PENDING_TEAM_LEAD", "PENDING_MANAGER", "PENDING_AUTHORIZATION"]}
            elif status_filter in ("Approved", "APPROVED"):
                query["status"] = {"$in": ["Approved", "APPROVED"]}
            elif status_filter in ("Rejected", "REJECTED"):
                query["status"] = {"$in": ["Rejected", "REJECTED"]}
            elif status_filter in ("Cancelled", "CANCELLED"):
                query["status"] = {"$in": ["Cancelled", "CANCELLED"]}
            else:
                query["status"] = status_filter

        cursor = db.leave_requests.find(query).sort("created_at", -1)
        requests = list(cursor)

        all_emp_reqs = list(db.leave_requests.find({"employee_id": employee_id}))
        pending_count = sum(1 for r in all_emp_reqs if r.get("status") in ("Pending", "PENDING_TEAM_LEAD", "PENDING_MANAGER", "PENDING_AUTHORIZATION"))
        approved_count = sum(1 for r in all_emp_reqs if r.get("status") in ("Approved", "APPROVED"))
        rejected_count = sum(1 for r in all_emp_reqs if r.get("status") in ("Rejected", "REJECTED"))
        cancelled_count = sum(1 for r in all_emp_reqs if r.get("status") in ("Cancelled", "CANCELLED"))

        approved_leaves = sum(1 for r in all_emp_reqs if r.get("status") in ("Approved", "APPROVED") and r.get("request_type") == "LEAVE")
        approved_permissions = sum(1 for r in all_emp_reqs if r.get("status") in ("Approved", "APPROVED") and r.get("request_type") == "PERMISSION")

        return {
            "requests": serialize_docs(requests),
            "summary": {
                "total_count": len(all_emp_reqs),
                "pending_count": pending_count,
                "approved_count": approved_count,
                "rejected_count": rejected_count,
                "cancelled_count": cancelled_count,
                "approved_leaves_count": approved_leaves,
                "approved_permissions_count": approved_permissions
            }
        }

    @classmethod
    def get_all_requests_for_reviewer(cls, reviewer: dict, status_filter: str = None, request_type: str = None) -> dict:
        """
        Retrieves leave and permission requests for Team Lead or Manager approval queue.
        - Team Lead: sees requests from their assigned team members (status: PENDING_TEAM_LEAD or team history).
        - Manager: sees requests awaiting manager approval (status: PENDING_MANAGER) and authorized history.
        - Self-requests and HR requests are strictly excluded.
        """
        db = get_db()
        role = normalize_role(reviewer.get("role"))
        reviewer_id = reviewer.get("employee_id") or reviewer.get("emp_id")

        if role not in (Role.TL, Role.MANAGER, Role.ADMIN):
            return {
                "requests": [],
                "summary": {
                    "total_count": 0,
                    "pending_count": 0,
                    "approved_count": 0,
                    "rejected_count": 0,
                    "cancelled_count": 0
                }
            }

        # Query setup: exclude reviewer's own requests and exclude HR requests
        query = {
            "employee_id": {"$ne": reviewer_id},
            "applicant_role": {"$ne": Role.HR}
        }

        # Role-scoped filter
        if role == Role.TL:
            team_id = reviewer.get("team_id")
            tl_filter = [{"assigned_tl_id": reviewer_id}]
            if team_id:
                tl_filter.append({"team_id": team_id})
            teams_led = [t["team_id"] for t in db.teams.find({"$or": [{"lead_employee_id": reviewer_id}, {"lead_id": reviewer_id}]}, {"team_id": 1}) if t.get("team_id")]
            for t_id in teams_led:
                if t_id != team_id:
                    tl_filter.append({"team_id": t_id})
            query["$or"] = tl_filter
        elif role == Role.MANAGER:
            dept = reviewer.get("department")
            mgr_filter = [{"assigned_manager_id": reviewer_id}]
            if dept and dept not in ("Management", "Executive", "Executive HR"):
                mgr_filter.append({"department": dept})
            sub_docs = db.users.find({"$or": [{"manager_id": reviewer_id}, {"reporting_manager_id": reviewer_id}]}, {"employee_id": 1, "emp_id": 1})
            subordinates = [u.get("employee_id") or u.get("emp_id") for u in sub_docs if (u.get("employee_id") or u.get("emp_id"))]
            if subordinates:
                mgr_filter.append({"employee_id": {"$in": subordinates}})
            query["$or"] = mgr_filter

        if request_type and request_type.upper() != "ALL":
            query["request_type"] = request_type.upper()

        if status_filter and status_filter.upper() != "ALL":
            if status_filter in ("Pending", "PENDING"):
                if role == Role.TL:
                    query["status"] = {"$in": ["PENDING_TEAM_LEAD", "Pending"]}
                elif role == Role.ADMIN:
                    query["status"] = {"$in": ["PENDING_TEAM_LEAD", "PENDING_MANAGER", "PENDING_HR", "Pending", "TL_Approved"]}
                else:
                    query["status"] = {"$in": ["PENDING_MANAGER", "Pending", "TL_Approved"]}
            elif status_filter in ("Approved", "APPROVED"):
                query["status"] = {"$in": ["Approved", "APPROVED"]}
            elif status_filter in ("Rejected", "REJECTED"):
                query["status"] = {"$in": ["Rejected", "REJECTED"]}
            elif status_filter in ("Cancelled", "CANCELLED"):
                query["status"] = {"$in": ["Cancelled", "CANCELLED"]}
            else:
                query["status"] = status_filter

        cursor = db.leave_requests.find(query).sort([("created_at", -1)])
        requests = list(cursor)

        base_count_query = {
            "employee_id": {"$ne": reviewer_id},
            "applicant_role": {"$ne": Role.HR}
        }
        if role == Role.TL:
            team_id = reviewer.get("team_id")
            tl_filter = [{"assigned_tl_id": reviewer_id}]
            if team_id:
                tl_filter.append({"team_id": team_id})
            teams_led = [t["team_id"] for t in db.teams.find({"$or": [{"lead_employee_id": reviewer_id}, {"lead_id": reviewer_id}]}, {"team_id": 1}) if t.get("team_id")]
            for t_id in teams_led:
                if t_id != team_id:
                    tl_filter.append({"team_id": t_id})
            base_count_query["$or"] = tl_filter
        elif role == Role.MANAGER:
            dept = reviewer.get("department")
            mgr_filter = [{"assigned_manager_id": reviewer_id}]
            if dept and dept not in ("Management", "Executive", "Executive HR"):
                mgr_filter.append({"department": dept})
            sub_docs = db.users.find({"$or": [{"manager_id": reviewer_id}, {"reporting_manager_id": reviewer_id}]}, {"employee_id": 1, "emp_id": 1})
            subordinates = [u.get("employee_id") or u.get("emp_id") for u in sub_docs if (u.get("employee_id") or u.get("emp_id"))]
            if subordinates:
                mgr_filter.append({"employee_id": {"$in": subordinates}})
            base_count_query["$or"] = mgr_filter

        all_scoped = list(db.leave_requests.find(base_count_query))
        if role == Role.TL:
            pending_count = sum(1 for r in all_scoped if r.get("status") in ("PENDING_TEAM_LEAD", "Pending"))
        elif role == Role.ADMIN:
            pending_count = sum(1 for r in all_scoped if r.get("status") in ("PENDING_TEAM_LEAD", "PENDING_MANAGER", "PENDING_HR", "Pending", "TL_Approved"))
        else:
            pending_count = sum(1 for r in all_scoped if r.get("status") in ("PENDING_MANAGER", "Pending", "TL_Approved"))

        approved_count = sum(1 for r in all_scoped if r.get("status") in ("Approved", "APPROVED"))
        rejected_count = sum(1 for r in all_scoped if r.get("status") in ("Rejected", "REJECTED"))
        cancelled_count = sum(1 for r in all_scoped if r.get("status") in ("Cancelled", "CANCELLED"))

        return {
            "requests": serialize_docs(requests),
            "summary": {
                "total_count": len(all_scoped),
                "pending_count": pending_count,
                "approved_count": approved_count,
                "rejected_count": rejected_count,
                "cancelled_count": cancelled_count
            }
        }

    @classmethod
    def get_all_requests_for_hr(cls, status_filter: str = None, request_type: str = None) -> dict:
        """
        HR is excluded from leave verification workflow.
        Returns empty list for HR verification queue.
        """
        return {
            "requests": [],
            "summary": {
                "total_count": 0,
                "pending_count": 0,
                "approved_count": 0,
                "rejected_count": 0,
                "cancelled_count": 0
            }
        }

    @classmethod
    def verify_request(cls, reviewer: dict, request_id: str, decision: str, remarks: str = "") -> tuple[dict | None, str | None]:
        """
        Two-stage approval workflow:
        1. Employee submits request -> Assigned Team Lead approves or rejects.
        2. If Team Lead approves -> Request moves to Manager queue (PENDING_MANAGER).
        3. Manager gives final approval (APPROVED) or rejection (REJECTED).
        4. Team Lead personal leave goes directly to Manager.
        5. Neither Team Lead nor Manager can approve their own leave.
        6. Rejection at any stage stops the workflow with recorded reason.
        """
        decision = decision.capitalize()
        if decision not in ("Approved", "Rejected"):
            return None, "Invalid decision. Must be 'Approved' or 'Rejected'."

        clean_remarks = (remarks or "").strip()
        if decision == "Rejected" and not clean_remarks:
            return None, "A rejection reason is required."

        db = get_db()
        req = db.leave_requests.find_one({"request_id": request_id})
        if not req:
            return None, f"Request '{request_id}' not found."

        # Strictly prevent unauthorized self-approval
        reviewer_id = reviewer.get("employee_id") or reviewer.get("emp_id")
        if req.get("employee_id") and reviewer_id and str(req.get("employee_id")).strip().upper() == str(reviewer_id).strip().upper():
            return None, "Unauthorized: Self-approval of leave requests is strictly forbidden."

        role = normalize_role(reviewer.get("role"))
        if role == Role.HR:
            return None, "Unauthorized: HR is strictly excluded from the leave approval workflow."
        if role == Role.EMPLOYEE:
            return None, "Only authorized Team Leads, Managers, or Administrators can approve leave requests."

        reviewer_name = reviewer.get("full_name", reviewer_id)
        current_status = req.get("status", "Pending")

        if current_status in ("Approved", "APPROVED"):
            return None, "Duplicate Action: This request has already been approved."
        if current_status in ("Rejected", "REJECTED"):
            return None, "Duplicate Action: This request has already been rejected."
        if current_status in ("Cancelled", "CANCELLED"):
            return None, "Cannot review request: This request was cancelled by the requester."

        req_type_label = "Leave" if req.get("request_type") == "LEAVE" else "Permission"

        # -----------------------------------------------------------------
        # STAGE 1: TEAM LEAD REVIEW
        # -----------------------------------------------------------------
        if role == Role.TL:
            if current_status not in ("PENDING_TEAM_LEAD", "Pending"):
                return None, f"Unauthorized: Request is in '{current_status}' status and cannot be reviewed by Team Lead."

            # Verify reporting relationship / team membership
            req_team = req.get("team_id")
            tl_team = reviewer.get("team_id")
            assigned_tl = req.get("assigned_tl_id")
            if assigned_tl:
                if str(assigned_tl).strip().upper() != str(reviewer_id or "").strip().upper():
                    return None, "Access Denied: This request is assigned to another Team Lead."
            else:
                if req_team and tl_team and req_team != tl_team:
                    return None, "Access Denied: You can only review requests from your assigned team members."
                if not can_access_employee_record(reviewer, req.get("employee_id")):
                    return None, "Access Denied: You can only review requests from your assigned team members."

            history_entry = {
                "stage": "TEAM_LEAD",
                "decision": decision,
                "reviewer_id": reviewer_id,
                "reviewer_name": reviewer_name,
                "reviewer_role": "team_lead",
                "remarks": clean_remarks,
                "timestamp": now_utc()
            }

            if decision == "Approved":
                next_status = "PENDING_MANAGER"
                update_fields = {
                    "status": next_status,
                    "tl_reviewed_by_id": reviewer_id,
                    "tl_reviewed_by_name": reviewer_name,
                    "tl_review_remarks": clean_remarks,
                    "tl_reviewed_at": now_utc(),
                    "updated_at": now_utc()
                }
                db.leave_requests.update_one(
                    {"request_id": request_id},
                    {"$set": update_fields, "$push": {"approval_history": history_entry}}
                )

                # Notify Manager
                try:
                    NotificationService.create_notification(
                        title=f"{req_type_label} Request Awaiting Manager Approval",
                        message=f"{req.get('employee_name')} ({req.get('employee_id')}) request approved by Team Lead {reviewer_name} and is now pending your final approval.",
                        category="LEAVE",
                        recipient_group="MANAGER",
                        link=f"/leaves?request_id={request_id}"
                    )
                except Exception as e:
                    logger.warning("Failed to notify manager: %s", e)

                # Notify Employee
                try:
                    NotificationService.create_notification(
                        title=f"{req_type_label} Request Approved by Team Lead",
                        message=f"Your {req_type_label.lower()} request ({request_id}) was approved by Team Lead {reviewer_name} and moved to Manager final approval queue.",
                        category="LEAVE",
                        recipient_id=req["employee_id"],
                        link=f"/leaves?request_id={request_id}"
                    )
                except Exception as e:
                    logger.warning("Failed to notify applicant: %s", e)

            else:  # Rejected
                next_status = "Rejected"
                update_fields = {
                    "status": next_status,
                    "rejection_reason": clean_remarks,
                    "tl_reviewed_by_id": reviewer_id,
                    "tl_reviewed_by_name": reviewer_name,
                    "tl_review_remarks": clean_remarks,
                    "tl_reviewed_at": now_utc(),
                    "updated_at": now_utc()
                }
                db.leave_requests.update_one(
                    {"request_id": request_id},
                    {"$set": update_fields, "$push": {"approval_history": history_entry}}
                )
                try:
                    NotificationService.create_notification(
                        title=f"{req_type_label} Request Rejected",
                        message=f"Your {req_type_label.lower()} request ({request_id}) was rejected by Team Lead {reviewer_name}. Reason: {clean_remarks}",
                        category="LEAVE",
                        recipient_id=req["employee_id"],
                        link=f"/leaves?request_id={request_id}"
                    )
                except Exception as e:
                    logger.warning("Failed to notify applicant: %s", e)

            # Log audit
            try:
                AuditService.log_action(
                    actor=reviewer,
                    action=f"TEAM_LEAD_{decision.upper()}_{req.get('request_type', 'REQUEST')}",
                    target_type="leave_request",
                    target_id=request_id,
                    details={"decision": decision, "remarks": clean_remarks, "next_status": next_status}
                )
            except Exception as e:
                logger.warning("Failed to log audit action: %s", e)

            updated = db.leave_requests.find_one({"request_id": request_id})
            return serialize_doc(updated), None

        # -----------------------------------------------------------------
        # STAGE 2: MANAGER / ADMIN REVIEW (FINAL DECISION)
        # -----------------------------------------------------------------
        elif role in (Role.MANAGER, Role.ADMIN):
            if current_status == "PENDING_TEAM_LEAD" and role != Role.ADMIN:
                return None, "Unauthorized: Request is awaiting mandatory first review by assigned Team Lead and cannot be approved by Manager yet."
            if current_status not in ("PENDING_TEAM_LEAD", "PENDING_MANAGER", "Pending", "TL_Approved"):
                return None, f"Unauthorized: Request is in '{current_status}' status and cannot be reviewed."
            if role == Role.MANAGER:
                in_scope = (
                    (req.get("assigned_manager_id") and str(req.get("assigned_manager_id")).strip().upper() == str(reviewer_id or "").strip().upper())
                    or can_access_employee_record(reviewer, req.get("employee_id"))
                )
                if not in_scope:
                    return None, "Access Denied: You can only review leave requests within your reporting scope."

            history_entry = {
                "stage": "MANAGER",
                "decision": decision,
                "reviewer_id": reviewer_id,
                "reviewer_name": reviewer_name,
                "reviewer_role": "manager",
                "remarks": clean_remarks,
                "timestamp": now_utc()
            }

            if decision == "Approved":
                next_status = "Approved"
                update_fields = {
                    "status": next_status,
                    "reviewed_by_id": reviewer_id,
                    "reviewed_by_name": reviewer_name,
                    "reviewed_by_role": role,
                    "review_remarks": clean_remarks,
                    "reviewed_at": now_utc(),
                    "updated_at": now_utc()
                }
                db.leave_requests.update_one(
                    {"request_id": request_id},
                    {"$set": update_fields, "$push": {"approval_history": history_entry}}
                )

                # Deduct leave balance & record immutable ledger transaction if LEAVE
                if req.get("request_type") == "LEAVE":
                    days = float(req.get("days_count", 1))
                    raw_ltype = req.get("leave_type", "Casual Leave")
                    ltype = cls.normalize_leave_type(raw_ltype)
                    fy = cls.get_financial_year(req.get("start_date"))

                    emp_bal = cls.get_or_create_leave_balance(req["employee_id"], fy)
                    bal_dict = emp_bal.get("balances", {}).get(ltype, {"total": 0.0, "used": 0.0, "available": 0.0})
                    balance_before = float(bal_dict.get("available", 0.0))
                    balance_after = balance_before - days
                    used_after = float(bal_dict.get("used", 0.0)) + days

                    db.leave_balances.update_one(
                        {"employee_id": req["employee_id"], "financial_year": fy},
                        {
                            "$set": {
                                f"balances.{ltype}.used": used_after,
                                f"balances.{ltype}.available": balance_after,
                                "updated_at": now_utc()
                            }
                        }
                    )

                    txn_id = cls._get_next_transaction_id(db)
                    db.leave_transactions.insert_one({
                        "transaction_id": txn_id,
                        "employee_id": req["employee_id"],
                        "financial_year": fy,
                        "leave_type": ltype,
                        "transaction_type": "DEBIT",
                        "days": days,
                        "balance_before": balance_before,
                        "balance_after": balance_after,
                        "reference_request_id": request_id,
                        "remarks": clean_remarks or f"Leave approved by Manager {reviewer_name}",
                        "performed_by": reviewer_id,
                        "created_at": now_utc()
                    })

                try:
                    NotificationService.create_notification(
                        title=f"{req_type_label} Request Approved",
                        message=f"Your {req_type_label.lower()} request ({request_id}) has received final approval from Manager {reviewer_name}. Remarks: {clean_remarks}",
                        category="LEAVE",
                        recipient_id=req["employee_id"],
                        link=f"/leaves?request_id={request_id}"
                    )
                except Exception as e:
                    logger.warning("Failed to notify applicant: %s", e)

                # Intimate HR of final approval
                try:
                    hr_users = list(db.users.find({"role": Role.HR, "is_active": True}))
                    for hr_user in hr_users:
                        NotificationService.create_notification(
                            title=f"Leave Approved: {req.get('employee_name')}",
                            message=f"{req.get('employee_name')} ({req.get('employee_id')})'s {req.get('leave_type', 'leave')} request ({request_id}) was approved by Manager {reviewer_name}.",
                            category="LEAVE",
                            recipient_id=hr_user["employee_id"],
                            link=f"/leaves?request_id={request_id}"
                        )
                except Exception as e:
                    logger.warning("Failed to notify HR: %s", e)

            else:  # Rejected
                next_status = "Rejected"
                update_fields = {
                    "status": next_status,
                    "rejection_reason": clean_remarks,
                    "reviewed_by_id": reviewer_id,
                    "reviewed_by_name": reviewer_name,
                    "reviewed_by_role": role,
                    "review_remarks": clean_remarks,
                    "reviewed_at": now_utc(),
                    "updated_at": now_utc()
                }
                db.leave_requests.update_one(
                    {"request_id": request_id},
                    {"$set": update_fields, "$push": {"approval_history": history_entry}}
                )
                try:
                    NotificationService.create_notification(
                        title=f"{req_type_label} Request Rejected",
                        message=f"Your {req_type_label.lower()} request ({request_id}) was rejected by Manager {reviewer_name}. Reason: {clean_remarks}",
                        category="LEAVE",
                        recipient_id=req["employee_id"],
                        link=f"/leaves?request_id={request_id}"
                    )
                except Exception as e:
                    logger.warning("Failed to notify applicant: %s", e)

                # Intimate HR of rejection
                try:
                    hr_users = list(db.users.find({"role": Role.HR, "is_active": True}))
                    for hr_user in hr_users:
                        NotificationService.create_notification(
                            title=f"Leave Rejected: {req.get('employee_name')}",
                            message=f"{req.get('employee_name')} ({req.get('employee_id')})'s {req.get('leave_type', 'leave')} request ({request_id}) was rejected by Manager {reviewer_name}. Reason: {clean_remarks}",
                            category="LEAVE",
                            recipient_id=hr_user["employee_id"],
                            link=f"/leaves?request_id={request_id}"
                        )
                except Exception as e:
                    logger.warning("Failed to notify HR: %s", e)

            # Log audit
            try:
                AuditService.log_action(
                    actor=reviewer,
                    action=f"MANAGER_{decision.upper()}_{req.get('request_type', 'REQUEST')}",
                    target_type="leave_request",
                    target_id=request_id,
                    details={"decision": decision, "remarks": clean_remarks, "next_status": next_status, "applicant_id": req["employee_id"]}
                )
            except Exception as e:
                logger.warning("Failed to log audit action: %s", e)

            updated = db.leave_requests.find_one({"request_id": request_id})
            return serialize_doc(updated), None

        else:
            return None, "Access Denied: Only authorized Team Leads and Managers have permission to approve or reject leave requests."

    @classmethod
    def cancel_request(cls, employee: dict, request_id: str) -> tuple[bool, str | None]:
        """
        Employee or Team Lead cancels their own pending request.
        Preserves historical record with 'Cancelled' status.
        """
        db = get_db()
        req = db.leave_requests.find_one({"request_id": request_id})
        if not req:
            return False, f"Request '{request_id}' not found."

        if req.get("employee_id") != employee["employee_id"]:
            return False, "Access Denied: You can only cancel your own requests."

        curr_status = req.get("status", "")
        if curr_status not in ("Pending", "PENDING_TEAM_LEAD", "PENDING_MANAGER", "PENDING_AUTHORIZATION"):
            return False, f"Cannot cancel request with status '{curr_status}'. Only pending requests can be cancelled."

        db.leave_requests.update_one(
            {"request_id": request_id},
            {
                "$set": {
                    "status": "Cancelled",
                    "cancelled_at": now_utc(),
                    "updated_at": now_utc()
                }
            }
        )
        logger.info("Cancelled request '%s' by employee '%s'", request_id, employee["employee_id"])

        try:
            AuditService.log_action(
                actor=employee,
                action="CANCEL_LEAVE_REQUEST",
                target_type="leave_request",
                target_id=request_id,
                details={"request_type": req.get("request_type")}
            )
        except Exception as e:
            logger.warning("Failed to log cancel audit action: %s", str(e))

        return True, None

    @classmethod
    def delete_leave_request(cls, actor: dict, request_id: str) -> tuple[bool, str | None]:
        """HR or Admin deletes or purges an invalid leave request. If already approved, refunds debited days."""
        role = normalize_role(actor.get("role"))
        if role not in (Role.HR, Role.ADMIN):
            return False, "Access Denied: Only HR or Administrators can delete leave requests."

        db = get_db()
        req = db.leave_requests.find_one({"request_id": request_id})
        if not req:
            return False, f"Request '{request_id}' not found."

        # If it was approved, refund leave balance
        if req.get("status") in ("APPROVED", "Approved") and req.get("request_type") == "LEAVE":
            try:
                days = float(req.get("days_count", 1))
                ltype = cls.normalize_leave_type(req.get("leave_type", "Casual Leave"))
                fy = cls.get_financial_year(req.get("start_date"))
                emp_bal = cls.get_or_create_leave_balance(req["employee_id"], fy)
                bal_dict = emp_bal.get("balances", {}).get(ltype, {"total": 0.0, "used": 0.0, "available": 0.0})
                balance_before = float(bal_dict.get("available", 0.0))
                balance_after = balance_before + days
                used_after = max(0.0, float(bal_dict.get("used", 0.0)) - days)

                db.leave_balances.update_one(
                    {"employee_id": req["employee_id"], "financial_year": fy},
                    {
                        "$set": {
                            f"balances.{ltype}.used": used_after,
                            f"balances.{ltype}.available": balance_after,
                            "updated_at": now_utc()
                        }
                    }
                )

                txn_id = cls._get_next_transaction_id(db)
                db.leave_transactions.insert_one({
                    "transaction_id": txn_id,
                    "employee_id": req["employee_id"],
                    "financial_year": fy,
                    "leave_type": ltype,
                    "transaction_type": "CREDIT",
                    "days": days,
                    "balance_before": balance_before,
                    "balance_after": balance_after,
                    "reference_request_id": request_id,
                    "remarks": f"Leave balance refunded upon deletion by {actor.get('name', 'Admin')}",
                    "performed_by": actor["employee_id"],
                    "created_at": now_utc()
                })
            except Exception as e:
                logger.error("Error refunding leave on delete: %s", e)

        db.leave_requests.delete_one({"request_id": request_id})
        return True, None

    @classmethod
    def send_approval_email_to_hr(
        cls,
        sender: dict,
        request_id: str,
        to_email: str = None,
        subject: str = "",
        message: str = "",
        cc_email: str | None = None
    ) -> tuple[dict | None, str | None]:
        """
        Manual Email Composer action:
        After Manager approval, Manager can compose and forward approved leave details to HR.
        Reuses ExternalNotificationService, records action accurately in request history.
        Deduplicates repeated clicks to prevent duplicate emails and history records.
        """
        db = get_db()
        req = db.leave_requests.find_one({"request_id": request_id})
        if not req:
            return None, f"Leave request '{request_id}' not found."

        if req.get("status") not in ("Approved", "APPROVED"):
            return None, "Email notifications can only be sent for 'Approved' requests."

        sender_role = normalize_role(sender.get("role"))
        if sender_role not in (Role.MANAGER, Role.ADMIN):
            return None, "Unauthorized: Only Managers or Administrators can send leave approval notifications."
        sender_id = (sender.get("employee_id") or sender.get("emp_id") or "").strip().upper()
        if sender_role == Role.MANAGER:
            in_scope = (
                (req.get("assigned_manager_id") and str(req.get("assigned_manager_id")).strip().upper() == sender_id)
                or (req.get("reviewed_by_id") and str(req.get("reviewed_by_id")).strip().upper() == sender_id)
                or can_access_employee_record(sender, req.get("employee_id"))
            )
            if not in_scope:
                return None, "Access Denied: You can only send notifications for leave requests within your reporting scope."

        configured_hr_email = getattr(Config, "HR_EMAIL", "hr.ramya@aisamrat.com").strip()
        to_email = (to_email or configured_hr_email).strip()
        cc_email = (cc_email or "").strip() or None

        if not to_email or "@" not in to_email:
            return None, "A valid HR recipient email address is required."

        idempotency_key = f"LEAVE_HR_FWD_{request_id}"

        # Prevent duplicate forwards when Manager clicks multiple times
        existing_in_history = next((e for e in req.get("email_history", []) if e.get("idempotency_key") == idempotency_key), None)
        if existing_in_history:
            logger.info("Request '%s' already forwarded to HR with key '%s'", request_id, idempotency_key)
            return {
                "success": existing_in_history.get("status") in ("SENT", "SIMULATED"),
                "email_status": existing_in_history.get("status"),
                "message": existing_in_history.get("status_text") or "Approved leave details already forwarded to HR.",
                "record": existing_in_history,
                "already_forwarded": True
            }, None

        emp_name = req.get("employee_name", "Employee")
        emp_id = req.get("employee_id", "Unknown")
        req_type = req.get("request_type", "LEAVE")
        leave_type = req.get("leave_type") or req.get("permission_type") or "Casual Leave"
        start_date = req.get("start_date", req.get("permission_date", "N/A"))
        end_date = req.get("end_date", req.get("permission_date", req.get("early_exit_time", "N/A")))
        days_count = req.get("days_count", 1)
        reason = req.get("reason", "N/A")
        status = req.get("status", "APPROVED")
        mgr_name = sender.get("full_name") or sender.get("employee_id", "Manager")
        mgr_id = sender.get("employee_id", "")
        mgr_remarks = req.get("review_remarks") or "Approved"

        if not subject:
            subject = f"Approved Leave Request – {emp_name} – {request_id}"

        if not message:
            message = (
                f"Hello HR Department,\n\n"
                f"The following leave request has been approved by Manager {mgr_name} ({mgr_id}) and forwarded for official HR records:\n\n"
                f"• Leave Request ID: {request_id}\n"
                f"• Employee Name: {emp_name}\n"
                f"• Employee ID: {emp_id}\n"
                f"• Department: {req.get('department', 'N/A')}\n"
                f"• Request Type: {req_type}\n"
                f"• Leave Type: {leave_type}\n"
                f"• Start Date: {start_date}\n"
                f"• End Date: {end_date}\n"
                f"• Total Days: {days_count}\n"
                f"• Leave Reason: {reason}\n"
                f"• Approval Status: {status}\n"
                f"• Manager Remarks: {mgr_remarks}\n"
                f"• Approved By: {mgr_name} ({mgr_id})\n\n"
                f"Best regards,\n"
                f"{mgr_name}\n"
                f"Manager, AISamrat HRMS"
            )

        # Dispatch via ExternalNotificationService
        dispatch_res = ExternalNotificationService.send_email(
            recipient_email=to_email,
            subject=subject,
            body=message,
            recipient_id=emp_id,
            category="LEAVE_APPROVAL",
            idempotency_key=idempotency_key,
            cc_email=cc_email
        )

        provider_status = dispatch_res.get("status", "FAILED")
        if provider_status == "DELIVERED":
            email_status = "SENT"
            status_text = f"Email successfully sent to {to_email}"
        elif provider_status == "SIMULATED_NO_CREDENTIALS":
            email_status = "SIMULATED"
            status_text = f"Email simulated (no external SMTP configured). Logged for {to_email}"
        else:
            email_status = "FAILED"
            status_text = dispatch_res.get("failure_reason") or "Failed to deliver email"

        email_record = {
            "email_id": f"EML-{1001 + len(req.get('email_history', []))}",
            "idempotency_key": idempotency_key,
            "to": to_email,
            "cc": cc_email or "",
            "subject": subject,
            "message": message,
            "status": email_status,
            "provider_status": provider_status,
            "status_text": status_text,
            "sent_at": now_utc(),
            "sent_by_id": sender.get("employee_id"),
            "sent_by_name": mgr_name
        }

        db.leave_requests.update_one(
            {"request_id": request_id},
            {
                "$push": {"email_history": email_record},
                "$set": {"updated_at": now_utc(), "last_email_status": email_status}
            }
        )

        # Deposit into Inbuilt Corporate Mailbox for HR
        try:
            from services.enterprise_mailbox_service import EnterpriseMailboxService
            EnterpriseMailboxService.send_user_mail(
                actor=sender,
                data={
                    "recipient_email": to_email,
                    "subject": subject,
                    "category": "OFFICIAL_LETTER",
                    "content": message,
                    "is_confidential": False
                }
            )
        except Exception:
            pass

        try:
            AuditService.log_action(
                actor=sender,
                action="SEND_LEAVE_APPROVAL_EMAIL",
                target_type="leave_request",
                target_id=request_id,
                details={
                    "to": to_email,
                    "cc": cc_email,
                    "subject": subject,
                    "status": email_status,
                    "provider_status": provider_status
                }
            )
        except Exception as e:
            logger.warning("Failed to log email audit action: %s", str(e))

        is_success = email_status in ("SENT", "SIMULATED")
        return {
            "success": is_success,
            "email_status": email_status,
            "message": status_text,
            "record": email_record
        }, None if is_success else status_text

    @classmethod
    def get_leave_correspondence_for_hr(cls) -> list[dict]:
        """
        Retrieves forwarded leave approval correspondence records for HR portal.
        HR can view forwarded notifications without approval authority.
        """
        db = get_db()
        cursor = db.leave_requests.find(
            {"email_history": {"$exists": True, "$ne": []}},
            {
                "request_id": 1,
                "request_type": 1,
                "employee_id": 1,
                "employee_name": 1,
                "department": 1,
                "leave_type": 1,
                "permission_type": 1,
                "start_date": 1,
                "end_date": 1,
                "permission_date": 1,
                "early_exit_time": 1,
                "status": 1,
                "email_history": 1
            }
        ).sort("updated_at", -1)

        correspondence_list = []
        for req in cursor:
            for eml in req.get("email_history", []):
                correspondence_list.append({
                    "email_id": eml.get("email_id"),
                    "request_id": req.get("request_id"),
                    "request_type": req.get("request_type"),
                    "employee_id": req.get("employee_id"),
                    "employee_name": req.get("employee_name"),
                    "department": req.get("department"),
                    "dates": f"{req.get('start_date', req.get('permission_date'))} to {req.get('end_date', req.get('early_exit_time'))}",
                    "sender_name": eml.get("sent_by_name"),
                    "sender_id": eml.get("sent_by_id"),
                    "recipient": eml.get("to"),
                    "cc": eml.get("cc", ""),
                    "subject": eml.get("subject"),
                    "message": eml.get("message"),
                    "status": eml.get("status"),
                    "provider_status": eml.get("provider_status"),
                    "status_text": eml.get("status_text"),
                    "sent_at": eml.get("sent_at")
                })

        correspondence_list.sort(key=lambda x: str(x.get("sent_at") or ""), reverse=True)
        return serialize_docs(correspondence_list)
