from flask import Blueprint, render_template, redirect, url_for, request, make_response, jsonify, flash
from bson import ObjectId
from config import Config
from backend.permissions.rbac import (
    require_auth,
    require_roles,
    Role,
    get_token_from_request,
    can_view_profile,
    normalize_role
)
from backend.auth.security import decode_jwt_token
from backend.database.connection import get_db
from backend.services.otp_service import OtpService
from backend.utils.serializers import serialize_doc, serialize_docs
from backend.utils.timezone import get_local_date_str

page_bp = Blueprint("page_views", __name__)


def get_current_user_from_cookie():
    """Validates token and ensures user account actually exists and is active in DB."""
    token = get_token_from_request()
    if not token:
        return None
    payload = decode_jwt_token(token)
    if not payload or not payload.get("user_id"):
        return None
    db = get_db()
    try:
        user = db.users.find_one({"_id": ObjectId(payload["user_id"])})
        if user and user.get("is_active", True):
            return user
    except Exception:
        pass
    return None


@page_bp.route("/")
def index():
    user = get_current_user_from_cookie()
    if user:
        role = (user.get("role") or "").lower()
        if role in (Role.ADMIN, "admin"):
            return redirect(url_for("page_views.admin_dashboard"))
        elif role in (Role.MANAGER, "manager"):
            return redirect(url_for("page_views.manager_dashboard"))
        elif role in (Role.HR, "hr"):
            return redirect(url_for("page_views.hr_dashboard"))
        elif role in (Role.TEAM_LEAD, "team_lead", "tl"):
            return redirect(url_for("page_views.team_lead_dashboard"))
        else:
            return redirect(url_for("page_views.employee_dashboard"))

    # If no valid active session, clear any stale cookie and go to login
    resp = redirect(url_for("page_views.login_page"))
    if get_token_from_request():
        resp.delete_cookie(Config.JWT_COOKIE_NAME)
    return resp


@page_bp.route("/login", methods=["GET", "POST"])
def login_page():
    if request.method == "POST":
        from backend.routes.auth_routes import login as api_login
        res = api_login()
        if request.headers.get("Accept") == "application/json" or request.is_json:
            return res
        response_obj = res[0] if isinstance(res, tuple) else res
        if hasattr(response_obj, "get_json") and response_obj.get_json():
            data = response_obj.get_json()
            if data.get("success") and data.get("redirect_url"):
                redirect_resp = redirect(data["redirect_url"])
                for cookie in response_obj.headers.getlist("Set-Cookie"):
                    redirect_resp.headers.add("Set-Cookie", cookie)
                return redirect_resp
            else:
                flash(data.get("error", "Invalid Employee ID or password."), "danger")
                return render_template("auth/login.html", error=data.get("error", "Authentication failed.")), 200
        return res

    user = get_current_user_from_cookie()
    if user and request.args.get("logged_out") != "1" and request.args.get("logout") != "1":
        return redirect(url_for("page_views.index"))

    generated_otp = request.args.get("otp") or (OtpService.get_debug_otp() if Config.is_development() else None)
    resp = make_response(render_template("auth/login.html", generated_otp=generated_otp))
    for p in ("/", "/api", "/api/auth"):
        resp.delete_cookie(Config.JWT_COOKIE_NAME, path=p)
        resp.delete_cookie("session", path=p)
        resp.set_cookie(Config.JWT_COOKIE_NAME, "", expires=0, max_age=0, path=p)
        resp.set_cookie("session", "", expires=0, max_age=0, path=p)
    return resp


@page_bp.route("/activate", endpoint="activate_page")
@page_bp.route("/activate-account")
@page_bp.route("/first-time-setup")
def activate_page():
    prefill_emp_id = request.args.get("emp_id") or request.args.get("employee_id") or ""
    generated_otp = request.args.get("otp") or request.args.get("generated_otp") or (OtpService.get_debug_otp() if Config.is_development() else None)
    return render_template("auth/activate.html", prefill_emp_id=prefill_emp_id, emp_id=prefill_emp_id, generated_otp=generated_otp)


@page_bp.route('/generate-otp', methods=['POST', 'GET'])
def generate_otp_bp():
    from flask import flash, redirect, url_for
    import random
    import re
    from datetime import datetime, timezone, timedelta
    emp_id = (request.form.get('emp_id') or request.args.get('emp_id') or "").strip()
    if not emp_id and request.is_json:
        data = request.get_json(silent=True) or {}
        emp_id = (data.get('emp_id') or data.get('employee_id') or "").strip()

    active_db = get_db()
    user = None
    if emp_id:
        user = active_db.users.find_one({
            "$or": [
                {"emp_id": re.compile(f"^{re.escape(emp_id)}$", re.IGNORECASE)},
                {"employee_id": re.compile(f"^{re.escape(emp_id)}$", re.IGNORECASE)}
            ]
        })

    if user:
        auto_otp = str(random.randint(100000, 999999))
        actual_emp_id = user.get("emp_id") or user.get("employee_id") or emp_id

        active_db.users.update_one(
            {"_id": user["_id"]},
            {"$set": {"activation_otp": auto_otp, "emp_id": actual_emp_id}}
        )

        try:
            from backend.services.otp_service import OtpService, OtpPurpose
            user_email = user.get("personal_email") or user.get("email") or ""
            if user_email:
                OtpService._dev_latest_otps[f"{user_email}:{OtpPurpose.ACTIVATION}"] = {
                    "otp": auto_otp,
                    "expires_at": datetime.now(timezone.utc) + timedelta(minutes=15)
                }
            OtpService._last_generated_otp = auto_otp
        except Exception as e:
            pass

        if request.is_json or request.headers.get("Accept") == "application/json":
            return jsonify({
                "success": True,
                "generated_otp": auto_otp,
                "emp_id": actual_emp_id,
                "message": f"OTP {auto_otp} generated successfully for {actual_emp_id}."
            }), 200

        return render_template('activate_account.html', generated_otp=auto_otp, emp_id=actual_emp_id)

    flash('Employee ID not found', 'danger')
    return redirect(url_for('page_views.activate_page', emp_id=emp_id))


@page_bp.route("/logout", methods=["GET", "POST"])
def logout_view():
    from flask import session
    session.clear()
    session.pop("user_id", None)
    session.pop("role", None)
    session.pop("emp_id", None)
    request.current_user = None

    resp = redirect("/login")
    for p in ("/", "/api", "/api/auth"):
        resp.delete_cookie(Config.JWT_COOKIE_NAME, path=p)
        resp.delete_cookie("session", path=p)
        resp.set_cookie(Config.JWT_COOKIE_NAME, "", expires=0, max_age=0, path=p)
        resp.set_cookie("session", "", expires=0, max_age=0, path=p)
    return resp


@page_bp.route("/dashboard/employee")
@require_auth
def employee_dashboard():
    return render_template(
        "dashboards/employee_dashboard.html",
        user=serialize_doc(request.current_user),
        today_date=get_local_date_str()
    )


@page_bp.route("/dashboard/hr")
@require_roles(Role.HR)
def hr_dashboard():
    return render_template(
        "dashboards/hr_dashboard.html",
        user=serialize_doc(request.current_user),
        today_date=get_local_date_str()
    )


@page_bp.route("/dashboard/admin")
@page_bp.route("/admin/dashboard")
@require_roles(Role.ADMIN)
def admin_dashboard():
    return render_template(
        "dashboards/admin_dashboard.html",
        user=serialize_doc(request.current_user),
        today_date=get_local_date_str()
    )


@page_bp.route("/dashboard/manager")
@page_bp.route("/dashboard/hr-manager")
@page_bp.route("/dashboard/organization")
@require_roles(Role.MANAGER)
def manager_dashboard():
    return render_template(
        "dashboards/manager_dashboard.html",
        user=serialize_doc(request.current_user),
        today_date=get_local_date_str()
    )


@page_bp.route("/dashboard/team-lead")
@page_bp.route("/dashboard/team_lead")
@page_bp.route("/dashboard/teamlead")
@page_bp.route("/dashboard/trainer")
@require_roles(Role.TEAM_LEAD)
def team_lead_dashboard():
    user = request.current_user
    team_id = user.get("team_id", "")
    lead_id = user.get("employee_id", "")
    from backend.services.skill_service import SkillService
    db = get_db()

    team_matrix = SkillService.get_team_skill_matrix(team_id) if team_id else {
        "members": [], "category_coverage": {}, "skill_gaps": [], "total_members": 0, "has_pending_assignment": True
    }

    # Active deliverables / projects assigned to or created by this Team Lead
    project_query = {
        "$or": [
            {"created_by": lead_id},
            {"manager_employee_id": lead_id},
            {"members": lead_id},
            {"team_id": team_id}
        ],
        "status": {"$ne": "Archived"}
    }
    active_projects_count = db.projects.count_documents(project_query)
    assigned_projects = list(db.projects.find(project_query).sort("created_at", -1))

    # Count pending leaves awaiting Team Lead review from assigned team members
    member_ids = [m["employee_id"] for m in team_matrix.get("members", [])]
    or_clauses = [{"assigned_tl_id": lead_id}]
    if member_ids:
        or_clauses.append({"employee_id": {"$in": member_ids}})
    if team_id:
        or_clauses.append({"team_id": team_id})
    pending_leaves_count = db.leave_requests.count_documents({
        "$or": or_clauses,
        "employee_id": {"$ne": lead_id},
        "status": {"$in": ["PENDING_TEAM_LEAD", "Pending"]}
    })

    return render_template(
        "dashboards/team_lead_dashboard.html",
        user=serialize_doc(user),
        team_matrix=team_matrix,
        active_projects_count=active_projects_count,
        assigned_projects=serialize_docs(assigned_projects),
        pending_leaves_count=pending_leaves_count,
        today_date=get_local_date_str()
    )


@page_bp.route("/skills")
@require_auth
def skill_matrix_page():
    user = request.current_user
    if user.get("role") == Role.HR:
        return redirect(url_for("page_views.hr_dashboard"))
    target_emp_id = request.args.get("employee") or user.get("employee_id")
    return redirect(url_for("page_views.view_profile_page", employee_id=target_emp_id))


@page_bp.route("/attendance")
@require_auth
def attendance_page():
    role = normalize_role(request.current_user.get("role"))
    if role == Role.HR:
        template = "attendance/hr_attendance.html"
    elif role in (Role.TL, Role.MANAGER):
        template = "attendance/team_attendance.html"
    else:
        template = "attendance/employee_attendance.html"

    tab = request.args.get("tab", "oversight")
    return render_template(
        template,
        user=serialize_doc(request.current_user),
        today_date=get_local_date_str(),
        active_tab=tab
    )


@page_bp.route("/profiles")
@require_auth
def profiles_page():
    role = normalize_role(request.current_user.get("role"))
    if role in (Role.HR, Role.ADMIN):
        template = "profiles/hr_management.html"
    elif role in (Role.TL, Role.MANAGER):
        template = "profiles/team_directory.html"
    else:
        return redirect(url_for("page_views.view_profile_page", employee_id=request.current_user.get("employee_id")))

    return render_template(
        template,
        user=serialize_doc(request.current_user)
    )


@page_bp.route("/profile")
@page_bp.route("/my-profile")
@require_auth
def my_profile_page():
    emp_id = request.current_user.get("employee_id") or request.current_user.get("emp_id")
    return redirect(url_for("page_views.view_profile_page", employee_id=emp_id))


@page_bp.route("/profile/<employee_id>")
@page_bp.route("/profiles/<employee_id>")
@page_bp.route("/profiles/view/<employee_id>")
@require_auth
def view_profile_page(employee_id):
    db = get_db()
    target_user = db.users.find_one({"$or": [{"employee_id": employee_id}, {"emp_id": employee_id}]})
    if not target_user:
        return render_template("errors/404.html", user=serialize_doc(request.current_user)), 404

    if not can_view_profile(request.current_user, target_user):
        return render_template(
            "errors/403.html",
            user=serialize_doc(request.current_user),
            required_roles=[Role.HR],
            user_role=request.current_user.get("role")
        ), 403

    current_emp_id = request.current_user.get("employee_id") or request.current_user.get("emp_id")
    target_emp_id = target_user.get("employee_id") or target_user.get("emp_id")
    is_self = bool(current_emp_id and target_emp_id and current_emp_id == target_emp_id)

    from backend.services.user_service import UserService
    enriched_target = UserService.enrich_user_profile(target_user)

    return render_template(
        "profiles/view_profile.html",
        user=serialize_doc(request.current_user),
        target_employee_id=target_emp_id,
        target_user=serialize_doc(enriched_target),
        is_self=is_self
    )


@page_bp.route("/projects")
@require_auth
def projects_page():
    user = request.current_user
    # HR & Admin Isolation Constraint: ZERO access to project codebases, tasks, or projects
    if user.get("role") in (Role.HR, Role.ADMIN):
        return render_template(
            "errors/403.html",
            user=serialize_doc(user),
            required_roles=[Role.EMPLOYEE, Role.TEAM_LEAD, Role.MANAGER],
            user_role=user.get("role")
        ), 403
    return render_template(
        "projects/project_list.html",
        user=serialize_doc(request.current_user)
    )


@page_bp.route("/projects/<project_id>")
@require_auth
def project_detail_page(project_id):
    user = request.current_user
    if user.get("role") == Role.HR:
        return render_template(
            "errors/403.html",
            user=serialize_doc(user),
            required_roles=[Role.EMPLOYEE, Role.TEAM_LEAD, Role.MANAGER],
            user_role=user.get("role")
        ), 403
    return render_template(
        "projects/project_detail.html",
        user=serialize_doc(request.current_user),
        project_id=project_id
    )


@page_bp.route("/complaints")
@require_auth
def complaints_page():
    return render_template(
        "complaints/complaint_list.html",
        user=serialize_doc(request.current_user)
    )


@page_bp.route("/complaints/<complaint_id>")
@require_auth
def complaint_detail_page(complaint_id):
    db = get_db()
    complaint = db.complaints.find_one({"complaint_id": complaint_id})
    if not complaint:
        return render_template(
            "errors/403.html",
            user=serialize_doc(request.current_user),
            required_roles=["Authorized Participant"],
            user_role=request.current_user.get("role")
        ), 404

    from backend.permissions.rbac import can_access_complaint
    if not can_access_complaint(request.current_user, complaint):
        return render_template(
            "errors/403.html",
            user=serialize_doc(request.current_user),
            required_roles=[Role.HR],
            user_role=request.current_user.get("role")
        ), 403

    return render_template(
        "complaints/complaint_detail.html",
        user=serialize_doc(request.current_user),
        complaint_id=complaint_id
    )


@page_bp.route("/communication")
@page_bp.route("/inbox")
@page_bp.route("/mailbox")
@require_auth
def unified_communication_page():
    path = request.path
    tab = (request.args.get("tab") or "").strip().lower()
    if not tab:
        if path == "/mailbox":
            tab = "mail"
        else:
            tab = "chat"

    project_id = request.args.get("project_id", "").strip()
    conversation_id = (request.args.get("conversation_id") or request.args.get("conversation", "")).strip()
    if not conversation_id and project_id:
        conversation_id = f"PRJ-CHAT-{project_id}"

    return render_template(
        "communication/unified_comm.html",
        user=serialize_doc(request.current_user),
        active_tab=tab,
        initial_project_id=project_id,
        initial_conversation_id=conversation_id
    )


@page_bp.route("/notifications")
@require_auth
def notifications_page():
    return render_template(
        "notifications/notifications.html",
        user=serialize_doc(request.current_user)
    )


@page_bp.route("/birthdays")
@require_auth
def birthday_calendar_page():
    return render_template(
        "birthdays/birthday_calendar.html",
        user=serialize_doc(request.current_user)
    )


@page_bp.route("/settings")
@page_bp.route("/settings/org")
@require_roles(Role.HR, Role.MANAGER, Role.ADMIN)
def settings_page():
    return render_template(
        "settings/org_settings.html",
        user=serialize_doc(request.current_user)
    )


@page_bp.route("/audit-logs")
@require_roles(Role.HR, Role.MANAGER, Role.ADMIN)
def audit_logs_page():
    return render_template(
        "audit/audit_logs.html",
        user=serialize_doc(request.current_user)
    )


@page_bp.route("/work-diary")
@require_auth
def work_diary_page():
    today = get_local_date_str()
    return render_template(
        "work_diary/work_diary.html",
        user=serialize_doc(request.current_user),
        today_date=today,
        current_month=today[:7]
    )


@page_bp.route("/leaves")
@require_auth
def leaves_page():
    role = request.current_user.get("role")
    today = get_local_date_str()

    if role in (Role.HR, "hr_manager"):
        return render_template(
            "leaves/hr_leaves.html",
            user=serialize_doc(request.current_user),
            today_date=today,
            hr_email=Config.HR_EMAIL
        )

    return render_template(
        "leaves/employee_leaves.html",
        user=serialize_doc(request.current_user),
        today_date=today,
        hr_email=Config.HR_EMAIL
    )


@page_bp.route("/salary")
@require_auth
def salary_page():
    user = request.current_user
    if user.get("role") in (Role.TEAM_LEAD, Role.MANAGER):
        return render_template(
            "errors/403.html",
            user=serialize_doc(user),
            required_roles=[Role.EMPLOYEE, Role.HR],
            user_role=user.get("role")
        ), 403

    from backend.services.user_service import UserService
    user_enriched = UserService.enrich_user_profile(user)
    return render_template(
        "salary/salary_view.html",
        user=serialize_doc(user_enriched),
        today_date=get_local_date_str()
    )


@page_bp.route("/holidays")
@require_auth
def holidays_page():
    if request.current_user.get("role") == Role.EMPLOYEE:
        return redirect(url_for("page_views.attendance_page", tab="holidays"))
    today = get_local_date_str()
    target_month = request.args.get("month", today[:7])
    return render_template(
        "holidays/holidays.html",
        user=serialize_doc(request.current_user),
        today_date=today,
        target_month=target_month
    )


@page_bp.route("/analytics")
@require_auth
def analytics_page():
    if request.current_user.get("role") == Role.HR:
        return redirect(url_for("page_views.attendance_page", tab="analytics"))
    if request.current_user.get("role") == Role.EMPLOYEE:
        return redirect(url_for("page_views.projects_page", tab="analytics"))
    return render_template(
        "analytics/analytics.html",
        user=serialize_doc(request.current_user),
        today_date=get_local_date_str()
    )


# ============================================================================
# ENTERPRISE EXTENSION PAGES (R1-R29)
# ============================================================================
@page_bp.route("/facilities")
@require_auth
def facilities_page():
    from backend.services.enterprise_hr_service import FacilityBookingService, TravelAllocationService, EngagementSupportService
    today = get_local_date_str()
    data = FacilityBookingService.get_rooms_and_bookings(today)
    travel_reqs = TravelAllocationService.get_travel_requests(request.current_user)
    emp_id = request.current_user.get("employee_id") or request.current_user.get("emp_id")
    claims = EngagementSupportService.get_expense_claims(emp_id)
    return render_template(
        "enterprise/facilities.html",
        user=serialize_doc(request.current_user),
        today_date=today,
        **data,
        travel_requests=travel_reqs,
        claims=claims
    )


@page_bp.route("/assets")
@require_auth
def assets_page():
    from backend.services.enterprise_hr_service import AssetSoftwareService, SeatingLockerService
    emp_id = request.current_user.get("employee_id") or request.current_user.get("emp_id")
    data = AssetSoftwareService.get_employee_assets(emp_id)
    user_role = normalize_role(request.current_user.get("role"))
    inv = AssetSoftwareService.get_global_inventory(request.current_user) if user_role in (Role.HR, Role.MANAGER, Role.ADMIN) else {}
    seating = SeatingLockerService.get_employee_seating(emp_id)
    all_seating = SeatingLockerService.get_all_seating_allocations() if user_role in (Role.HR, Role.MANAGER, Role.ADMIN, Role.TL) else []
    return render_template(
        "enterprise/assets.html",
        user=serialize_doc(request.current_user),
        today_date=get_local_date_str(),
        **data,
        all_seating=all_seating,
        inventory=inv
    )


@page_bp.route("/performance")
@page_bp.route("/tasks-certificates")
@require_auth
def performance_page():
    from backend.services.enterprise_hr_service import PerformanceLearningService
    emp_id = request.current_user["employee_id"]
    data = PerformanceLearningService.get_employee_performance_hub(emp_id)
    return render_template(
        "enterprise/performance.html",
        user=serialize_doc(request.current_user),
        today_date=get_local_date_str(),
        **data
    )


@page_bp.route("/engagement")
@page_bp.route("/kudos-support")
@require_auth
def engagement_page():
    from backend.services.enterprise_hr_service import EngagementSupportService, TravelAllocationService
    feed = EngagementSupportService.get_community_feed()
    kudos = EngagementSupportService.get_kudos_leaderboard()
    emp_id = request.current_user["employee_id"]
    tickets = EngagementSupportService.get_support_tickets(emp_id)
    claims = EngagementSupportService.get_expense_claims(emp_id)
    travel_reqs = TravelAllocationService.get_travel_requests(request.current_user)
    return render_template(
        "enterprise/engagement.html",
        user=serialize_doc(request.current_user),
        today_date=get_local_date_str(),
        feed=feed,
        kudos=kudos,
        tickets=tickets,
        claims=claims,
        travel_requests=travel_reqs
    )


@page_bp.route("/policies")
@require_auth
def policies_page():
    from backend.services.enterprise_hr_service import EngagementSupportService
    policies = EngagementSupportService.get_company_policy_vault()
    return render_template(
        "enterprise/policies.html",
        user=serialize_doc(request.current_user),
        today_date=get_local_date_str(),
        policies=policies
    )


@page_bp.route("/separation")
@page_bp.route("/exit-tenure")
@require_auth
def separation_page():
    from backend.services.enterprise_hr_service import SeparationService
    emp_id = request.current_user["employee_id"]
    data = SeparationService.get_tenure_and_status(emp_id)
    pending_resignations = SeparationService.get_all_resignations(request.current_user)
    return render_template(
        "enterprise/separation.html",
        user=serialize_doc(request.current_user),
        today_date=get_local_date_str(),
        pending_resignations=pending_resignations,
        **data
    )


@page_bp.route("/recruitment")
@require_roles(Role.TEAM_LEAD, Role.MANAGER, Role.HR, Role.ADMIN)
def recruitment_page():
    from backend.services.enterprise_hr_service import RecruitmentTalentService
    scorecards = RecruitmentTalentService.get_candidate_scorecards()
    ats = RecruitmentTalentService.get_ats_pipeline()
    return render_template(
        "enterprise/recruitment.html",
        user=serialize_doc(request.current_user),
        today_date=get_local_date_str(),
        scorecards=scorecards,
        **ats
    )


@page_bp.route("/payroll-center")
@require_roles(Role.HR, Role.ADMIN)
def payroll_center_page():
    from backend.services.enterprise_hr_service import EnterprisePayrollService
    data = EnterprisePayrollService.get_payroll_overview()
    return render_template(
        "enterprise/payroll_center.html",
        user=serialize_doc(request.current_user),
        today_date=get_local_date_str(),
        **data
    )



