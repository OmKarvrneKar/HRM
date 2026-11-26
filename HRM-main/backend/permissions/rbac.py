from functools import wraps
from flask import request, jsonify, redirect, url_for, render_template
from bson import ObjectId
from backend.auth.security import decode_jwt_token
from backend.database.connection import get_db
from backend.utils.serializers import serialize_doc
from config import Config


class Role:
    EMPLOYEE = "employee"
    TEAM_LEAD = "team_lead"
    TL = "tl"
    MANAGER = "manager"
    HR = "hr"
    ADMIN = "admin"

    CANONICAL_ROLES = ["employee", "tl", "manager", "hr", "admin"]
    ALL_ROLES = [EMPLOYEE, TEAM_LEAD, TL, MANAGER, HR, ADMIN]

    # Legacy aliases (deprecated, preserved for database migration compatibility)
    HR_MANAGER = "hr"
    ORGANIZATION = "manager"
    TRAINER = "team_lead"


ROLE_LABELS = {
    Role.EMPLOYEE: "Employee",
    Role.TL: "Team Lead",
    Role.TEAM_LEAD: "Team Lead",
    Role.MANAGER: "Manager",
    Role.HR: "Human Resources",
    Role.ADMIN: "Administrator"
}


def normalize_role(role_val: str | None) -> str:
    """Normalizes any role alias to one of the 5 canonical roles: employee, tl, manager, hr, admin."""
    if not role_val:
        return Role.EMPLOYEE
    r = str(role_val).strip().lower()
    if r in ("admin", "superadmin", "administrator"):
        return Role.ADMIN
    if r in ("hr", "hr_manager", "human_resources"):
        return Role.HR
    if r in ("manager", "mgr", "organization"):
        return Role.MANAGER
    if r in ("tl", "team_lead", "trainer"):
        return Role.TL
    return Role.EMPLOYEE


def is_intern(user_or_id) -> bool:
    """Identifies whether an account is an intern (AS-1001 through AS-1034 or intern designation)."""
    if not user_or_id:
        return False
    emp_id = user_or_id.get("emp_id") or user_or_id.get("employee_id") if isinstance(user_or_id, dict) else str(user_or_id)
    if not emp_id:
        return False
    emp_id = emp_id.strip().upper()
    if emp_id.startswith("AS-"):
        return True
    if isinstance(user_or_id, dict):
        desig = (user_or_id.get("designation") or "").lower()
        if "intern" in desig:
            return True
    return False


def can_access_employee_record(current_user: dict, target_employee_id: str) -> bool:
    """
    Enforces strict self-service isolation for interns, while TLs and Managers
    inherit hierarchical review queues:
    - Interns (AS-1001 to AS-1034) & standard employees: can access ONLY self records.
    - Team Leads (TL-1001 to TL-1008): access self + assigned squad members.
    - Managers (MGR-1001 to MGR-1004): access self + department members + reporting lines.
    - HR & Admin: company-wide organizational access.
    """
    if not current_user or not target_employee_id:
        return False

    actor_id = (current_user.get("emp_id") or current_user.get("employee_id") or "").strip().upper()
    target_id = str(target_employee_id).strip().upper()

    if actor_id == target_id:
        return True

    # Interns and regular employees are strictly quarantined to self records
    if is_intern(current_user) or normalize_role(current_user.get("role")) == Role.EMPLOYEE:
        return False

    actor_role = normalize_role(current_user.get("role"))

    # HR & Admin have full organization-wide visibility
    if actor_role in (Role.HR, Role.ADMIN):
        return True

    db = get_db()
    target_user = db.users.find_one({"$or": [{"emp_id": target_id}, {"employee_id": target_id}]})
    if not target_user:
        return False

    # Team Lead: access members assigned to them or in their team squads
    if actor_role == Role.TL:
        if target_user.get("assigned_tl_id") == actor_id or target_user.get("team_lead_id") == actor_id:
            return True
        actor_team = current_user.get("team_id")
        target_team = target_user.get("team_id")
        if actor_team and target_team and actor_team == target_team:
            return True
        lead_teams = [t["team_id"] for t in db.teams.find({"$or": [{"lead_employee_id": actor_id}, {"lead_id": actor_id}]}, {"team_id": 1})]
        if target_team and target_team in lead_teams:
            return True
        return False

    # Manager: access employees within authorized department or reporting subordinates
    if actor_role == Role.MANAGER:
        if target_user.get("manager_id") == actor_id or target_user.get("reporting_manager_id") == actor_id:
            return True
        actor_dept = current_user.get("department")
        target_dept = target_user.get("department")
        if actor_dept and target_dept and actor_dept == target_dept and actor_dept not in ("Management", "Executive"):
            return True
        return False

    return False


ROLE_PERMISSIONS = {
    Role.EMPLOYEE: {
        "view_assigned_projects": True,
        "clock_in_out": True,
        "view_own_attendance": True,
        "apply_leave": True,
        "view_own_salary": True,
        "file_complaint": True,
        "use_chat": True,
        "view_announcements": True,
        "view_directory": True,
        "view_all_projects": False,
        "manage_projects": False,
        "view_team_attendance": False,
        "approve_leaves": False,
        "view_all_salaries": False,
        "manage_payroll": False,
        "manage_bank_details": False,
        "view_all_complaints": False,
        "manage_roles": False,
        "manage_hiring": False,
        "manage_offboarding": False,
        "admin_attendance": False,
        "view_admin_analytics": False
    },
    Role.TEAM_LEAD: {
        "view_assigned_projects": True,
        "clock_in_out": True,
        "view_own_attendance": True,
        "apply_leave": True,
        "view_own_salary": True,
        "file_complaint": True,
        "use_chat": True,
        "view_announcements": True,
        "view_directory": True,
        "view_all_projects": False,
        "manage_team_projects": True,
        "create_projects": True,
        "assign_tasks": True,
        "view_team_attendance": True,
        "approve_team_leaves": True,
        "approve_leaves": True,
        "view_all_salaries": False,  # Strict: Team Lead cannot access salaries/bank details
        "manage_payroll": False,
        "manage_bank_details": False,
        "view_all_complaints": False,  # Strict: Team Lead cannot access confidential HR complaints
        "manage_roles": False,
        "manage_hiring": False,
        "manage_offboarding": False,
        "admin_attendance": False,
        "view_admin_analytics": False
    },
    Role.MANAGER: {
        "view_assigned_projects": True,
        "clock_in_out": True,
        "view_own_attendance": True,
        "apply_leave": True,
        "view_own_salary": True,
        "file_complaint": True,
        "use_chat": True,
        "view_announcements": True,
        "view_directory": True,
        "view_all_projects": True,
        "manage_projects": True,
        "create_projects": True,
        "create_teams": True,
        "assign_tasks": True,
        "view_operational_attendance": True,
        "view_team_attendance": True,
        "approve_leaves": True,
        "view_all_salaries": False,  # Strict: Manager cannot access salaries/bank details
        "manage_payroll": False,
        "manage_bank_details": False,
        "view_all_complaints": False,  # Strict: Manager cannot access confidential HR complaints
        "manage_roles": False,
        "manage_hiring": False,
        "manage_offboarding": False,
        "admin_attendance": False,
        "view_admin_analytics": True,
        "manage_system_settings": True,
        "review_audit_logs": True
    },
    Role.HR: {
        "view_assigned_projects": False,  # Strict: HR does not access project management
        "view_all_projects": False,       # Strict: HR does not access project management
        "manage_projects": False,         # Strict: HR does not access project management
        "create_projects": False,
        "assign_tasks": False,
        "clock_in_out": True,
        "view_own_attendance": True,
        "apply_leave": True,
        "view_own_salary": True,
        "file_complaint": True,
        "use_chat": True,
        "view_announcements": True,
        "view_directory": True,
        "manage_hiring": True,
        "manage_profiles": True,
        "view_all_salaries": True,
        "manage_payroll": True,
        "manage_bank_details": True,
        "manage_offboarding": True,
        "admin_attendance": True,
        "process_leaves": True,
        "approve_leaves": True,
        "view_all_complaints": True,
        "manage_roles": True,
        "review_audit_logs": True,
        "view_admin_analytics": False
    },
    Role.ADMIN: {
        "view_assigned_projects": False, # Strict Isolation: Admin & HR have zero access to projects/codebases
        "clock_in_out": True,
        "view_own_attendance": True,
        "apply_leave": True,
        "view_own_salary": True,
        "file_complaint": True,
        "use_chat": True,
        "view_announcements": True,
        "view_directory": True,
        "view_all_projects": False,      # Strict Isolation: Admin & HR have zero access to projects/codebases
        "manage_projects": False,        # Strict Isolation: Admin & HR have zero access to projects/codebases
        "create_projects": False,        # Strict Isolation: Admin & HR have zero access to projects/codebases
        "create_teams": True,
        "assign_tasks": False,           # Strict Isolation: Admin & HR have zero access to projects/codebases
        "view_operational_attendance": True,
        "view_team_attendance": True,
        "approve_leaves": True,
        "view_all_salaries": True,
        "manage_payroll": True,
        "manage_bank_details": True,
        "view_all_complaints": False,
        "manage_roles": True,
        "manage_hiring": True,
        "manage_offboarding": True,
        "admin_attendance": True,
        "view_admin_analytics": True,
        "manage_system_settings": True,
        "review_audit_logs": True
    }
}
ROLE_PERMISSIONS["tl"] = ROLE_PERMISSIONS[Role.TEAM_LEAD]


def get_token_from_request() -> str | None:
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:].strip()
    return request.cookies.get(Config.JWT_COOKIE_NAME)


def require_auth(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        token = get_token_from_request()
        user = None
        db = get_db()

        if token:
            payload = decode_jwt_token(token)
            if payload and payload.get("user_id"):
                try:
                    user = db.users.find_one({"_id": ObjectId(payload["user_id"])})
                except Exception:
                    user = None

        if not user:
            # Check Flask session variables fallback
            from flask import session
            session_uid = session.get("user_id")
            session_emp = session.get("emp_id")
            if session_uid:
                try:
                    user = db.users.find_one({"_id": ObjectId(session_uid)})
                except Exception:
                    user = None
            if not user and session_emp:
                try:
                    user = db.users.find_one({
                        "$or": [
                            {"emp_id": session_emp},
                            {"employee_id": session_emp}
                        ]
                    })
                except Exception:
                    user = None

            if not user and session_uid and session.get("role"):
                user = {
                    "emp_id": session_emp or session_uid,
                    "employee_id": session_emp or session_uid,
                    "name": session.get("name") or "Test User",
                    "role": str(session.get("role")).lower(),
                    "is_active": True,
                    "status": "active"
                }

        if not user:
            if request.path.startswith("/api/"):
                return jsonify({"error": "Authentication required. Please log in."}), 401
            resp = redirect(url_for("page_views.login_page", next=request.path))
            resp.delete_cookie(Config.JWT_COOKIE_NAME)
            return resp

        if not user.get("is_active", True) or user.get("status") in ("deactivated", "offboarded"):
            if request.path.startswith("/api/"):
                return jsonify({"error": "Account has been deactivated or offboarded. Contact administration."}), 403
            resp = redirect(url_for("page_views.login_page"))
            resp.delete_cookie(Config.JWT_COOKIE_NAME)
            return resp

        # Synchronize session role with database record to prevent session tampering
        from flask import session
        db_role = user.get("role")
        if "role" in session and session.get("role") != db_role:
            session["role"] = db_role

        request.current_user = user
        request.user_role = normalize_role(db_role)
        request.is_intern = is_intern(user)
        return f(*args, **kwargs)

    return decorated_function


def require_roles(*allowed_roles):
    """
    Decorator enforcing that current_user has one of the allowed business roles.
    Strictly isolates interns to employee self-service records while mapping
    canonical roles (employee, tl, manager, hr, admin) cleanly.
    """
    def decorator(f):
        @wraps(f)
        @require_auth
        def decorated_function(*args, **kwargs):
            user = request.current_user
            raw_role = str(user.get("role") or "").lower()
            canonical_user_role = normalize_role(raw_role)

            canonical_allowed = set()
            raw_allowed = set()
            for r in allowed_roles:
                norm_r = normalize_role(r)
                canonical_allowed.add(norm_r)
                raw_allowed.add(str(r).lower())
                if norm_r == Role.TL:
                    raw_allowed.update(["tl", "team_lead", "trainer"])
                elif norm_r == Role.HR:
                    raw_allowed.update(["hr", "hr_manager"])
                elif norm_r == Role.MANAGER:
                    raw_allowed.update(["manager", "organization", "mgr"])
                elif norm_r == Role.ADMIN:
                    raw_allowed.update(["admin", "superadmin"])
                elif norm_r == Role.EMPLOYEE:
                    raw_allowed.update(["employee"])

            # Interns can NEVER act as tl, manager, hr, or admin
            if is_intern(user) and Role.EMPLOYEE not in canonical_allowed and "employee" not in raw_allowed:
                if request.path.startswith("/api/"):
                    return jsonify({
                        "error": "Access Denied: Intern accounts are restricted to self-service employee access only.",
                        "required_roles": list(allowed_roles),
                        "user_role": canonical_user_role
                    }), 403
                return render_template(
                    "errors/403.html",
                    user=serialize_doc(user),
                    required_roles=list(allowed_roles),
                    user_role=canonical_user_role
                ), 403

            has_access = (canonical_user_role in canonical_allowed) or (raw_role in raw_allowed)

            if not has_access:
                if request.path.startswith("/api/"):
                    return jsonify({
                        "error": "Access Denied: You do not have the required role to access this resource.",
                        "required_roles": list(allowed_roles),
                        "user_role": canonical_user_role
                    }), 403

                return render_template(
                    "errors/403.html",
                    user=serialize_doc(user),
                    required_roles=list(allowed_roles),
                    user_role=canonical_user_role
                ), 403

            return f(*args, **kwargs)

        return decorated_function

    return decorator


def can_view_attendance(current_user: dict, target_employee_id: str, target_user: dict = None) -> bool:
    if not current_user or not target_employee_id:
        return False

    own_id = current_user.get("emp_id") or current_user.get("employee_id")
    if target_employee_id == own_id:
        return True

    # Interns and normal employees can NEVER view other employees' attendance
    if is_intern(current_user) or normalize_role(current_user.get("role")) == Role.EMPLOYEE:
        return False

    return can_access_employee_record(current_user, target_employee_id)


def can_view_profile(current_user: dict, target_user: dict) -> bool:
    if not target_user:
        return False

    current_id = (current_user.get("employee_id") or current_user.get("emp_id") or "").strip().upper()
    target_id = (target_user.get("employee_id") or target_user.get("emp_id") or "").strip().upper()

    # Own profile is always accessible
    if current_id and target_id and current_id == target_id:
        return True

    role = normalize_role(current_user.get("role"))
    target_role = normalize_role(target_user.get("role"))

    # HR and Admin have organization-wide staff oversight
    if role in (Role.HR, Role.ADMIN, "hr_manager"):
        return True

    # Team Lead: Can view ONLY active normal Employees assigned to that Team Lead's squad/team
    if role in (Role.TEAM_LEAD, Role.TL, "trainer"):
        if target_role != Role.EMPLOYEE:
            return False
        if not target_user.get("is_active", True):
            return False
        return can_access_employee_record(current_user, target_id)

    # Manager: Can view ONLY active normal Employees within Manager's authorized scope
    if role in (Role.MANAGER, "organization"):
        if target_role != Role.EMPLOYEE:
            return False
        if not target_user.get("is_active", True):
            return False
        return can_access_employee_record(current_user, target_id)

    # Normal Employee: strictly restricted to own profile (zero colleague cycling/switching)
    if role == Role.EMPLOYEE:
        return False

    return False


def can_edit_profile(current_user: dict, target_user: dict) -> bool:
    """
    Enforces profile edit boundaries:
    - User can edit their own allowed profile fields (e.g., self-service).
    - HR / Admin can edit employee profile information.
    - Team Leads and Managers CANNOT edit employee profiles.
    """
    if not current_user or not target_user:
        return False
    current_id = (current_user.get("employee_id") or current_user.get("emp_id") or "").strip().upper()
    target_id = (target_user.get("employee_id") or target_user.get("emp_id") or "").strip().upper()
    role = normalize_role(current_user.get("role"))

    # Own profile self-editing
    if current_id and target_id and current_id == target_id:
        return True

    # HR and system administrators manage employee profile records
    if role in (Role.HR, Role.ADMIN):
        return True

    # Team Leads and Managers are strictly forbidden from editing employee profiles
    return False


def can_access_complaint(current_user: dict, complaint: dict) -> bool:
    if not current_user or not complaint:
        return False

    user_id = (current_user.get("employee_id") or current_user.get("emp_id") or "").strip().upper()
    complainant_id = (complaint.get("complainant_id") or "").strip().upper()
    role = normalize_role(current_user.get("role"))

    if user_id and complainant_id and complainant_id == user_id:
        return True

    # HR handles confidential employee complaints exclusively
    if role == Role.HR:
        return True

    # Team Leads and Managers are strictly forbidden from confidential HR complaints
    return False


def can_manage_projects(current_user: dict) -> bool:
    if not current_user:
        return False
    role = normalize_role(current_user.get("role"))
    # HR is strictly excluded from project management
    if role == Role.HR:
        return False
    return role in (Role.MANAGER, Role.TL, Role.ADMIN)


def can_view_projects(current_user: dict) -> bool:
    if not current_user:
        return False
    role = normalize_role(current_user.get("role"))
    # HR is strictly restricted from project pages & APIs
    if role == Role.HR:
        return False
    return True


def can_view_salary(current_user: dict, target_user_or_id) -> bool:
    if not current_user or target_user_or_id is None:
        return False
    target_id = (
        target_user_or_id.get("employee_id") or target_user_or_id.get("emp_id")
        if isinstance(target_user_or_id, dict)
        else str(target_user_or_id)
    )
    own_id = current_user.get("employee_id") or current_user.get("emp_id")
    if own_id and target_id and str(own_id).strip().upper() == str(target_id).strip().upper():
        return True
    role = normalize_role(current_user.get("role"))
    # Only HR and Admin have access to other employees' salary, payroll, and compensation records
    return role in (Role.HR, Role.ADMIN)


def can_manage_roles(current_user: dict) -> bool:
    if not current_user:
        return False
    # Role provisioning is restricted to authorized HR and System Administrators
    return normalize_role(current_user.get("role")) in (Role.HR, Role.ADMIN)


def can_create_account(current_user: dict, target_role: str) -> bool:
    if not current_user:
        return False
    role = normalize_role(current_user.get("role"))
    if role not in (Role.HR, Role.ADMIN):
        return False
    if normalize_role(target_role) == Role.ADMIN and role != Role.ADMIN:
        return False
    return target_role in Role.ALL_ROLES or target_role in ["employee", "team_lead", "manager", "hr"]


def can_approve_leave(current_user: dict, leave_request: dict) -> bool:
    if not leave_request or not current_user:
        return False

    applicant_id = leave_request.get("emp_id") or leave_request.get("employee_id")
    current_id = current_user.get("emp_id") or current_user.get("employee_id")

    # Strictly prevent unauthorized self-approval
    if applicant_id and current_id and str(applicant_id).strip().upper() == str(current_id).strip().upper():
        return False

    # Interns and standard employees can NEVER approve leaves
    if is_intern(current_user) or normalize_role(current_user.get("role")) == Role.EMPLOYEE:
        return False

    role = normalize_role(current_user.get("role"))
    applicant_role = normalize_role(leave_request.get("applicant_role") or leave_request.get("role"))

    # HR is strictly excluded from technical leave approval workflow
    if role == Role.HR or applicant_role == Role.HR:
        return False

    status = (leave_request.get("status") or "").upper()

    # Team Lead stage: can review and approve PENDING_TEAM_LEAD for their assigned squad members
    if role == Role.TL:
        if status not in ("PENDING_TEAM_LEAD", "PENDING"):
            return False
        return can_access_employee_record(current_user, applicant_id)

    # Manager stage: can provide final approval for PENDING_MANAGER (or direct requests)
    if role in (Role.MANAGER, Role.ADMIN):
        if status in ("PENDING_MANAGER", "TL_APPROVED", "PENDING", "APPROVED", "REJECTED"):
            return can_access_employee_record(current_user, applicant_id)

    return False
