from flask import Blueprint, request, jsonify, Response, send_file
from datetime import datetime, date, timedelta
from bson import ObjectId
from database.connection import get_db
from permissions.rbac import (
    require_auth,
    require_roles,
    Role,
    normalize_role,
    can_view_attendance,
    can_view_profile,
    can_view_salary,
    can_access_complaint,
    can_access_employee_record,
    can_view_projects
)
from services.attendance_service import AttendanceService
from services.user_service import UserService
from services.project_service import ProjectService
from services.complaint_service import ComplaintService
from services.notification_service import NotificationService
from services.export_service import ExportService
from services.audit_service import AuditService
from services.work_diary_service import WorkDiaryService
from services.leave_service import LeaveService
from services.wfh_service import WFHService
from services.roster_service import RosterService
from services.pip_service import PIPService
from services.document_service import DocumentService
from utils.serializers import serialize_doc, serialize_docs
from utils.timezone import get_local_date_str, now_utc, to_local
from config import Config

api_bp = Blueprint("main_api", __name__, url_prefix="/api")


# ==========================================
# 1. ATTENDANCE ENDPOINTS
# ==========================================

@api_bp.route("/attendance/today", methods=["GET"])
@require_auth
def get_today_attendance():
    user = request.current_user
    today_str = get_local_date_str()
    timing_status = AttendanceService.get_office_timing_status(user["employee_id"])
    rules = AttendanceService.get_office_rules()
    record = AttendanceService.recalculate_daily_summary(user["employee_id"], today_str)
    if not record:
        record = AttendanceService.get_employee_daily_record(user["employee_id"], today_str)

    server_now = now_utc()

    has_open_session = False
    if timing_status and "has_open_session" in timing_status:
        has_open_session = bool(timing_status["has_open_session"])
    elif record:
        has_open_session = bool(record.get("has_open_session", False))

    first_login_local = None
    if record and record.get("first_login"):
        first_login_local = to_local(record["first_login"]).strftime("%I:%M %p")

    rec_dict = serialize_doc(record) or {}
    rec_dict["has_open_session"] = has_open_session
    if timing_status and "shift_split" in timing_status:
        rec_dict["shift_split"] = timing_status["shift_split"]

    return jsonify({
        "attendance": rec_dict,
        "office_rules": rules,
        "timing_status": timing_status,
        "shift_split": timing_status.get("shift_split") if timing_status else None,
        "has_open_session": has_open_session,
        "is_clocked_in": has_open_session,
        "first_login_local": first_login_local,
        "server_time": server_now.isoformat(),
        "today_date": today_str
    })


@api_bp.route("/attendance/cutoff-status", methods=["GET"])
@require_auth
def get_cutoff_status():
    user = request.current_user
    timing = AttendanceService.get_office_timing_status(user["employee_id"])
    rules = AttendanceService.get_office_rules()
    return jsonify({
        "office_rules": rules,
        "timing_status": timing,
        "server_time": now_utc().isoformat()
    })


def _extract_location_payload(data: dict) -> dict | None:
    if not data or not isinstance(data, dict):
        return None
    loc = data.get("location")
    if isinstance(loc, dict) and loc.get("status"):
        return loc
    if "latitude" in data or "lat" in data or "location_status" in data:
        lat = data.get("latitude") if "latitude" in data else data.get("lat")
        lng = data.get("longitude") if "longitude" in data else data.get("lng")
        status = data.get("location_status") or ("CAPTURED" if lat is not None else "UNAVAILABLE")
        try:
            lat_f = float(lat) if lat is not None else None
            lng_f = float(lng) if lng is not None else None
            acc_f = float(data.get("accuracy")) if data.get("accuracy") is not None else None
        except (ValueError, TypeError):
            lat_f, lng_f, acc_f = None, None, None
        return {
            "status": status,
            "latitude": lat_f,
            "longitude": lng_f,
            "accuracy_meters": acc_f,
            "captured_at": now_utc()
        }
    return None


@api_bp.route("/attendance/check-in", methods=["POST"])
@require_auth
def manual_check_in():
    user = request.current_user
    data = request.get_json(silent=True) or {}
    target_emp_id = data.get("employee_id")
    if target_emp_id and target_emp_id != user["employee_id"]:
        return jsonify({"error": "Forbidden: You cannot modify attendance for another employee."}), 403

    loc = _extract_location_payload(data)
    summary, session_id, is_new = AttendanceService.record_login(
        user, ip_address=request.remote_addr, return_is_new=True, location=loc
    )
    if not is_new:
        return jsonify({
            "success": False,
            "error": "You already have an active attendance session in progress. Please clock out first.",
            "already_clocked_in": True,
            "session_id": session_id,
            "attendance": serialize_doc(summary)
        }), 400

    return jsonify({
        "success": True,
        "message": "Check-in recorded successfully.",
        "session_id": session_id,
        "attendance": serialize_doc(summary)
    })


@api_bp.route("/attendance/check-out", methods=["POST"])
@require_auth
def manual_check_out():
    user = request.current_user
    data = request.get_json(silent=True) or {}
    target_emp_id = data.get("employee_id")
    if target_emp_id and target_emp_id != user["employee_id"]:
        return jsonify({"error": "Forbidden: You cannot modify attendance for another employee."}), 403

    session_id = data.get("session_id")
    loc = _extract_location_payload(data)
    summary, closed_session = AttendanceService.record_logout(
        user, session_id=session_id, ip_address=request.remote_addr, location=loc
    )
    if not closed_session:
        return jsonify({
            "success": False,
            "error": "No active clock-in session found to clock out from.",
            "attendance": serialize_doc(summary)
        }), 400

    return jsonify({
        "success": True,
        "message": "Check-out recorded successfully.",
        "session_id": closed_session,
        "attendance": serialize_doc(summary)
    })


@api_bp.route("/attendance/break/start", methods=["POST"])
@require_auth
def start_break():
    user = request.current_user
    data = request.get_json(silent=True) or {}
    notes = data.get("notes", "Work Break")
    summary, err = AttendanceService.record_break_start(user, notes=notes)
    if err:
        return jsonify({"success": False, "error": err}), 400
    return jsonify({
        "success": True,
        "message": "Break recorded. Active working timer paused.",
        "attendance": serialize_doc(summary)
    })


@api_bp.route("/attendance/break/end", methods=["POST"])
@require_auth
def end_break():
    user = request.current_user
    summary, err = AttendanceService.record_break_end(user)
    if err:
        return jsonify({"success": False, "error": err}), 400
    return jsonify({
        "success": True,
        "message": "Break ended. Resumed active working time.",
        "attendance": serialize_doc(summary)
    })


@api_bp.route("/attendance/break", methods=["POST"])
@require_auth
def toggle_break_alias():
    """
    Intelligent break toggle endpoint. Pauses active session if working,
    or resumes active session if currently on break.
    """
    user = request.current_user
    data = request.get_json(silent=True) or {}
    employee_id = user.get("employee_id") or user.get("emp_id")
    event_time_utc = now_utc()
    date_str = get_local_date_str(event_time_utc)
    db = get_db()

    open_break = db.attendance_events.find_one({
        "employee_id": employee_id,
        "date": date_str,
        "event_type": "BREAK_START",
        "is_closed": False
    })

    action = (data.get("action") or "").lower()
    if action == "start" or (not action and not open_break):
        summary, err = AttendanceService.record_break_start(user, notes=data.get("notes", "Work Break"))
        if err:
            return jsonify({"success": False, "error": err}), 400
        return jsonify({
            "success": True,
            "on_break": True,
            "message": "Break recorded. Active working timer paused.",
            "attendance": serialize_doc(summary)
        })
    else:
        summary, err = AttendanceService.record_break_end(user)
        if err:
            return jsonify({"success": False, "error": err}), 400
        return jsonify({
            "success": True,
            "on_break": False,
            "message": "Break ended. Resumed active working time.",
            "attendance": serialize_doc(summary)
        })


@api_bp.route("/attendance/team-overview", methods=["GET"])
@require_roles(Role.TEAM_LEAD, Role.MANAGER, Role.HR)
def get_team_attendance_overview():
    user = request.current_user
    date_str = request.args.get("date", get_local_date_str())
    overview = AttendanceService.get_team_attendance_overview(user, date_str=date_str)
    return jsonify(serialize_doc(overview))


@api_bp.route("/attendance/my-history", methods=["GET"])
@require_auth
def get_my_attendance_history():
    user = request.current_user
    today = now_utc()
    year = int(request.args.get("year", today.year))
    month = int(request.args.get("month", today.month))

    summary = AttendanceService.get_employee_monthly_summary(user["employee_id"], year, month)
    summary["records"] = serialize_docs(summary["records"])
    return jsonify(summary)


@api_bp.route("/attendance/calendar", methods=["GET"])
@api_bp.route("/attendance/calendar-month", methods=["GET"])
@require_auth
def get_attendance_calendar():
    user = request.current_user
    today = now_utc()
    year = int(request.args.get("year", today.year))
    month = int(request.args.get("month", today.month))
    target_emp_id = request.args.get("employee_id")

    if target_emp_id and target_emp_id != user["employee_id"]:
        db = get_db()
        target_user = db.users.find_one({"employee_id": target_emp_id})
        if not can_view_attendance(user, target_emp_id, target_user):
            return jsonify({"error": "Access Denied: You are not authorized to view this employee's attendance calendar."}), 403
        emp_id = target_emp_id
    else:
        emp_id = user["employee_id"]

    calendar_data = AttendanceService.get_monthly_calendar_data(emp_id, year, month)
    return jsonify(calendar_data)



@api_bp.route("/attendance/user/<employee_id>", methods=["GET"])
@require_auth
def get_user_attendance(employee_id):
    user = request.current_user
    db = get_db()
    target_user = db.users.find_one({"employee_id": employee_id})
    if not target_user:
        return jsonify({"error": "Employee not found."}), 404

    if not can_view_attendance(user, employee_id, target_user):
        return jsonify({"error": "Access Denied: You are not authorized to view this attendance record."}), 403

    today = now_utc()
    year = int(request.args.get("year", today.year))
    month = int(request.args.get("month", today.month))

    summary = AttendanceService.get_employee_monthly_summary(employee_id, year, month)
    summary["records"] = serialize_docs(summary["records"])
    summary["target_user"] = serialize_doc(target_user)
    return jsonify(summary)


@api_bp.route("/attendance/hr-monitor", methods=["GET"])
@require_roles(Role.HR)
def hr_attendance_monitor():
    date_str = request.args.get("date", get_local_date_str())
    filters = {
        "department": request.args.get("department"),
        "status": request.args.get("status"),
        "search": request.args.get("search")
    }
    overview = AttendanceService.get_hr_monitoring_overview(date_str, filters)
    overview["records"] = serialize_docs(overview["records"])
    return jsonify(overview)


@api_bp.route("/attendance/hr-manager-monitor", methods=["GET"])
@require_roles(Role.HR, Role.ADMIN)
def hr_manager_attendance_monitor():
    date_str = request.args.get("date", get_local_date_str())
    overview = AttendanceService.get_hr_manager_attendance_overview(date_str)
    overview["records"] = serialize_docs(overview["records"])
    return jsonify(overview)


@api_bp.route("/attendance/correct", methods=["POST"])
@api_bp.route("/attendance/correction", methods=["POST"])
@require_roles(Role.HR, Role.ADMIN)
def correct_attendance():
    data = request.get_json(silent=True) or {}
    target_emp_id = data.get("employee_id")
    date_str = data.get("attendance_date") or data.get("date")
    reason = data.get("reason") or data.get("correction_reason")
    corrections = data.get("corrections")
    if corrections is None:
        corrections = {
            k: v for k, v in data.items()
            if k in ["status", "late_arrival_status", "delay_minutes", "total_hours"]
        }

    if not target_emp_id or not date_str or not reason:
        return jsonify({"error": "employee_id, date, and reason are required."}), 400

    record, err = AttendanceService.correct_attendance_record(
        actor=request.current_user,
        target_employee_id=target_emp_id,
        date_str=date_str,
        corrections=corrections,
        reason=reason
    )
    if err:
        code = 403 if ("Only authorized" in err or "Unauthorized" in err or "Access Denied" in err) else 400
        return jsonify({"error": err}), code

    return jsonify({"success": True, "record": serialize_doc(record)})


# ==========================================
# ATTENDANCE CORRECTIONS (REGULARIZATION WORKFLOW)
# Employee -> Manager Approves/Rejects -> HR Intimated
# ==========================================

@api_bp.route("/attendance/corrections/request", methods=["POST"])
@api_bp.route("/attendance/corrections", methods=["POST"])
@require_auth
def request_attendance_correction():
    from services.attendance_correction_service import AttendanceCorrectionService
    user = request.current_user
    data = request.get_json(silent=True) or {}
    target_date = data.get("target_date") or data.get("date")
    corr_type = data.get("correction_type") or "PUNCH_TIME"
    req_in = data.get("requested_in_time") or data.get("requested_clock_in") or data.get("in_time")
    req_out = data.get("requested_out_time") or data.get("requested_clock_out") or data.get("out_time")
    reason = data.get("reason")
    requested_status = data.get("requested_status") or "PRESENT"

    req, err = AttendanceCorrectionService.request_correction(
        employee_user=user,
        target_date=target_date,
        correction_type=corr_type,
        requested_in_time=req_in,
        requested_out_time=req_out,
        reason=reason,
        requested_status=requested_status
    )
    if err:
        return jsonify({"success": False, "error": err}), 400

    return jsonify({"success": True, "message": "Attendance correction request submitted to Manager.", "correction": serialize_doc(req)})


@api_bp.route("/attendance/corrections/my", methods=["GET"])
@require_auth
def get_my_attendance_corrections():
    from services.attendance_correction_service import AttendanceCorrectionService
    user = request.current_user
    corrections = AttendanceCorrectionService.get_my_corrections(user["employee_id"])
    return jsonify({"success": True, "corrections": serialize_docs(corrections)})


@api_bp.route("/attendance/corrections/pending", methods=["GET"])
@require_roles(Role.TEAM_LEAD, Role.MANAGER, Role.HR, Role.ADMIN)
def get_pending_attendance_corrections():
    from services.attendance_correction_service import AttendanceCorrectionService
    user = request.current_user
    user_role = normalize_role(user.get("role"))
    actor_id = user.get("employee_id") or user.get("emp_id")
    if user_role in (Role.HR, Role.ADMIN):
        pending = AttendanceCorrectionService.get_all_pending_corrections_for_hr()
    elif user_role == Role.TL:
        pending = AttendanceCorrectionService.get_pending_corrections_for_team_lead(
            team_lead_id=actor_id, department=user.get("department")
        )
    else:
        pending = AttendanceCorrectionService.get_pending_corrections_for_manager(
            manager_id=actor_id, department=user.get("department")
        )
    return jsonify({"success": True, "pending_corrections": serialize_docs(pending)})


@api_bp.route("/attendance/corrections/<request_id>/review", methods=["POST"])
@require_roles(Role.TEAM_LEAD, Role.MANAGER, Role.HR, Role.ADMIN)
def review_attendance_correction(request_id):
    from services.attendance_correction_service import AttendanceCorrectionService
    user = request.current_user
    data = request.get_json(silent=True) or {}
    decision = data.get("decision")
    remarks = data.get("remarks")

    record, err = AttendanceCorrectionService.review_correction(
        reviewer_user=user,
        request_id=request_id,
        decision=decision,
        remarks=remarks
    )
    if err:
        is_auth_err = any(
            token in err for token in ("Access Denied", "Unauthorized", "cannot approve", "Only authorized", "Only Team Leads")
        )
        return jsonify({"success": False, "error": err}), 403 if is_auth_err else 400

    return jsonify({
        "success": True,
        "message": f"Attendance correction {decision.lower()} successfully.",
        "record": serialize_doc(record)
    })


@api_bp.route("/attendance/corrections/<request_id>", methods=["DELETE"])
@require_auth
def cancel_attendance_correction_route(request_id):
    from services.attendance_correction_service import AttendanceCorrectionService
    user = request.current_user
    success, err = AttendanceCorrectionService.cancel_correction(user, request_id)
    if not success:
        is_auth_err = err and any(
            token in err for token in ("Access Denied", "Unauthorized", "cannot cancel another", "cannot be cancelled by employees")
        )
        return jsonify({"success": False, "error": err}), 403 if is_auth_err else 400
    return jsonify({"success": True, "message": "Attendance correction cancelled successfully."}), 200


@api_bp.route("/attendance/corrections/hr-intimations", methods=["GET"])
@require_roles(Role.HR, Role.ADMIN)
def get_hr_attendance_corrections():
    from services.attendance_correction_service import AttendanceCorrectionService
    corrections = AttendanceCorrectionService.get_all_corrections_for_hr()
    return jsonify({"success": True, "corrections": serialize_docs(corrections)})


# ==========================================
# 2. USER & PROFILE MANAGEMENT ENDPOINTS
# ==========================================

@api_bp.route("/users", methods=["GET"])
@api_bp.route("/profiles", methods=["GET"])
@require_auth
def list_users():
    actor = request.current_user
    role = normalize_role(actor.get("role"))
    actor_id = actor.get("employee_id") or actor.get("emp_id")
    db = get_db()

    if role == Role.EMPLOYEE:
        return jsonify({"error": "Access Denied: Employees cannot list the company staff directory."}), 403

    include_inactive = (
        role in (Role.HR, Role.ADMIN)
        and request.args.get("include_inactive", "false").lower() == "true"
    )
    query = {} if include_inactive else {"is_active": True}

    restricted_projection = {
        "password_hash": 0,
        "activation_token": 0,
        "salary_info": 0,
        "bank_info": 0,
        "bank_details": 0,
        "payslips": 0,
        "complaints": 0,
        "hr_notes": 0,
        "documents": 0,
        "aadhaar_number": 0,
        "pan_number": 0,
        "bank_account_number": 0,
        "residential_address": 0,
        "citizen_id_address": 0,
        "emergency_contact": 0,
        "personal_email": 0,
        "date_of_birth": 0,
        "dob": 0,
        "birthdate": 0
    }

    if role == Role.TL:
        # Team Lead Staff Directory: strictly active normal Employees assigned to this Team Lead's team
        # NEVER show HR, Managers, other TLs, or unrelated teams
        team_id = actor.get("team_id")
        lead_teams = [t["team_id"] for t in db.teams.find({"$or": [{"lead_employee_id": actor_id}, {"lead_id": actor_id}]}, {"team_id": 1}) if t.get("team_id")]
        if team_id:
            lead_teams.append(team_id)
        tl_clauses = [{"assigned_tl_id": actor_id}, {"team_lead_id": actor_id}]
        if lead_teams:
            tl_clauses.append({"team_id": {"$in": list(set(lead_teams))}})
        lead_query = {"role": Role.EMPLOYEE, "is_active": True, "$or": tl_clauses}
        users = list(db.users.find(lead_query, restricted_projection))
        return jsonify({"users": serialize_docs(users)})
    elif role == Role.MANAGER:
        # Manager Staff Directory: active Team Leads and Employees strictly within authorized reporting scope / department
        mgr_clauses = [{"manager_id": actor_id}, {"reporting_manager_id": actor_id}]
        mgr_dept = actor.get("department")
        mgr_team = actor.get("team_id")
        if mgr_team:
            mgr_clauses.append({"team_id": mgr_team})
        elif mgr_dept and mgr_dept not in ("Executive HR", "Management", "Executive"):
            mgr_clauses.append({"department": mgr_dept})
        mgr_query = {
            "role": {"$in": [Role.EMPLOYEE, Role.TEAM_LEAD, Role.TL]},
            "is_active": True,
            "$or": mgr_clauses
        }
        users = list(db.users.find(mgr_query, restricted_projection))
        return jsonify({"users": serialize_docs(users)})
    elif role in (Role.HR, Role.ADMIN):
        role_filter = request.args.get("role")
        if role_filter and role_filter != "all":
            query["role"] = role_filter
        users = list(db.users.find(query, {"password_hash": 0, "activation_token": 0}))
        return jsonify({"users": serialize_docs(users)})

    return jsonify({"error": "Access Denied."}), 403


@api_bp.route("/users/team-directory", methods=["GET"])
@require_roles(Role.TEAM_LEAD, Role.MANAGER)
def get_team_directory():
    actor = request.current_user
    actor_role = normalize_role(actor.get("role"))
    actor_id = actor.get("employee_id") or actor.get("emp_id")
    db = get_db()
    team_id = actor.get("team_id")

    query = {"role": Role.EMPLOYEE, "is_active": True}
    if actor_role == Role.TL:
        tl_clauses = [{"assigned_tl_id": actor_id}, {"team_lead_id": actor_id}]
        lead_teams = [t["team_id"] for t in db.teams.find({"$or": [{"lead_employee_id": actor_id}, {"lead_id": actor_id}]}, {"team_id": 1}) if t.get("team_id")]
        if team_id:
            lead_teams.append(team_id)
        if lead_teams:
            tl_clauses.append({"team_id": {"$in": list(set(lead_teams))}})
        query["$or"] = tl_clauses
    elif actor_role == Role.MANAGER:
        query = {"role": {"$in": [Role.EMPLOYEE, Role.TEAM_LEAD, Role.TL]}, "is_active": True}
        mgr_clauses = [{"manager_id": actor_id}, {"reporting_manager_id": actor_id}]
        if actor.get("department") and actor.get("department") not in ("Executive HR", "Management", "Executive"):
            mgr_clauses.append({"department": actor.get("department")})
        elif team_id:
            mgr_clauses.append({"team_id": team_id})
        query["$or"] = mgr_clauses

    projection = {
        "password_hash": 0,
        "activation_token": 0,
        "salary_info": 0,
        "bank_details": 0,
        "bank_info": 0,
        "payslips": 0,
        "complaints": 0,
        "hr_notes": 0,
        "documents": 0,
        "aadhaar_number": 0,
        "pan_number": 0,
        "bank_account_number": 0,
        "residential_address": 0,
        "citizen_id_address": 0,
        "emergency_contact": 0,
        "personal_email": 0,
        "date_of_birth": 0,
        "dob": 0,
        "birthdate": 0
    }
    employees = list(db.users.find(query, projection).sort("full_name", 1))
    
    today_str = get_local_date_str()
    emp_ids = [e["employee_id"] for e in employees]
    
    projects = list(db.projects.find({
        "status": {"$in": ["In Progress", "Planning", "Active", "Open"]},
        "assigned_members": {"$in": emp_ids}
    }, {"name": 1, "title": 1, "project_id": 1, "assigned_members": 1, "assigned_manager": 1, "lead_id": 1}))
    
    att_records = list(db.attendance_daily.find({
        "employee_id": {"$in": emp_ids},
        "attendance_date": today_str
    }))
    att_map = {a["employee_id"]: a for a in att_records}
    
    leaves = list(db.leave_requests.find({
        "employee_id": {"$in": emp_ids},
        "status": "Approved",
        "request_type": "LEAVE",
        "start_date": {"$lte": today_str},
        "end_date": {"$gte": today_str}
    }))
    leave_map = {l["employee_id"]: l for l in leaves}

    supervisors = []
    if actor.get("role") == Role.TEAM_LEAD:
        mgr = db.users.find_one({"role": Role.MANAGER, "is_active": True}, {"full_name": 1, "email": 1, "employee_id": 1, "designation": 1})
        if mgr:
            supervisors.append({
                "employee_id": mgr.get("employee_id"),
                "name": mgr.get("full_name"),
                "designation": mgr.get("designation", "Operations Manager"),
                "relationship": "Project Supervisor"
            })

    enriched = []
    for emp in employees:
        eid = emp["employee_id"]
        emp_projects = [p.get("name") or p.get("title") for p in projects if eid in p.get("assigned_members", [])]
        
        if leave_map.get(eid):
            avail = "On Leave"
            avail_badge = "badge-leave"
        elif att_map.get(eid):
            rec = att_map[eid]
            if rec.get("is_on_break"):
                avail = "On Break"
                avail_badge = "badge-warning"
            elif rec.get("has_open_session"):
                avail = "Active / Working"
                avail_badge = "badge-present"
            else:
                avail = "Clocked Out"
                avail_badge = "badge-secondary"
        else:
            avail = "Not Clocked In"
            avail_badge = "badge-light text-secondary border"

        skill_docs = list(db.skills.find({"employee_id": eid}))
        skill_names = [s.get("skill_name") or s.get("name") for s in skill_docs if s.get("skill_name") or s.get("name")]
        if not skill_names and emp.get("skills"):
            skill_names = emp.get("skills") if isinstance(emp.get("skills"), list) else [str(emp.get("skills"))]

        clean_emp = serialize_doc(emp)
        clean_emp["assigned_projects"] = emp_projects
        clean_emp["relevant_skills"] = skill_names[:5]
        clean_emp["work_availability"] = avail
        clean_emp["work_availability_badge"] = avail_badge
        enriched.append(clean_emp)

    return jsonify({
        "team_id": team_id,
        "has_pending_assignment": (len(employees) == 0),
        "total_members": len(employees),
        "supervisors": supervisors,
        "employees": enriched
    })


@api_bp.route("/users", methods=["POST"])
@require_roles(Role.HR, Role.ADMIN)
def create_user():
    data = request.get_json(silent=True) or {}
    new_user, err = UserService.create_user(creator=request.current_user, user_data=data)
    if err:
        return jsonify({"error": err}), 403 if "not authorized" in err.lower() or "only administrators" in err.lower() else 400
    return jsonify({"success": True, "user": serialize_doc(new_user)}), 201


@api_bp.route("/users/<employee_id>", methods=["GET"])
@require_auth
def get_user_profile(employee_id):
    db = get_db()
    query = {
        "$or": [
            {"employee_id": employee_id},
            {"emp_id": employee_id},
            {"email": str(employee_id).strip().lower()},
            {"personal_email": str(employee_id).strip().lower()}
        ]
    }
    if ObjectId.is_valid(employee_id):
        query["$or"].append({"_id": ObjectId(employee_id)})
    target_user = db.users.find_one(query)
    if not target_user:
        return jsonify({"error": "User not found."}), 404

    if not can_view_profile(request.current_user, target_user):
        return jsonify({"error": "Access Denied: You cannot view this profile."}), 403

    user_data = UserService.enrich_user_profile(target_user)
    user_data.pop("activation_token", None)
    user_data.pop("password_hash", None)

    actor_id = (request.current_user.get("employee_id") or request.current_user.get("emp_id") or "").strip().upper()
    target_id = (target_user.get("employee_id") or target_user.get("emp_id") or "").strip().upper()
    is_self = bool(actor_id and target_id and actor_id == target_id)
    actor_role = normalize_role(request.current_user.get("role"))

    if not can_view_salary(request.current_user, target_user):
        user_data.pop("salary_info", None)
        user_data.pop("salary_slips", None)
        user_data.pop("bank_info", None)
        user_data.pop("bank_details", None)
        user_data.pop("payslips", None)

    if not is_self and actor_role not in (Role.HR, Role.ADMIN):
        for sensitive_field in (
            "aadhaar_number", "pan_number", "bank_account_number",
            "complaints", "hr_notes", "documents", "emergency_contact",
            "personal_email", "residential_address", "citizen_id_address",
            "address", "permanent_address", "date_of_birth", "dob",
            "birthdate", "place_of_birth", "marital_status", "religion",
            "blood_type", "age", "other_contact", "nominees_count",
            "nominees_summary", "notes"
        ):
            user_data.pop(sensitive_field, None)

    return jsonify({"user": serialize_doc(user_data)})


@api_bp.route("/users/<employee_id>/skills", methods=["POST"])
@require_auth
def add_user_skill(employee_id):
    data = request.get_json(silent=True) or {}
    skill_name = data.get("skill") or data.get("name") or ""
    level = data.get("level", "Proficient")

    skills, err = UserService.add_user_skill(
        actor=request.current_user,
        target_employee_id=employee_id,
        skill_name=skill_name,
        level=level
    )
    if err:
        return jsonify({"error": err}), 400
    return jsonify({"success": True, "skills": skills})


@api_bp.route("/users/<employee_id>/skills/<path:skill_name>", methods=["DELETE"])
@require_auth
def remove_user_skill(employee_id, skill_name):
    skills, err = UserService.remove_user_skill(
        actor=request.current_user,
        target_employee_id=employee_id,
        skill_name=skill_name
    )
    if err:
        return jsonify({"error": err}), 400
    return jsonify({"success": True, "skills": skills})


@api_bp.route("/users/<employee_id>/salary", methods=["GET"])
@require_auth
def get_user_salary(employee_id):
    actor = request.current_user
    db = get_db()
    target_user = db.users.find_one({"$or": [{"employee_id": employee_id}, {"emp_id": employee_id}]})
    if not target_user:
        return jsonify({"error": "Employee not found."}), 404
    if not can_view_salary(actor, target_user):
        return jsonify({"error": "Access Denied: You cannot view this employee's salary."}), 403
    salary_info = UserService.get_salary_info(target_user)
    slips = UserService.get_salary_slips(target_user, count=12)
    return jsonify({"success": True, "salary": salary_info, "slips": slips})


@api_bp.route("/users/<employee_id>/salary/generate-slip", methods=["POST"])
@require_auth
def generate_user_salary_slip(employee_id):
    actor = request.current_user
    db = get_db()
    target_user = db.users.find_one({"$or": [{"employee_id": employee_id}, {"emp_id": employee_id}]})
    if not target_user:
        return jsonify({"error": "Employee not found."}), 404
    if not can_view_salary(actor, target_user):
        return jsonify({"error": "Access Denied: You cannot generate salary slips for this employee."}), 403

    data = request.get_json(silent=True) or {}
    year_month = (data.get("year_month") or "").strip()
    if not year_month:
        today = datetime.now()
        year_month = today.strftime("%Y-%m")

    slip, err = UserService.get_single_salary_slip(actor, employee_id, year_month)
    if not slip:
        # If not already present in the preceding list, dynamically calculate slip for that requested month
        salary_info = UserService.get_salary_info(target_user)
        try:
            parts = year_month.split("-")
            y, m = int(parts[0]), int(parts[1])
            dt = datetime(y, m, 1)
            month_name = dt.strftime("%B %Y")
        except Exception:
            month_name = year_month

        gross = salary_info.get("monthly_gross", 80000)
        basic = salary_info.get("basic", round(gross * 0.5))
        hra = salary_info.get("hra", round(gross * 0.25))
        special = salary_info.get("special_allowance", round(gross * 0.15))
        conveyance = salary_info.get("conveyance", round(gross * 0.10))
        pf = salary_info.get("pf", 1800)
        pt = salary_info.get("pt", 200)
        tds = salary_info.get("tds", 4500)
        med = salary_info.get("medical_insurance", 500)
        deductions = pf + pt + tds + med
        net = gross - deductions

        slip = {
            "slip_id": f"SLP-{employee_id}-{year_month}",
            "employee_id": employee_id,
            "employee_name": target_user.get("full_name") or target_user.get("name") or employee_id,
            "department": target_user.get("department", "General"),
            "designation": target_user.get("designation", "Staff"),
            "year_month": year_month,
            "month_name": month_name,
            "basic": basic,
            "hra": hra,
            "special_allowance": special,
            "conveyance": conveyance,
            "gross_earnings": gross,
            "pf": pf,
            "pt": pt,
            "tds": tds,
            "medical_insurance": med,
            "total_deductions": deductions,
            "net_salary": net,
            "status": "Disbursed",
            "payment_mode": "Direct Bank Deposit (NEFT/RTGS)",
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

    return jsonify({"success": True, "message": f"Payslip generated for {year_month}", "slip": slip})


@api_bp.route("/users/<employee_id>/salary", methods=["PUT"])
@require_roles(Role.HR, Role.ADMIN)
def update_user_salary(employee_id):
    data = request.get_json(silent=True) or {}
    salary_data = data.get("salary_info") or data
    reason = data.get("reason", "Salary structure revision")

    updated_salary, err = UserService.update_user_salary(
        actor=request.current_user,
        target_employee_id=employee_id,
        salary_data=salary_data,
        reason=reason
    )
    if err:
        code = 403 if ("Unauthorized" in err or "Only HR" in err or "Access Denied" in err) else 400
        return jsonify({"error": err}), code
    return jsonify({"success": True, "salary_info": updated_salary})


@api_bp.route("/users/<employee_id>/salary-slip/<year_month>", methods=["GET"])
@require_auth
def get_user_salary_slip(employee_id, year_month):
    slip, err = UserService.get_single_salary_slip(
        actor=request.current_user,
        target_employee_id=employee_id,
        year_month=year_month
    )
    if err:
        return jsonify({"error": err}), 403 if "Access Denied" in err else 404
    return jsonify({"slip": slip})


@api_bp.route("/users/<employee_id>", methods=["PUT"])
@require_auth
def update_user_profile(employee_id):
    actor = request.current_user
    actor_role = normalize_role(actor.get("role"))
    db = get_db()
    target_user = db.users.find_one({"$or": [{"employee_id": employee_id}, {"emp_id": employee_id}]})

    actor_emp_id = (actor.get("employee_id") or actor.get("emp_id") or "").strip().upper()
    resolved_target_id = ((target_user.get("employee_id") or target_user.get("emp_id")) if target_user else employee_id or "").strip().upper()
    is_self = bool(actor_emp_id and resolved_target_id and actor_emp_id == resolved_target_id)

    # Interns/Employees, TLs, and Managers cannot modify other employee profiles (HR/Admin only)
    if not is_self and actor_role not in (Role.HR, Role.ADMIN):
        return jsonify({"error": "Unauthorized: Profile information of other team members can only be managed by HR or System Administrators."}), 403

    data = request.get_json(silent=True) or {}
    updates = data.get("updates", {})
    if not updates and any(k in data for k in ["employee_id", "emp_id", "department", "designation", "full_name", "role", "verification_status"]):
        updates = {k: v for k, v in data.items() if k not in ("reason",)}
    reason = data.get("reason", "Profile update")

    updated, err = UserService.update_profile(
        actor=actor,
        target_employee_id=employee_id,
        updates=updates,
        reason=reason
    )
    if err:
        return jsonify({"error": err}), 403 if "Unauthorized" in err else 400

    return jsonify({"success": True, "user": serialize_doc(updated)})


@api_bp.route("/users/<employee_id>/history", methods=["GET"])
@require_auth
def get_profile_history(employee_id):
    actor = request.current_user
    db = get_db()
    target_user = db.users.find_one({"$or": [{"employee_id": employee_id}, {"emp_id": employee_id}]})
    if not target_user:
        return jsonify({"error": "User not found."}), 404

    actor_id = (actor.get("employee_id") or actor.get("emp_id") or "").strip().upper()
    target_id = (target_user.get("employee_id") or target_user.get("emp_id") or "").strip().upper()
    is_self = bool(actor_id and target_id and actor_id == target_id)
    actor_role = normalize_role(actor.get("role"))

    if not is_self and actor_role not in (Role.HR, Role.ADMIN):
        return jsonify({"error": "Access Denied: Profile change history is restricted to the employee, HR, and Administrators."}), 403

    history = UserService.get_profile_history(target_user.get("employee_id") or employee_id)
    return jsonify({"history": serialize_docs(history)})


@api_bp.route("/users/<employee_id>/toggle-status", methods=["POST"])
@require_roles(Role.HR, Role.ADMIN)
def toggle_status(employee_id):
    data = request.get_json(silent=True) or {}
    is_active = bool(data.get("is_active", True))

    success, msg = UserService.toggle_user_active_status(
        actor=request.current_user,
        target_employee_id=employee_id,
        is_active=is_active
    )
    if not success:
        is_auth_err = any(k in msg for k in ("Unauthorized", "HR can only"))
        return jsonify({"error": msg}), 403 if is_auth_err else 400
    return jsonify({"success": True, "message": msg})


@api_bp.route("/users/<employee_id>/offboard", methods=["POST"])
@require_roles(Role.HR, Role.ADMIN)
def offboard_employee_endpoint(employee_id):
    actor = request.current_user
    data = request.get_json(silent=True) or {}
    res, err = UserService.offboard_employee(actor, employee_id, data)
    if err:
        is_auth_err = any(k in err for k in ("Unauthorized", "Cannot offboard", "cannot offboard"))
        return jsonify({"error": err}), 403 if is_auth_err else 400
    return jsonify({
        "success": True,
        "message": f"Employee {employee_id} successfully offboarded.",
        "offboarding": serialize_doc(res)
    }), 200


@api_bp.route("/users/<employee_id>/reactivate", methods=["POST"])
@require_roles(Role.HR, Role.ADMIN)
def reactivate_employee_endpoint(employee_id):
    actor = request.current_user
    data = request.get_json(silent=True) or {}
    success, msg = UserService.reactivate_employee(actor, employee_id, data.get("reason"))
    if not success:
        return jsonify({"error": msg}), 403 if "Unauthorized" in msg else 400
    return jsonify({"success": True, "message": msg}), 200


@api_bp.route("/offboardings", methods=["GET"])
@require_roles(Role.HR, Role.ADMIN)
def get_offboardings_endpoint():
    actor = request.current_user
    offboardings = UserService.get_offboardings(actor)
    return jsonify({"offboardings": serialize_docs(offboardings)})


# ==========================================
# 3. PROJECT & TEAM MANAGEMENT ENDPOINTS
# ==========================================

@api_bp.route("/projects", methods=["GET"])
@require_auth
def list_projects():
    user = request.current_user
    if user.get("role") == Role.HR:
        return jsonify({"error": "Access Denied: HR personnel are restricted from project operations and project APIs."}), 403
    projects = ProjectService.get_user_projects(request.current_user)
    return jsonify({"projects": serialize_docs(projects)})


@api_bp.route("/projects", methods=["POST"])
@require_roles(Role.TEAM_LEAD, Role.MANAGER, Role.ADMIN, Role.HR_MANAGER, Role.ORGANIZATION, Role.TRAINER)
def create_project():
    data = request.get_json(silent=True) or {}
    project, err = ProjectService.create_project(request.current_user, data)
    if err:
        return jsonify({"error": err}), 400
    return jsonify({"success": True, "project": serialize_doc(project)}), 201


@api_bp.route("/projects/eligible-members", methods=["GET"])
@require_auth
def get_eligible_project_members():
    actor = request.current_user
    if actor.get("role") == Role.HR:
        return jsonify({"error": "Forbidden: HR does not manage project deliverables."}), 403

    db = get_db()
    query = {"role": Role.EMPLOYEE, "is_active": True}
    projection = {
        "employee_id": 1,
        "full_name": 1,
        "department": 1,
        "designation": 1,
        "email": 1,
        "skills": 1,
        "team_id": 1
    }
    employees = list(db.users.find(query, projection).sort("full_name", 1))

    emp_ids = [e["employee_id"] for e in employees]
    skill_docs = list(db.skills.find({"employee_id": {"$in": emp_ids}}))
    skills_by_emp = {}
    for s in skill_docs:
        eid = s.get("employee_id")
        s_name = s.get("skill_name") or s.get("name")
        if s_name:
            skills_by_emp.setdefault(eid, []).append(s_name)

    lead_query = {"role": {"$in": [Role.TEAM_LEAD, Role.MANAGER]}, "is_active": True}
    leads = list(db.users.find(lead_query, {"employee_id": 1, "full_name": 1, "role": 1, "designation": 1}))

    clean_list = []
    for emp in employees:
        eid = emp["employee_id"]
        emp_skills = skills_by_emp.get(eid, [])
        if not emp_skills and emp.get("skills"):
            emp_skills = emp["skills"] if isinstance(emp["skills"], list) else [str(emp["skills"])]

        clean_list.append({
            "employee_id": eid,
            "full_name": emp.get("full_name", ""),
            "department": emp.get("department", "Engineering"),
            "designation": emp.get("designation", "Engineer"),
            "skills": emp_skills[:4],
            "role": "employee"
        })

    return jsonify({
        "employees": clean_list,
        "eligible_members": clean_list,
        "leads": serialize_docs(leads),
        "count": len(clean_list)
    })


@api_bp.route("/projects/pending-approvals", methods=["GET"])
@require_auth
def get_pending_project_approvals():
    user = request.current_user
    if user.get("role") == Role.HR:
        return jsonify({"error": "Access Denied: HR personnel are restricted from project operations."}), 403
    approvals = ProjectService.get_pending_approvals(user)
    return jsonify({
        "proposals": serialize_docs(approvals.get("proposals", [])),
        "membership_requests": serialize_docs(approvals.get("membership_requests", [])),
        "total_pending": approvals.get("total_pending", 0)
    })


@api_bp.route("/projects/<project_id>/approve", methods=["POST"])
@require_roles(Role.MANAGER, Role.ADMIN)
def approve_project(project_id):
    data = request.get_json(silent=True) or {}
    review_notes = data.get("review_notes", "")
    project, err = ProjectService.approve_project(request.current_user, project_id, review_notes)
    if err:
        return jsonify({"error": err}), 400
    return jsonify({"success": True, "project": serialize_doc(project), "message": "Project approved and activated successfully."})


@api_bp.route("/projects/<project_id>/reject", methods=["POST"])
@require_roles(Role.MANAGER, Role.ADMIN)
def reject_project(project_id):
    data = request.get_json(silent=True) or {}
    rejection_reason = data.get("rejection_reason", "").strip()
    if not rejection_reason:
        return jsonify({"error": "Rejection reason is required."}), 400
    project, err = ProjectService.reject_project(request.current_user, project_id, rejection_reason)
    if err:
        return jsonify({"error": err}), 400
    return jsonify({"success": True, "project": serialize_doc(project), "message": "Project proposal rejected."})


@api_bp.route("/projects/<project_id>/request-changes", methods=["POST"])
@require_roles(Role.MANAGER, Role.ADMIN)
def request_changes_project(project_id):
    data = request.get_json(silent=True) or {}
    comments = data.get("comments", "").strip()
    if not comments:
        return jsonify({"error": "Comments detailing requested changes are required."}), 400
    project, err = ProjectService.request_changes_project(request.current_user, project_id, comments)
    if err:
        return jsonify({"error": err}), 400
    return jsonify({"success": True, "project": serialize_doc(project), "message": "Changes requested on proposal."})


@api_bp.route("/projects/<project_id>/proposal", methods=["PUT"])
@require_roles(Role.TEAM_LEAD, Role.MANAGER, Role.ADMIN, Role.TRAINER)
def update_project_proposal(project_id):
    data = request.get_json(silent=True) or {}
    submit_for_approval = data.get("submit_for_approval", True)
    project, err = ProjectService.update_project_proposal(request.current_user, project_id, data, submit_for_approval)
    if err:
        return jsonify({"error": err}), 400
    return jsonify({"success": True, "project": serialize_doc(project), "message": "Proposal updated successfully."})


@api_bp.route("/projects/<project_id>/membership-change-request", methods=["POST"])
@require_roles(Role.TEAM_LEAD, Role.MANAGER, Role.ADMIN, Role.TRAINER)
def submit_membership_change_request(project_id):
    data = request.get_json(silent=True) or {}
    add_members = data.get("add_members", [])
    remove_members = data.get("remove_members", [])
    reason = data.get("reason", "")
    req, err = ProjectService.submit_membership_change_request(request.current_user, project_id, add_members, remove_members, reason)
    if err:
        return jsonify({"error": err}), 400
    return jsonify({"success": True, "request": serialize_doc(req), "message": "Membership change request submitted to Manager."}), 201


@api_bp.route("/projects/<project_id>/membership-change-request/<request_id>/review", methods=["POST"])
@require_roles(Role.MANAGER, Role.ADMIN)
def review_membership_change_request(project_id, request_id):
    data = request.get_json(silent=True) or {}
    action = data.get("action", "")
    review_notes = data.get("review_notes", "")
    res, err = ProjectService.review_membership_change_request(request.current_user, project_id, request_id, action, review_notes)
    if err:
        return jsonify({"error": err}), 400
    return jsonify({"success": True, "result": serialize_doc(res), "message": f"Membership change request {action.lower()}d."})


@api_bp.route("/projects/<project_id>", methods=["GET"])
@require_auth
def get_project_detail(project_id):
    user = request.current_user
    if user.get("role") == Role.HR:
        return jsonify({"error": "Access Denied: HR personnel are restricted from project operations and project APIs."}), 403

    db = get_db()
    project = db.projects.find_one({"project_id": project_id})
    if not project:
        return jsonify({"error": "Project not found."}), 404

    # Strict Employee isolation:
    # Employees cannot view pending proposals, drafts, or projects they are not active members of
    if user["role"] == Role.EMPLOYEE:
        if project.get("status") not in ("APPROVED", "ACTIVE", "IN_PROGRESS", "ON_HOLD", "COMPLETED") or user["employee_id"] not in project.get("members", []):
            return jsonify({"error": "Access Denied: This project is not active or you are not an assigned member."}), 403

    member_ids = project.get("members", [])
    members_docs = list(db.users.find(
        {"employee_id": {"$in": member_ids}},
        {"employee_id": 1, "full_name": 1, "department": 1, "designation": 1, "email": 1, "role": 1, "skills": 1}
    ))
    project["member_details"] = members_docs

    # Proposed/Selected member details
    sel_ids = project.get("selected_members", [])
    if sel_ids:
        sel_docs = list(db.users.find(
            {"employee_id": {"$in": sel_ids}},
            {"employee_id": 1, "full_name": 1, "department": 1, "designation": 1, "email": 1, "role": 1, "skills": 1}
        ))
        for u in sel_docs:
            u_id = u.get("employee_id")
            active_prjs = db.projects.count_documents({"members": u_id, "status": {"$in": ["ACTIVE", "APPROVED", "IN_PROGRESS"]}})
            active_tsks = db.tasks.count_documents({"assigned_to": u_id, "status": {"$in": ["Pending", "In Progress"]}})
            u["active_projects_count"] = active_prjs
            u["active_tasks_count"] = active_tsks
            u["availability"] = "Available (0 active)" if active_prjs == 0 else f"{active_prjs} active project(s)"
        project["selected_member_details"] = sel_docs
    else:
        project["selected_member_details"] = []

    # Chat is ONLY accessible / ensured if project has been approved
    is_approved = project.get("is_approved") or (project.get("status") in ("APPROVED", "ACTIVE", "IN_PROGRESS", "ON_HOLD", "COMPLETED"))
    if is_approved:
        try:
            from services.chat_service import ChatService
            ChatService.ensure_project_chat(project)
        except Exception:
            pass
        project["conversation_id"] = f"PRJ-CHAT-{project_id}"
    else:
        project["conversation_id"] = None

    tasks = list(db.tasks.find({"project_id": project_id}))
    return jsonify({
        "project": serialize_doc(project),
        "tasks": serialize_docs(tasks),
        "conversation_id": project.get("conversation_id")
    })


@api_bp.route("/projects/<project_id>/members", methods=["PUT"])
@require_roles(Role.TEAM_LEAD, Role.MANAGER, Role.ADMIN)
def update_project_members(project_id):
    user = request.current_user
    data = request.get_json(silent=True) or {}
    members = data.get("members", [])

    if user.get("role") == Role.TEAM_LEAD:
        # Team Leads must submit membership change request per policy
        db = get_db()
        project = db.projects.find_one({"project_id": project_id})
        if not project:
            return jsonify({"error": "Project not found."}), 404

        current_members = set(project.get("members", []))
        target_members = set([str(m).strip().upper() for m in members if str(m).strip()])
        add_members = list(target_members - current_members)
        remove_members = list(current_members - target_members)

        req, err = ProjectService.submit_membership_change_request(
            user,
            project_id,
            add_members,
            remove_members,
            data.get("reason", "Membership update submitted by Team Lead.")
        )
        if err:
            return jsonify({"error": err}), 400
        return jsonify({
            "success": True,
            "requires_approval": True,
            "message": "Membership change request submitted to Manager for approval.",
            "request": serialize_doc(req)
        })

    # Managers and Admins can directly update
    project, err = ProjectService.update_project_members(user, project_id, members)
    if err:
        return jsonify({"error": err}), 400
    return jsonify({"success": True, "project": serialize_doc(project)})


@api_bp.route("/projects/<project_id>", methods=["PUT"])
@require_roles(Role.TEAM_LEAD, Role.MANAGER, Role.ADMIN, Role.HR_MANAGER, Role.ORGANIZATION, Role.TRAINER)
def edit_project_endpoint(project_id):
    data = request.get_json(silent=True) or {}
    project, err = ProjectService.edit_project(request.current_user, project_id, data)
    if err:
        return jsonify({"error": err}), 403 if "Unauthorized" in err else 400
    return jsonify({"success": True, "project": serialize_doc(project)})


@api_bp.route("/projects/<project_id>", methods=["DELETE"])
@require_roles(Role.TEAM_LEAD, Role.MANAGER, Role.ADMIN, Role.HR_MANAGER, Role.ORGANIZATION)
def delete_project_endpoint(project_id):
    data = request.get_json(silent=True) or {}
    reason = data.get("reason", "")
    success, msg = ProjectService.delete_or_archive_project(request.current_user, project_id, reason)
    if not success:
        return jsonify({"error": msg}), 403 if "Unauthorized" in msg else 400
    return jsonify({"success": True, "message": msg})


@api_bp.route("/projects/dummy-candidates", methods=["GET"])
@require_roles(Role.MANAGER, Role.ADMIN, Role.ORGANIZATION)
def get_dummy_candidates_endpoint():
    candidates = ProjectService.get_dummy_projects_for_review(request.current_user)
    return jsonify({"candidates": serialize_docs(candidates)})


@api_bp.route("/tasks", methods=["GET"])
@require_auth
def get_user_tasks():
    user = request.current_user
    if user.get("role") == Role.HR:
        return jsonify({"error": "Access Denied: HR personnel are restricted from task operations."}), 403
    db = get_db()
    tasks = ProjectService.get_user_tasks(user)
    # Enrich with project title if available
    project_ids = list({t.get("project_id") for t in tasks if t.get("project_id")})
    projects_cursor = db.projects.find(
        {"project_id": {"$in": project_ids}},
        {"project_id": 1, "title": 1, "priority": 1, "status": 1}
    )
    proj_map = {p["project_id"]: p for p in projects_cursor}
    for t in tasks:
        p = proj_map.get(t.get("project_id"))
        if p:
            t["project_title"] = p.get("title")
            t["project_priority"] = p.get("priority")
            t["project_status"] = p.get("status")
    return jsonify({"tasks": serialize_docs(tasks)})


@api_bp.route("/tasks", methods=["POST"])
@require_roles(Role.TEAM_LEAD, Role.MANAGER, Role.ADMIN, Role.HR_MANAGER, Role.ORGANIZATION, Role.TRAINER)
def create_task():
    data = request.get_json(silent=True) or {}
    task, err = ProjectService.create_task(request.current_user, data)
    if err:
        return jsonify({"error": err}), 400
    return jsonify({"success": True, "task": serialize_doc(task)}), 201


@api_bp.route("/tasks/<task_id>/progress", methods=["PUT"])
@require_auth
def update_task_progress(task_id):
    user = request.current_user
    if user.get("role") == Role.HR:
        return jsonify({"error": "Access Denied: HR personnel are restricted from task operations."}), 403

    data = request.get_json(silent=True) or {}
    progress = data.get("progress_percentage", 0)
    status = data.get("status")
    notes = data.get("notes")

    task, err = ProjectService.update_task_progress(
        actor=request.current_user,
        task_id=task_id,
        progress_percentage=progress,
        status=status,
        notes=notes
    )
    if err:
        return jsonify({"error": err}), 400
    return jsonify({"success": True, "task": serialize_doc(task)})


@api_bp.route("/teams", methods=["POST"])
@require_roles(Role.TEAM_LEAD, Role.MANAGER, Role.ADMIN, Role.HR_MANAGER, Role.ORGANIZATION, Role.TRAINER)
def create_team():
    data = request.get_json(silent=True) or {}
    team, err = ProjectService.create_team(request.current_user, data)
    if err:
        return jsonify({"error": err}), 400
    return jsonify({"success": True, "team": serialize_doc(team)}), 201


# ==========================================
# 3.5 UNIFIED INBOX & CHAT ENDPOINTS
# ==========================================

@api_bp.route("/conversations", methods=["GET"])
@require_auth
def list_conversations():
    user = request.current_user
    filter_type = request.args.get("type")
    search = request.args.get("search")
    from services.chat_service import ChatService
    convs = ChatService.get_user_conversations(user, filter_type=filter_type, search=search)
    return jsonify({"conversations": serialize_docs(convs)})


@api_bp.route("/conversations/<conversation_id>", methods=["GET"])
@require_auth
def get_conversation_detail(conversation_id):
    user = request.current_user
    from services.chat_service import ChatService
    conv, err = ChatService.get_conversation(user, conversation_id)
    if err:
        status_code = 403 if "Access Denied" in err else 404
        return jsonify({"error": err}), status_code
    return jsonify({"conversation": serialize_doc(conv)})


@api_bp.route("/conversations/<conversation_id>/messages", methods=["GET"])
@require_auth
def get_conversation_messages(conversation_id):
    user = request.current_user
    from services.chat_service import ChatService
    limit = request.args.get("limit", 150, type=int)
    messages, err = ChatService.get_messages(user, conversation_id, limit=limit)
    if err:
        status_code = 403 if "Access Denied" in err else 404
        return jsonify({"error": err}), status_code
    return jsonify({"messages": serialize_docs(messages)})


@api_bp.route("/conversations/<conversation_id>/messages", methods=["POST"])
@require_auth
def send_conversation_message(conversation_id):
    user = request.current_user
    data = request.get_json(silent=True) or {}
    content = data.get("content", "").strip()
    from services.chat_service import ChatService
    msg, err = ChatService.send_message(user, conversation_id, content)
    if err:
        status_code = 403 if "Access Denied" in err else 400
        return jsonify({"error": err}), status_code
    return jsonify({"success": True, "message": serialize_doc(msg)}), 201


@api_bp.route("/conversations/direct", methods=["POST"])
@require_auth
def create_direct_conversation():
    actor = request.current_user
    data = request.get_json(silent=True) or {}
    target_id = data.get("recipient_id", "").strip().upper()
    if not target_id:
        return jsonify({"error": "Recipient employee ID is required."}), 400

    db = get_db()
    target_user = db.users.find_one({"employee_id": target_id})
    if not target_user:
        return jsonify({"error": f"Employee '{target_id}' not found."}), 404

    from services.chat_service import ChatService
    try:
        conv = ChatService.get_or_create_direct_chat(actor, target_user)
        return jsonify({"success": True, "conversation": serialize_doc(conv)}), 201
    except ValueError as ve:
        return jsonify({"error": str(ve)}), 400


@api_bp.route("/conversations/project/<project_id>", methods=["GET"])
@require_auth
def get_project_conversation(project_id):
    user = request.current_user
    if user.get("role") in (Role.HR, Role.ADMIN):
        return jsonify({"error": "Access Denied: HR/Admin personnel are restricted from project operations."}), 403

    db = get_db()
    project = db.projects.find_one({"project_id": project_id})
    if not project:
        return jsonify({"error": "Project not found."}), 404

    from services.chat_service import ChatService
    conv = ChatService.ensure_project_chat(project, user)
    # Validate access
    if user["employee_id"] not in conv.get("participant_ids", []):
        if user.get("role") != Role.MANAGER:
            return jsonify({"error": "Access Denied: You are not a member of this project group chat."}), 403
    return jsonify({"conversation": serialize_doc(conv)})


@api_bp.route("/conversations/<conversation_id>/messages/<message_id>/unsend", methods=["POST"])
@api_bp.route("/messages/<message_id>/unsend", methods=["POST"])
@require_auth
def unsend_message_endpoint(message_id, conversation_id=None):
    user = request.current_user
    from services.chat_service import ChatService
    msg, err = ChatService.unsend_message(user, message_id)
    if err:
        status_code = 403 if "Access Denied" in err else 400
        return jsonify({"error": err}), status_code
    return jsonify({"success": True, "message": serialize_doc(msg)}), 200


@api_bp.route("/conversations/<conversation_id>/messages/<message_id>", methods=["DELETE"])
@api_bp.route("/messages/<message_id>/delete", methods=["POST", "DELETE"])
@require_auth
def delete_message_endpoint(message_id, conversation_id=None):
    user = request.current_user
    from services.chat_service import ChatService
    res, err = ChatService.delete_chat_message(user, message_id)
    if err:
        status_code = 403 if "Access Denied" in err else 400
        return jsonify({"error": err}), status_code
    return jsonify({"success": True, "message": "Message deleted successfully.", "result": res}), 200


@api_bp.route("/conversations/<conversation_id>/attachments", methods=["POST"])
@require_auth
def upload_chat_attachment(conversation_id):
    user = request.current_user
    if "file" not in request.files:
        return jsonify({"error": "No file part in the upload request."}), 400
    file_obj = request.files["file"]
    caption = request.form.get("caption", "")
    from services.chat_service import ChatService
    msg, err = ChatService.save_attachment(user, conversation_id, file_obj, caption=caption)
    if err:
        status_code = 403 if "Access Denied" in err else 400
        return jsonify({"error": err}), status_code
    return jsonify({"success": True, "message": serialize_doc(msg)}), 201


@api_bp.route("/conversations/<conversation_id>/attachments/<attachment_id>/download", methods=["GET"])
@require_auth
def download_chat_attachment(conversation_id, attachment_id):
    user = request.current_user
    from services.chat_service import ChatService
    att, err = ChatService.get_attachment_for_download(user, conversation_id, attachment_id)
    if err:
        status_code = 403 if "Access Denied" in err else 404
        return jsonify({"error": err}), status_code

    return send_file(
        att["file_path"],
        mimetype=att.get("mime_type", "application/octet-stream"),
        as_attachment=True,
        download_name=att.get("original_filename", "attachment")
    )


@api_bp.route("/conversations/<conversation_id>", methods=["DELETE"])
@require_auth
def delete_conversation_endpoint(conversation_id):
    user = request.current_user
    data = request.get_json(silent=True) or {}
    confirm_permanent = (
        data.get("confirm_permanent") is True or
        data.get("confirm") is True or
        request.args.get("confirm", "").lower() in ("true", "1") or
        request.args.get("confirm_permanent", "").lower() in ("true", "1")
    )
    from services.chat_service import ChatService
    res, err = ChatService.delete_conversation(user, conversation_id, confirm_permanent=confirm_permanent)
    if err:
        if "Access Denied" in err or "Unauthorized" in err:
            status_code = 403
        elif "not found" in err.lower():
            status_code = 404
        else:
            status_code = 400
        return jsonify({"error": err}), status_code

    return jsonify({"success": True, **res}), 200


@api_bp.route("/conversations/<conversation_id>/archive", methods=["POST"])
@require_auth
def archive_conversation_endpoint(conversation_id):
    user = request.current_user
    from services.chat_service import ChatService
    res, err = ChatService.archive_project_chat(user, conversation_id)
    if err:
        if "Access Denied" in err or "Unauthorized" in err:
            status_code = 403
        elif "not found" in err.lower():
            status_code = 404
        else:
            status_code = 400
        return jsonify({"error": err}), status_code

    return jsonify({"success": True, **res}), 200


@api_bp.route("/conversations/<conversation_id>/hide", methods=["POST"])
@require_auth
def hide_conversation_endpoint(conversation_id):
    user = request.current_user
    from services.chat_service import ChatService
    res, err = ChatService.hide_conversation(user, conversation_id)
    if err:
        status_code = 403 if "Access Denied" in err else 404
        return jsonify({"error": err}), status_code

    return jsonify({"success": True, **res}), 200


@api_bp.route("/conversations/<conversation_id>/unhide", methods=["POST"])
@require_auth
def unhide_conversation_endpoint(conversation_id):
    user = request.current_user
    from services.chat_service import ChatService
    res, err = ChatService.unhide_conversation(user, conversation_id)
    if err:
        status_code = 403 if "Access Denied" in err else 404
        return jsonify({"error": err}), status_code

    return jsonify({"success": True, **res}), 200


# ==========================================
# CHAT ROOM EMAIL COMPOSITION (INBOX ONLY)
# ==========================================

@api_bp.route("/chat/authorized-email-recipients", methods=["GET"])
@require_auth
def get_chat_authorized_email_recipients():
    """
    Returns verified company employees with valid company email addresses
    for authorized email composition inside Chat Room only.
    """
    actor = request.current_user
    db = get_db()
    users = list(db.users.find(
        {"is_active": True, "email": {"$exists": True, "$ne": None}},
        {"employee_id": 1, "full_name": 1, "email": 1, "official_email": 1, "department": 1, "role": 1}
    ).sort("full_name", 1))

    recipients = []
    for u in users:
        email = (u.get("official_email") or u.get("email") or "").strip()
        if email and "@" in email:
            recipients.append({
                "employee_id": u.get("employee_id"),
                "full_name": u.get("full_name"),
                "email": email,
                "role": u.get("role"),
                "department": u.get("department", "Company")
            })

    return jsonify({"recipients": recipients, "count": len(recipients)}), 200


@api_bp.route("/chat/compose-email", methods=["POST"])
@require_auth
def chat_compose_email():
    """
    Secure Email Composition inside Chat Room only.
    Dispatches via ExternalNotificationService, records audit log, and returns real provider status.
    """
    actor = request.current_user
    db = get_db()
    data = request.get_json(silent=True) or {}

    to_email = (data.get("to") or data.get("to_email") or "").strip().lower()
    cc_email = (data.get("cc") or data.get("cc_email") or "").strip().lower() or None
    subject = (data.get("subject") or "").strip()
    message = (data.get("message") or data.get("body") or "").strip()

    if not to_email or "@" not in to_email:
        return jsonify({"error": "A valid recipient company email address is required."}), 400
    if not subject:
        return jsonify({"error": "Email subject is required."}), 400
    if not message:
        return jsonify({"error": "Email message body is required."}), 400

    # Verify recipient is an authorized company employee
    target_user = db.users.find_one({
        "$or": [{"email": to_email}, {"official_email": to_email}],
        "is_active": True
    })
    if not target_user:
        return jsonify({"error": f"Recipient '{to_email}' is not a registered, active company employee."}), 403

    if cc_email:
        cc_user = db.users.find_one({
            "$or": [{"email": cc_email}, {"official_email": cc_email}],
            "is_active": True
        })
        if not cc_user:
            return jsonify({"error": f"CC recipient '{cc_email}' is not a registered company employee."}), 403

    from services.external_notification_service import ExternalNotificationService
    idempotency_key = f"CHAT_EMAIL_{actor['employee_id']}_{int(now_utc().timestamp())}"

    dispatch_res = ExternalNotificationService.send_email(
        recipient_email=to_email,
        subject=subject,
        body=message,
        recipient_id=target_user.get("employee_id"),
        category="CHAT_ENTERPRISE_EMAIL",
        idempotency_key=idempotency_key,
        cc_email=cc_email
    )

    provider_status = dispatch_res.get("status", "FAILED")
    if provider_status == "DELIVERED":
        email_status = "SENT"
        status_text = f"Email successfully delivered to {to_email} via company SMTP."
    elif provider_status == "SIMULATED_NO_CREDENTIALS":
        email_status = "SIMULATED"
        status_text = f"Email simulated: external SMTP credentials not configured. Recorded for {to_email}."
    else:
        email_status = "FAILED"
        status_text = dispatch_res.get("failure_reason") or "Failed to deliver email."

    email_log = {
        "email_id": f"EML-CHAT-{int(now_utc().timestamp())}",
        "sender_id": actor["employee_id"],
        "sender_name": actor.get("full_name"),
        "sender_email": actor.get("email"),
        "recipient_id": target_user.get("employee_id"),
        "recipient_name": target_user.get("full_name"),
        "to": to_email,
        "cc": cc_email or "",
        "subject": subject,
        "message": message,
        "status": email_status,
        "provider_status": provider_status,
        "status_text": status_text,
        "created_at": now_utc()
    }
    db.external_message_logs.insert_one(email_log)

    try:
        AuditService.log_action(
            actor=actor,
            action="CHAT_COMPOSE_EMAIL",
            target_type="email",
            target_id=target_user["employee_id"],
            details={"to": to_email, "cc": cc_email, "subject": subject, "status": email_status}
        )
    except Exception as e:
        logger.warning("Audit logging error in chat email: %s", e)

    return jsonify({
        "success": email_status in ("SENT", "SIMULATED"),
        "status": email_status,
        "provider_status": provider_status,
        "message": status_text,
        "record": serialize_doc(email_log)
    }), 200


@api_bp.route("/birthdays/monthly", methods=["GET"])
@require_auth
def get_monthly_birthdays_api():
    from services.birthday_service import BirthdayService
    from utils.timezone import now_local
    import calendar
    current_dt = now_local()
    year = request.args.get("year", default=current_dt.year, type=int)
    month = request.args.get("month", default=current_dt.month, type=int)
    
    birthdays = BirthdayService.get_monthly_birthdays(year=year, month=month)
    today_birthdays = BirthdayService.get_today_birthdays(target_local_dt=current_dt) if month == current_dt.month and year == current_dt.year else []
    upcoming_birthdays = BirthdayService.get_upcoming_birthdays(target_local_dt=current_dt) if month == current_dt.month and year == current_dt.year else []

    return jsonify({
        "success": True,
        "year": year,
        "month": month,
        "month_name": calendar.month_name[month],
        "birthdays": birthdays,
        "today_birthdays": today_birthdays,
        "upcoming_birthdays": upcoming_birthdays,
        "total_celebrants": len(birthdays)
    })


@api_bp.route("/birthdays/user-status", methods=["GET"])
@require_auth
def get_user_birthday_status_api():
    """Returns celebration metadata if the current user celebrates their birthday today."""
    from services.birthday_service import BirthdayService
    status = BirthdayService.get_user_birthday_status(request.current_user)
    return jsonify(status), 200


@api_bp.route("/festivals/current", methods=["GET"])
@require_auth
def get_current_festival_theme_api():
    """Returns the current active cultural festival theme, accents, and greetings."""
    from services.festival_service import FestivalService
    active_theme = FestivalService.get_active_festival()
    return jsonify({"success": True, "active": bool(active_theme), "festival": active_theme}), 200


@api_bp.route("/birthdays/preview", methods=["GET"])
@require_roles(Role.HR, Role.MANAGER, Role.HR_MANAGER, Role.ADMIN)
def preview_birthday_announcement_api():
    from services.birthday_service import BirthdayService
    year = request.args.get("year", type=int)
    month = request.args.get("month", type=int)
    preview = BirthdayService.preview_monthly_announcement(year=year, month=month)
    return jsonify(preview)


@api_bp.route("/birthdays/trigger-check", methods=["POST"])
@require_roles(Role.HR, Role.MANAGER, Role.HR_MANAGER, Role.ADMIN)
def trigger_birthday_check_api():
    """
    HR-only administrative action to generate safe in-app birthday notifications
    without sending live external messages to employees.
    """
    from services.birthday_service import BirthdayService
    from services.notification_service import NotificationService
    from utils.timezone import now_local
    import calendar

    data = request.get_json(silent=True) or {}
    action = data.get("action", "monthly")  # "monthly", "daily", or "test"
    current_dt = now_local()

    if action == "monthly":
        notif = BirthdayService.check_and_send_monthly_birthday_announcement(target_local_dt=current_dt, force=True)
        return jsonify({
            "success": True,
            "action": "monthly",
            "message": f"Monthly announcement generated for {calendar.month_name[current_dt.month]} {current_dt.year}.",
            "notification": serialize_doc(notif) if notif else None
        })
    elif action == "daily":
        notifs = BirthdayService.check_and_send_birthday_notifications(target_local_dt=current_dt, force=True)
        return jsonify({
            "success": True,
            "action": "daily",
            "message": f"Daily birthday checks completed. Dispatched {len(notifs)} celebration(s).",
            "notifications": serialize_docs(notifs) if notifs else []
        })
    elif action == "test":
        # Safe test in-app notification strictly for HR verification
        notif = NotificationService.create_notification(
            title="🎂 [TEST] November Birthday Announcement",
            message="This is a test birthday notification generated by HR to verify in-app notification bell functionality.",
            category="BIRTHDAY",
            recipient_id=request.current_user["employee_id"],
            link="/birthdays",
            priority="HIGH"
        )
        return jsonify({
            "success": True,
            "action": "test",
            "message": "Test birthday notification generated successfully.",
            "notification": serialize_doc(notif)
        })

    return jsonify({"error": f"Unknown action: {action}"}), 400


@api_bp.route("/notifications/external-logs", methods=["GET"])
@require_roles(Role.HR, Role.ADMIN)
def get_external_notification_logs():
    from services.external_notification_service import ExternalNotificationService
    recipient_id = request.args.get("recipient_id")
    channel = request.args.get("channel")
    logs = ExternalNotificationService.get_delivery_logs(recipient_id=recipient_id, channel=channel)
    return jsonify({"logs": serialize_docs(logs)})


# ==========================================
# 4. COMPLAINT & LEGAL COMMUNICATION ENDPOINTS
# ==========================================

@api_bp.route("/complaints", methods=["GET"])
@require_auth
def list_complaints():
    user = request.current_user
    if user.get("role") in (Role.MANAGER, Role.TEAM_LEAD, "hr_manager", "organization"):
        return jsonify({
            "error": "Access Denied: Team Leads and Managers are strictly forbidden from viewing confidential HR complaints.",
            "complaints": []
        }), 403

    complaints = ComplaintService.get_user_complaints(user)
    return jsonify({"complaints": serialize_docs(complaints)})


@api_bp.route("/complaints", methods=["POST"])
@require_auth
def submit_complaint():
    data = request.get_json(silent=True) or {}
    complaint, err = ComplaintService.submit_complaint(request.current_user, data)
    if err:
        return jsonify({"error": err}), 400
    return jsonify({"success": True, "complaint": serialize_doc(complaint)}), 201


@api_bp.route("/complaints/<complaint_id>", methods=["GET"])
@require_auth
def get_complaint_detail(complaint_id):
    db = get_db()
    complaint = db.complaints.find_one({"complaint_id": complaint_id})
    if not complaint:
        return jsonify({"error": "Complaint not found."}), 404

    if not can_access_complaint(request.current_user, complaint):
        return jsonify({"error": "Access Denied: You do not have permission to view this complaint."}), 403

    return jsonify({"complaint": serialize_doc(complaint)})


@api_bp.route("/complaints/<complaint_id>/respond", methods=["POST"])
@require_auth
def respond_to_complaint(complaint_id):
    data = request.get_json(silent=True) or {}
    message = data.get("message")
    new_status = data.get("status")

    complaint, err = ComplaintService.add_response(
        actor=request.current_user,
        complaint_id=complaint_id,
        message=message,
        new_status=new_status
    )
    if err:
        return jsonify({"error": err}), 400
    return jsonify({"success": True, "complaint": serialize_doc(complaint)})


@api_bp.route("/complaints/<complaint_id>/status", methods=["PUT"])
@require_roles(Role.HR)
def update_complaint_status(complaint_id):
    data = request.get_json(silent=True) or {}
    new_status = data.get("status")

    complaint, err = ComplaintService.update_status(request.current_user, complaint_id, new_status)
    if err:
        return jsonify({"error": err}), 400
    return jsonify({"success": True, "complaint": serialize_doc(complaint)})


# ==========================================
# 5. NOTIFICATIONS ENDPOINTS
# ==========================================

@api_bp.route("/notifications", methods=["GET"])
@require_auth
def list_notifications():
    unread_only = request.args.get("unread_only", "false").lower() == "true"
    notifs = NotificationService.get_user_notifications(request.current_user, unread_only=unread_only)
    serialized = serialize_docs(notifs)
    for n in serialized:
        if "_id" in n and "id" not in n:
            n["id"] = n["_id"]
    unread_count = sum(1 for n in serialized if not n.get("is_read"))
    return jsonify({
        "notifications": serialized,
        "unread_count": unread_count
    })


@api_bp.route("/notifications/<notif_id>/read", methods=["POST"])
@require_auth
def mark_notification_read(notif_id):
    if not NotificationService.mark_as_read(notif_id, request.current_user):
        return jsonify({"error": "Notification not found or could not be marked as read."}), 404
    return jsonify({"success": True})


@api_bp.route("/notifications/read-all", methods=["POST"])
@require_auth
def mark_all_notifications_read():
    count = NotificationService.mark_all_as_read(request.current_user)
    return jsonify({"success": True, "count": count})


@api_bp.route("/notifications/broadcast", methods=["POST"])
@require_roles(Role.HR, Role.HR_MANAGER, Role.ORGANIZATION, Role.ADMIN)
def send_broadcast_notification():
    actor = request.current_user
    data = request.get_json(silent=True) or {}
    title = data.get("title", "").strip()
    message = data.get("message", "").strip()
    target_group = data.get("recipient_group", "ALL")

    if not title or not message:
        return jsonify({"error": "Title and message are required."}), 400

    if actor["role"] == Role.HR_MANAGER and target_group not in ("HR", "HR_MANAGERS"):
        return jsonify({"error": "HR Manager can only broadcast announcements to HR users."}), 403

    notif = NotificationService.create_notification(
        title=title,
        message=message,
        category="ANNOUNCEMENT",
        recipient_group=target_group
    )
    return jsonify({"success": True, "notification": serialize_doc(notif)}), 201


# ==========================================
# 6. REPORTS & EXPORTS
# ==========================================

@api_bp.route("/reports/attendance/csv", methods=["GET"])
@require_auth
def export_attendance_csv():
    actor = request.current_user
    role = normalize_role(actor.get("role"))
    date_str = request.args.get("date", get_local_date_str())

    if role == Role.EMPLOYEE:
        records = [AttendanceService.get_employee_daily_record(actor["employee_id"], date_str)]
        records = [r for r in records if r]
    elif role in (Role.TL, Role.MANAGER):
        overview = AttendanceService.get_team_attendance_overview(actor, date_str)
        records = overview.get("records", [])
    elif role == Role.HR:
        overview = AttendanceService.get_hr_monitoring_overview(date_str)
        records = overview.get("records", [])
    elif role == Role.ADMIN:
        overview = AttendanceService.get_hr_manager_attendance_overview(date_str)
        records = overview.get("records", [])
    else:
        records = []

    csv_data = ExportService.export_attendance_csv(records)
    return Response(
        csv_data,
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename=attendance_{date_str}.csv"}
    )


@api_bp.route("/reports/attendance/excel", methods=["GET"])
@require_auth
def export_attendance_excel():
    actor = request.current_user
    role = normalize_role(actor.get("role"))
    date_str = request.args.get("date", get_local_date_str())

    if role == Role.EMPLOYEE:
        records = [AttendanceService.get_employee_daily_record(actor["employee_id"], date_str)]
        records = [r for r in records if r]
    elif role in (Role.TL, Role.MANAGER):
        overview = AttendanceService.get_team_attendance_overview(actor, date_str)
        records = overview.get("records", [])
    elif role == Role.HR:
        overview = AttendanceService.get_hr_monitoring_overview(date_str)
        records = overview.get("records", [])
    elif role == Role.ADMIN:
        overview = AttendanceService.get_hr_manager_attendance_overview(date_str)
        records = overview.get("records", [])
    else:
        records = []

    stream = ExportService.export_attendance_excel(records)
    return Response(
        stream.getvalue(),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=attendance_{date_str}.xlsx"}
    )


# ==========================================
# 7. AUDIT LOGS & SETTINGS
# ==========================================

@api_bp.route("/audit-logs", methods=["GET"])
@api_bp.route("/audit/logs", methods=["GET"])
@require_roles(Role.HR, Role.ADMIN)
def get_audit_logs():
    actor = request.current_user
    limit = int(request.args.get("limit", 100))
    skip = int(request.args.get("skip", 0))
    action = request.args.get("action") or None
    filter_role = request.args.get("role") or None
    target_type = request.args.get("target_type") or None
    date_from = request.args.get("date_from") or None
    date_to = request.args.get("date_to") or None
    search = request.args.get("search") or None

    logs = AuditService.get_audit_logs(
        actor_role=normalize_role(actor.get("role")),
        limit=limit,
        skip=skip,
        action=action,
        filter_role=filter_role,
        target_type=target_type,
        date_from=date_from,
        date_to=date_to,
        search=search,
    )
    return jsonify({"audit_logs": serialize_docs(logs)})


@api_bp.route("/settings", methods=["GET", "PUT"])
@require_roles(Role.HR, Role.ADMIN)
def handle_settings():
    db = get_db()
    if request.method == "GET":
        settings = list(db.organization_settings.find())
        return jsonify({"settings": serialize_docs(settings)})

    if normalize_role(request.current_user.get("role")) != Role.ADMIN:
        return jsonify({"error": "Access Denied: Only authorized Admin can configure system and organizational settings."}), 403

    data = request.get_json(silent=True) or {}
    key = data.get("key", "attendance_policy")
    value = data.get("value", {})

    db.organization_settings.update_one(
        {"key": key},
        {"$set": {"value": value, "updated_at": now_utc()}},
        upsert=True
    )
    AuditService.log_action(
        actor=request.current_user,
        action="UPDATE_SETTINGS",
        target_type="setting",
        target_id=key,
        details={"value": value}
    )
    return jsonify({"success": True, "message": "Settings updated successfully."})


# ==========================================
# 8. WORK DIARY ENDPOINTS (STRICTLY PRIVATE)
# ==========================================

@api_bp.route("/work-diary/daily", methods=["GET"])
@require_auth
def get_daily_work_diary():
    actor = request.current_user
    date_str = request.args.get("date", get_local_date_str())
    data = WorkDiaryService.get_daily_diary(actor["employee_id"], date_str)
    return jsonify(data)


@api_bp.route("/work-diary/entries", methods=["POST"])
@require_auth
def create_work_diary_entry():
    actor = request.current_user
    payload = request.get_json(silent=True) or {}
    
    # Strictly prevent unauthorized user impersonation
    submitted_emp_id = payload.get("employee_id")
    if submitted_emp_id and submitted_emp_id != actor["employee_id"]:
        return jsonify({"error": "Unauthorized: Cannot create work diary entries on behalf of another employee."}), 403

    act_title = (payload.get("activity_title") or payload.get("title") or payload.get("summary") or "").strip()
    work_desc = (payload.get("work_description") or payload.get("description") or payload.get("summary") or "").strip()
    if not act_title and not work_desc:
        return jsonify({"error": "Activity title or work description is required."}), 400

    entry = WorkDiaryService.create_entry(
        employee_id=actor["employee_id"],
        employee_name=actor.get("full_name", "Employee"),
        payload=payload
    )
    return jsonify({"message": "Work diary entry created successfully.", "entry": entry}), 201


@api_bp.route("/work-diary/entries/<diary_id>", methods=["PUT"])
@require_auth
def update_work_diary_entry(diary_id):
    actor = request.current_user
    payload = request.get_json(silent=True) or {}
    
    # Strictly prevent unauthorized user impersonation
    submitted_emp_id = payload.get("employee_id")
    if submitted_emp_id and submitted_emp_id != actor["employee_id"]:
        return jsonify({"error": "Unauthorized: Cannot edit work diary entries on behalf of another employee."}), 403

    try:
        updated = WorkDiaryService.update_entry(
            employee_id=actor["employee_id"],
            diary_id=diary_id,
            payload=payload
        )
        return jsonify({"message": "Work diary entry updated successfully.", "entry": updated}), 200
    except KeyError as e:
        return jsonify({"error": str(e)}), 404
    except PermissionError as e:
        return jsonify({"error": str(e)}), 403
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@api_bp.route("/work-diary/entries/<diary_id>", methods=["DELETE"])
@require_auth
def delete_work_diary_entry(diary_id):
    actor = request.current_user
    try:
        WorkDiaryService.delete_entry(
            employee_id=actor["employee_id"],
            diary_id=diary_id
        )
        return jsonify({"message": "Work diary entry deleted successfully."}), 200
    except KeyError as e:
        return jsonify({"error": str(e)}), 404
    except PermissionError as e:
        return jsonify({"error": str(e)}), 403


@api_bp.route("/work-diary/monthly", methods=["GET"])
@require_auth
def get_monthly_work_diary():
    actor = request.current_user
    month_str = request.args.get("month", get_local_date_str()[:7])
    data = WorkDiaryService.get_monthly_diary(actor["employee_id"], month_str)
    return jsonify(data)


@api_bp.route("/work-diary/export/excel", methods=["GET"])
@require_auth
def export_work_diary_excel():
    actor = request.current_user
    filter_type = request.args.get("type", "daily").lower()
    
    if filter_type == "daily":
        date_or_month = request.args.get("date", get_local_date_str())
        filename = f"work_diary_{actor['employee_id']}_{date_or_month}.xlsx"
    else:
        filter_type = "monthly"
        date_or_month = request.args.get("month", get_local_date_str()[:7])
        filename = f"work_diary_{actor['employee_id']}_{date_or_month}.xlsx"

    stream = WorkDiaryService.export_diary_excel(
        employee_id=actor["employee_id"],
        employee_name=actor.get("full_name", "Employee"),
        filter_type=filter_type,
        date_or_month=date_or_month
    )
    return Response(
        stream.getvalue(),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@api_bp.route("/work-diary/team", methods=["GET"])
@require_roles(Role.TEAM_LEAD, Role.MANAGER, Role.HR, Role.ADMIN, Role.HR_MANAGER, Role.ORGANIZATION, Role.TRAINER)
def get_team_work_diaries():
    actor = request.current_user
    date_str = request.args.get("date", get_local_date_str())
    try:
        data = WorkDiaryService.get_team_work_diaries(actor, date_str)
        return jsonify(data), 200
    except PermissionError as e:
        return jsonify({"error": str(e)}), 403
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/work-diary/<diary_id>/feedback", methods=["POST"])
@require_roles(Role.TEAM_LEAD, Role.MANAGER, Role.HR, Role.ADMIN, Role.HR_MANAGER, Role.ORGANIZATION, Role.TRAINER)
def add_work_diary_feedback(diary_id):
    actor = request.current_user
    payload = request.get_json(silent=True) or {}
    comment_text = payload.get("comment", "")
    try:
        updated = WorkDiaryService.add_review_comment(actor, diary_id, comment_text)
        return jsonify({"message": "Feedback recorded successfully.", "entry": updated}), 200
    except KeyError as e:
        return jsonify({"error": str(e)}), 404
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except PermissionError as e:
        return jsonify({"error": str(e)}), 403
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ==========================================
# 9. LEAVE & EARLY PERMISSION ENDPOINTS
# ==========================================

@api_bp.route("/leaves/my", methods=["GET"])
@api_bp.route("/leaves/my-requests", methods=["GET"])
@require_auth
def get_my_leave_requests():
    actor = request.current_user
    status_filter = request.args.get("status", "ALL")
    data = LeaveService.get_employee_requests(actor["employee_id"], status_filter)
    return jsonify(data)


@api_bp.route("/leaves/apply", methods=["POST"])
@require_auth
def apply_leave():
    actor = request.current_user
    payload = request.get_json(silent=True) or {}
    doc, err = LeaveService.apply_leave(actor, payload)
    if err:
        return jsonify({"error": err}), 400
    return jsonify({"message": "Leave application submitted successfully.", "request": doc}), 201


@api_bp.route("/leaves/permission", methods=["POST"])
@require_auth
def apply_permission():
    actor = request.current_user
    payload = request.get_json(silent=True) or {}
    doc, err = LeaveService.apply_permission(actor, payload)
    if err:
        return jsonify({"error": err}), 400
    return jsonify({"message": "Early exit permission submitted successfully.", "request": doc}), 201


@api_bp.route("/leaves/my-requests/<request_id>", methods=["DELETE"])
@api_bp.route("/leaves/cancel/<request_id>", methods=["DELETE", "POST"])
@require_auth
def cancel_leave_request(request_id):
    actor = request.current_user
    success, err = LeaveService.cancel_request(actor, request_id)
    if err:
        return jsonify({"error": err}), 403 if ("Access Denied" in err or "Unauthorized" in err) else 400
    return jsonify({"message": "Request cancelled successfully."}), 200


@api_bp.route("/leaves/all", methods=["GET"])
@require_roles(Role.TEAM_LEAD, Role.MANAGER, Role.ADMIN, Role.ORGANIZATION, Role.TRAINER, Role.HR)
def get_all_leave_requests():
    actor = request.current_user
    status_filter = request.args.get("status", "ALL")
    req_type = request.args.get("type", "ALL")
    data = LeaveService.get_all_requests_for_reviewer(actor, status_filter, req_type)
    return jsonify(data)


@api_bp.route("/leaves/verify/<request_id>", methods=["POST"])
@api_bp.route("/leaves/<request_id>/approve", methods=["POST"])
@api_bp.route("/leaves/<request_id>/reject", methods=["POST"])
@require_roles(Role.TEAM_LEAD, Role.MANAGER, Role.ADMIN)
def verify_leave_request(request_id):
    actor = request.current_user
    payload = request.get_json(silent=True) or {}
    decision = payload.get("decision", "")
    if not decision:
        if request.path.endswith("/approve"):
            decision = "Approved"
        elif request.path.endswith("/reject"):
            decision = "Rejected"
    remarks = payload.get("remarks", "")
    updated, err = LeaveService.verify_request(actor, request_id, decision, remarks)
    if err:
        is_auth_err = (
            err.startswith("Unauthorized")
            or err.startswith("Access Denied")
            or err.startswith("Only authorized")
        )
        return jsonify({"error": err}), 403 if is_auth_err else 400
    return jsonify({"message": f"Request {decision.lower()} successfully.", "request": updated}), 200


@api_bp.route("/leaves/<request_id>", methods=["DELETE"])
@require_roles(Role.HR, Role.ADMIN)
def admin_delete_leave_request_route(request_id):
    actor = request.current_user
    success, err = LeaveService.delete_leave_request(actor, request_id)
    if not success:
        code = 403 if err and ("Access Denied" in err or "Unauthorized" in err) else 400
        return jsonify({"error": err}), code
    return jsonify({"message": f"Leave request {request_id} deleted successfully."}), 200


@api_bp.route("/leaves/<request_id>/send-email", methods=["POST"])
@require_roles(Role.MANAGER, Role.ADMIN)
def send_leave_approval_email(request_id):
    actor = request.current_user
    payload = request.get_json(silent=True) or {}
    to_email = payload.get("to") or getattr(Config, "HR_EMAIL", "hr.ramya@aisamrat.com")
    cc_email = payload.get("cc", "")
    subject = payload.get("subject", "")
    message = payload.get("message", "")

    result, err = LeaveService.send_approval_email_to_hr(
        sender=actor,
        request_id=request_id,
        to_email=to_email,
        subject=subject,
        message=message,
        cc_email=cc_email
    )
    if err:
        code = 403 if ("Unauthorized" in err or "Access Denied" in err) else 400
        return jsonify({"error": err}), code

    return jsonify(result), 200


@api_bp.route("/leaves/correspondence", methods=["GET"])
@require_roles(Role.HR, Role.ADMIN)
def get_leave_correspondence():
    records = LeaveService.get_leave_correspondence_for_hr()
    return jsonify({"correspondence": records, "count": len(records)}), 200


@api_bp.route("/leaves/ledger/<employee_id>", methods=["GET"])
@require_auth
def get_employee_leave_ledger(employee_id):
    actor = request.current_user
    db = get_db()
    target_user = db.users.find_one({"$or": [{"employee_id": employee_id}, {"emp_id": employee_id}]})
    if not target_user:
        return jsonify({"error": "Employee not found."}), 404

    resolved_target_id = target_user.get("employee_id") or target_user.get("emp_id") or employee_id
    actor_id = (actor.get("employee_id") or actor.get("emp_id") or "").strip().upper()
    is_self = bool(actor_id and resolved_target_id and actor_id == str(resolved_target_id).strip().upper())
    actor_role = normalize_role(actor.get("role"))
    has_scope = (
        is_self
        or actor_role in (Role.ADMIN, Role.HR)
        or (actor_role in (Role.MANAGER, Role.TL) and can_access_employee_record(actor, resolved_target_id))
    )

    if not has_scope:
        return jsonify({"error": "Access Denied: You do not have permission to view this employee's leave ledger."}), 403

    fy = request.args.get("fy") or LeaveService.get_financial_year()
    ledger_data = LeaveService.get_leave_ledger(resolved_target_id, fy)
    return jsonify(ledger_data), 200


@api_bp.route("/leaves/balances", methods=["GET"])
@require_auth
def get_my_leave_balances():
    actor = request.current_user
    fy = request.args.get("fy") or LeaveService.get_financial_year()
    ledger_data = LeaveService.get_leave_ledger(actor["employee_id"], fy)
    return jsonify(ledger_data), 200


@api_bp.route("/leaves/policies", methods=["GET"])
@require_auth
def get_leave_policies():
    """Returns all standard and progressive leave policies configured in the HRMS."""
    policies = LeaveService.get_all_leave_policies()
    progressive = LeaveService.get_progressive_policies()
    return jsonify({
        "policies": policies,
        "progressive_policies": progressive,
        "financial_year": LeaveService.get_financial_year()
    }), 200


# ==========================================
# 9b. WORK FROM HOME (WFH) ENDPOINTS
# Workflow: Employee -> Manager -> Employee & HR Notified
# ==========================================

@api_bp.route("/wfh/request", methods=["POST"])
@require_auth
def request_wfh():
    actor = request.current_user
    payload = request.get_json(silent=True) or {}
    doc, err = WFHService.request_wfh(actor, payload)
    if err:
        return jsonify({"error": err}), 400
    return jsonify({"success": True, "message": "WFH request submitted successfully.", "request": doc}), 201


@api_bp.route("/wfh/my", methods=["GET"])
@require_auth
def get_my_wfh():
    actor = request.current_user
    reqs = WFHService.get_my_wfh(actor["employee_id"])
    return jsonify({"requests": reqs, "count": len(reqs)}), 200


@api_bp.route("/wfh/pending", methods=["GET"])
@require_roles(Role.MANAGER, Role.ADMIN, "organization")
def get_pending_wfh():
    actor = request.current_user
    reqs = WFHService.get_pending_wfh_for_manager(actor)
    return jsonify({"requests": reqs, "count": len(reqs)}), 200


@api_bp.route("/wfh/<request_id>/review", methods=["POST"])
@require_roles(Role.MANAGER, Role.ADMIN, "organization")
def review_wfh(request_id):
    actor = request.current_user
    payload = request.get_json(silent=True) or {}
    decision = payload.get("decision", "")
    remarks = payload.get("remarks", "")
    updated, err = WFHService.review_wfh(actor, request_id, decision, remarks)
    if err:
        status_code = 403 if "Unauthorized" in err else 400
        return jsonify({"error": err}), status_code
    return jsonify({"success": True, "message": f"WFH request {decision.lower()} successfully.", "request": updated}), 200


@api_bp.route("/wfh/all", methods=["GET"])
@require_roles(Role.HR, Role.MANAGER, Role.ADMIN, "organization", "hr_manager")
def get_all_wfh():
    status_filter = request.args.get("status")
    reqs = WFHService.get_all_wfh(status_filter)
    return jsonify({"requests": reqs, "count": len(reqs)}), 200


@api_bp.route("/wfh/team", methods=["GET"])
@require_roles(Role.TEAM_LEAD, "trainer", Role.MANAGER, Role.ADMIN)
def get_team_wfh():
    actor = request.current_user
    reqs = WFHService.get_team_wfh(actor)
    return jsonify({"requests": reqs, "count": len(reqs)}), 200


# ==========================================
# 9c. SHIFT ROSTERING ENDPOINTS
# Workflow: Team Lead proposes -> Manager approves & publishes -> Team notified
# ==========================================

@api_bp.route("/roster/propose", methods=["POST"])
@require_roles(Role.TEAM_LEAD, Role.MANAGER, Role.HR, Role.HR_MANAGER, Role.ADMIN, "trainer", "organization")
def propose_roster():
    actor = request.current_user
    payload = request.get_json(silent=True) or {}
    doc, err = RosterService.propose_roster(actor, payload)
    if err:
        return jsonify({"error": err}), 400
    return jsonify({"success": True, "message": "Shift roster proposed for review.", "roster": doc}), 201


@api_bp.route("/roster/pending", methods=["GET"])
@require_roles(Role.MANAGER, Role.HR, Role.HR_MANAGER, Role.ADMIN, "organization")
def get_pending_rosters():
    actor = request.current_user
    rosters = RosterService.get_pending_rosters_for_manager(actor)
    return jsonify({"rosters": rosters, "count": len(rosters)}), 200


@api_bp.route("/roster/<roster_id>/review", methods=["POST"])
@require_roles(Role.MANAGER, Role.HR, Role.HR_MANAGER, Role.ADMIN, "organization")
def review_roster(roster_id):
    actor = request.current_user
    payload = request.get_json(silent=True) or {}
    decision = payload.get("decision", "")
    remarks = payload.get("remarks", "")
    updated, err = RosterService.review_roster(actor, roster_id, decision, remarks)
    if err:
        status_code = 403 if "Unauthorized" in err else 400
        return jsonify({"error": err}), status_code
    return jsonify({"success": True, "message": f"Roster {decision.lower()} successfully.", "roster": updated}), 200


@api_bp.route("/roster/<roster_id>", methods=["PUT"])
@require_roles(Role.TEAM_LEAD, Role.MANAGER, Role.HR, Role.HR_MANAGER, Role.ADMIN, "organization")
def update_roster_endpoint(roster_id):
    actor = request.current_user
    payload = request.get_json(silent=True) or {}
    updated, err = RosterService.update_roster(actor, roster_id, payload)
    if err:
        status_code = 403 if "Unauthorized" in err else 400
        return jsonify({"error": err}), status_code
    return jsonify({"success": True, "message": "Roster updated successfully.", "roster": updated}), 200


@api_bp.route("/roster/<roster_id>", methods=["DELETE"])
@require_roles(Role.MANAGER, Role.HR, Role.HR_MANAGER, Role.ADMIN, "organization")
def delete_roster_endpoint(roster_id):
    actor = request.current_user
    success, err = RosterService.delete_roster(actor, roster_id)
    if not success or err:
        status_code = 403 if err and "Unauthorized" in err else 400
        return jsonify({"error": err or "Failed to delete roster"}), status_code
    return jsonify({"success": True, "message": "Roster schedule deleted successfully."}), 200


@api_bp.route("/roster/team", methods=["GET"])
@require_auth
def get_team_roster_endpoint():
    team_id = request.args.get("team_id") or request.current_user.get("team_id")
    rosters = RosterService.get_team_rosters(team_id)
    return jsonify({"rosters": rosters, "count": len(rosters)}), 200


@api_bp.route("/roster/my", methods=["GET"])
@require_auth
def get_my_roster_schedule():
    actor = request.current_user
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")
    schedule = RosterService.get_employee_schedule(actor["employee_id"], start_date, end_date)
    return jsonify({"schedule": schedule, "count": len(schedule)}), 200


# ==========================================
# 9d. PERFORMANCE IMPROVEMENT PLAN (PIP) & PROBATION ENDPOINTS
# Workflow: TL proposes -> Manager approves -> HR kicks off -> Employee acknowledges -> TL check-ins -> Manager evaluates -> HR verifies compliance
# ==========================================

@api_bp.route("/pip/propose", methods=["POST"])
@require_roles(Role.TEAM_LEAD, Role.MANAGER, Role.ADMIN, "trainer", "organization")
def propose_pip():
    actor = request.current_user
    payload = request.get_json(silent=True) or {}
    doc, err = PIPService.initiate_proposal(actor, payload)
    if err:
        return jsonify({"error": err}), 400
    return jsonify({"success": True, "message": "PIP proposal submitted for Manager approval.", "pip": doc}), 201


@api_bp.route("/pip/<pip_id>/manager-review", methods=["POST"])
@require_roles(Role.MANAGER, Role.ADMIN, "organization")
def manager_review_pip(pip_id):
    actor = request.current_user
    payload = request.get_json(silent=True) or {}
    decision = payload.get("decision", "")
    remarks = payload.get("remarks", "")
    updated, err = PIPService.manager_review_proposal(actor, pip_id, decision, remarks)
    if err:
        return jsonify({"error": err}), 400
    return jsonify({"success": True, "message": f"PIP proposal {decision.lower()} successfully.", "pip": updated}), 200


@api_bp.route("/pip/<pip_id>/hr-kickoff", methods=["POST"])
@require_roles(Role.HR, Role.ADMIN, "organization", "hr_manager")
def hr_kickoff_pip(pip_id):
    actor = request.current_user
    payload = request.get_json(silent=True) or {}
    guidelines = payload.get("guidelines", "")
    updated, err = PIPService.hr_kickoff(actor, pip_id, guidelines)
    if err:
        return jsonify({"error": err}), 400
    return jsonify({"success": True, "message": "PIP plan officially kicked off.", "pip": updated}), 200


@api_bp.route("/pip/<pip_id>/acknowledge", methods=["POST"])
@require_auth
def employee_acknowledge_pip(pip_id):
    actor = request.current_user
    payload = request.get_json(silent=True) or {}
    comments = payload.get("comments", "")
    updated, err = PIPService.employee_acknowledge(actor, pip_id, comments)
    if err:
        return jsonify({"error": err}), 400
    return jsonify({"success": True, "message": "PIP plan acknowledged.", "pip": updated}), 200


@api_bp.route("/pip/<pip_id>/checkin", methods=["POST"])
@require_roles(Role.TEAM_LEAD, Role.MANAGER, Role.ADMIN, "trainer", "organization")
def log_pip_checkin(pip_id):
    actor = request.current_user
    payload = request.get_json(silent=True) or {}
    notes = payload.get("notes", "")
    rating = payload.get("rating", "Satisfactory")
    updated, err = PIPService.log_checkin(actor, pip_id, notes, rating)
    if err:
        return jsonify({"error": err}), 400
    return jsonify({"success": True, "message": "Milestone check-in recorded.", "pip": updated}), 200


@api_bp.route("/pip/<pip_id>/evaluate", methods=["POST"])
@require_roles(Role.MANAGER, Role.ADMIN, "organization")
def manager_evaluate_pip(pip_id):
    actor = request.current_user
    payload = request.get_json(silent=True) or {}
    outcome = payload.get("outcome", "")
    notes = payload.get("notes", "")
    updated, err = PIPService.manager_evaluate(actor, pip_id, outcome, notes)
    if err:
        return jsonify({"error": err}), 400
    return jsonify({"success": True, "message": "PIP evaluated successfully.", "pip": updated}), 200


@api_bp.route("/pip/<pip_id>/verify-compliance", methods=["POST"])
@require_roles(Role.HR, Role.ADMIN, "organization", "hr_manager")
def hr_verify_compliance_pip(pip_id):
    actor = request.current_user
    payload = request.get_json(silent=True) or {}
    compliance_notes = payload.get("compliance_notes", "")
    updated, err = PIPService.hr_verify_compliance_and_close(actor, pip_id, compliance_notes)
    if err:
        return jsonify({"error": err}), 400
    return jsonify({"success": True, "message": "PIP compliance verified and record closed.", "pip": updated}), 200


@api_bp.route("/pip/list", methods=["GET"])
@require_auth
def list_pips():
    actor = request.current_user
    pips = PIPService.list_pips_for_user(actor)
    return jsonify({"pips": pips, "count": len(pips)}), 200


@api_bp.route("/pip/<pip_id>", methods=["GET"])
@require_auth
def get_pip_detail(pip_id):
    pip = PIPService.get_pip(pip_id)
    if not pip:
        return jsonify({"error": "PIP record not found."}), 404
    return jsonify({"pip": pip}), 200


# ==========================================
# 9e. COMPANY POLICIES & DOCUMENTS ENDPOINTS
# ==========================================

@api_bp.route("/documents/upload", methods=["POST"])
@require_roles(Role.HR, Role.ADMIN)
def upload_company_document():
    actor = request.current_user
    if "file" not in request.files:
        return jsonify({"error": "No file attached."}), 400

    file_obj = request.files["file"]
    form_data = {
        "title": request.form.get("title", ""),
        "category": request.form.get("category", "Company Policy"),
        "description": request.form.get("description", "")
    }

    doc, err = DocumentService.upload_document(actor, file_obj, form_data)
    if err:
        return jsonify({"error": err}), 403 if "Unauthorized" in err else 400
    return jsonify({"success": True, "message": "Document uploaded successfully.", "document": doc}), 201


@api_bp.route("/documents", methods=["GET"])
@require_auth
def list_company_documents():
    category = request.args.get("category")
    docs = DocumentService.list_documents(category)
    return jsonify({"documents": docs, "count": len(docs)}), 200


@api_bp.route("/documents/<doc_id>/download", methods=["GET"])
@require_auth
def download_company_document(doc_id):
    doc, err = DocumentService.get_document_for_download(doc_id)
    if err:
        return jsonify({"error": err}), 404

    return send_file(
        doc["file_path"],
        mimetype=doc.get("mime_type", "application/octet-stream"),
        as_attachment=True,
        download_name=doc.get("original_filename", "document")
    )


@api_bp.route("/documents/<doc_id>", methods=["DELETE"])
@require_roles(Role.HR, Role.ADMIN)
def delete_company_document(doc_id):
    actor = request.current_user
    success, err = DocumentService.delete_document(actor, doc_id)
    if not success:
        return jsonify({"error": err}), 403 if err and "Unauthorized" in err else 400
    return jsonify({"success": True, "message": "Document deleted successfully."}), 200


# ==========================================
# 11. SALARY SLIPS & PAYROLL ENDPOINTS
# ==========================================

@api_bp.route("/salary/slips/<employee_id>", methods=["GET"])
@require_auth
def get_employee_salary_slips(employee_id):
    actor = request.current_user
    db = get_db()
    target_user = db.users.find_one({"$or": [{"employee_id": employee_id}, {"emp_id": employee_id}]})
    if not target_user:
        return jsonify({"error": "Employee not found."}), 404

    if not can_view_salary(actor, target_user):
        return jsonify({"error": "Access Denied: You cannot view this employee's salary."}), 403

    count = request.args.get("count", 6, type=int)
    slips = UserService.get_salary_slips(target_user, count=count)
    return jsonify({"slips": slips})


@api_bp.route("/salary/slips/<employee_id>/<year_month>", methods=["GET"])
@require_auth
def get_single_salary_slip_api(employee_id, year_month):
    actor = request.current_user
    slip, err = UserService.get_single_salary_slip(actor, employee_id, year_month)
    if err or not slip:
        status_code = 403 if err and "Access Denied" in err else 404
        return jsonify({"error": err or "Salary slip not found"}), status_code
    return jsonify({"slip": slip})


@api_bp.route("/salary/slip/<employee_id>/<year_month>/pdf", methods=["GET"])
@api_bp.route("/salary/slips/<employee_id>/<year_month>/pdf", methods=["GET"])
@require_auth
def download_salary_slip_pdf(employee_id, year_month):
    actor = request.current_user
    slip, err = UserService.get_single_salary_slip(actor, employee_id, year_month)
    if err or not slip:
        status_code = 403 if err and "Access Denied" in err else 404
        return jsonify({"error": err or "Salary slip not found"}), status_code

    from services.salary_pdf_service import SalaryPDFService
    pdf_buffer = SalaryPDFService.generate_payslip_pdf(slip)
    filename = f"AI_Samrat_Salary_Slip_{employee_id}_{year_month}.pdf"
    return send_file(
        pdf_buffer,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=filename
    )


# ==========================================
# 12. HOLIDAYS ENDPOINTS
# ==========================================

@api_bp.route("/holidays", methods=["GET"])
@require_auth
def get_holidays():
    from services.holiday_service import HolidayService
    year = request.args.get("year", type=int)
    holidays = HolidayService.get_all_holidays(year=year)
    upcoming = HolidayService.get_upcoming_holidays(limit=8)
    return jsonify({
        "holidays": holidays,
        "upcoming": upcoming
    })


@api_bp.route("/holidays", methods=["POST"])
@require_roles(Role.HR, Role.HR_MANAGER, Role.ORGANIZATION, Role.ADMIN)
def add_holiday():
    actor = request.current_user
    payload = request.get_json(silent=True) or {}
    from services.holiday_service import HolidayService
    holiday, err = HolidayService.add_holiday(
        actor=actor,
        date_str=payload.get("date"),
        name=payload.get("name"),
        holiday_type=payload.get("type", "Public")
    )
    if err:
        return jsonify({"error": err}), 400
    return jsonify({"message": "Holiday added successfully.", "holiday": holiday}), 201


@api_bp.route("/holidays/<holiday_id>", methods=["PUT"])
@require_roles(Role.HR, Role.HR_MANAGER, Role.ORGANIZATION, Role.ADMIN)
def update_holiday_route(holiday_id):
    actor = request.current_user
    payload = request.get_json(silent=True) or {}
    from services.holiday_service import HolidayService
    holiday, err = HolidayService.update_holiday(
        actor=actor,
        holiday_id=holiday_id,
        date_str=payload.get("date"),
        name=payload.get("name"),
        holiday_type=payload.get("type", "Public")
    )
    if err:
        return jsonify({"error": err}), 400
    return jsonify({"success": True, "message": "Holiday updated successfully.", "holiday": holiday}), 200


@api_bp.route("/holidays/<holiday_id>", methods=["DELETE"])
@require_roles(Role.HR, Role.HR_MANAGER, Role.ORGANIZATION, Role.ADMIN)
def delete_holiday(holiday_id):
    actor = request.current_user
    from services.holiday_service import HolidayService
    success, err = HolidayService.delete_holiday(actor, holiday_id)
    if err or not success:
        return jsonify({"error": err or "Failed to delete holiday"}), 400
    return jsonify({"message": "Holiday deleted successfully."}), 200


# ==========================================
# 13. ADMINISTRATIVE EXPORT ARCHIVE
# ==========================================

@api_bp.route("/export/zip", methods=["GET"])
@require_roles(Role.HR, Role.ADMIN)
def export_admin_zip():
    actor = request.current_user
    try:
        zip_buffer = ExportService.export_administrative_zip(actor)
    except PermissionError as e:
        return jsonify({"error": str(e)}), 403
    from datetime import datetime
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"ai_samrat_hrm_export_{stamp}.zip"
    return send_file(
        zip_buffer,
        mimetype="application/zip",
        as_attachment=True,
        download_name=filename
    )


# ==========================================
# 14. SKILL MATRIX & TRAINING ENDPOINTS
# ==========================================

@api_bp.route("/skills/categories", methods=["GET"])
@require_auth
def get_skill_categories():
    from services.skill_service import SkillService
    return jsonify({
        "categories": SkillService.get_categories(),
        "proficiency_levels": SkillService.get_proficiency_levels()
    })


@api_bp.route("/skills/categories", methods=["POST"])
@require_roles(Role.HR, Role.HR_MANAGER, Role.ORGANIZATION, Role.ADMIN)
def add_skill_category():
    actor = request.current_user
    payload = request.get_json(silent=True) or {}
    from services.skill_service import SkillService
    cat, err = SkillService.add_category(actor, payload.get("name"))
    if err:
        return jsonify({"error": err}), 400
    return jsonify({"success": True, "message": "Skill category added successfully.", "category": cat}), 201


@api_bp.route("/skills/categories/<path:category_name>", methods=["DELETE"])
@require_roles(Role.HR, Role.HR_MANAGER, Role.ORGANIZATION, Role.ADMIN)
def delete_skill_category(category_name):
    actor = request.current_user
    from services.skill_service import SkillService
    success, err = SkillService.delete_category(actor, category_name)
    if err or not success:
        return jsonify({"error": err or "Failed to delete skill category."}), 400
    return jsonify({"success": True, "message": f"Category '{category_name}' deleted successfully."}), 200


@api_bp.route("/skills/user/<employee_id>", methods=["GET"])
@require_auth
def matrix_get_user_skills(employee_id):
    actor = request.current_user
    actor_role = actor.get("role")
    actor_id = actor.get("employee_id")

    # Authorization: Self, HR, HR Manager, Trainer, or Team Lead for own team member
    if actor_role == Role.EMPLOYEE and actor_id != employee_id:
        return jsonify({"error": "Access Denied: You cannot view another employee's skills."}), 403

    if actor_role == Role.TEAM_LEAD:
        db = get_db()
        target = db.users.find_one({"employee_id": employee_id})
        if not target or target.get("team_id") != actor.get("team_id"):
            return jsonify({"error": "Access Denied: You can only view skills of your own team members."}), 403

    from services.skill_service import SkillService
    skills = SkillService.get_user_skills(employee_id)
    recs = SkillService.get_recommendations(employee_id=employee_id)
    return jsonify({"skills": skills, "recommendations": recs})


@api_bp.route("/skills", methods=["POST"])
@require_auth
def matrix_add_skill():
    actor = request.current_user
    payload = request.get_json(silent=True) or {}
    from services.skill_service import SkillService
    skill, err = SkillService.add_skill(actor, payload)
    if err:
        return jsonify({"error": err}), 400
    return jsonify({"message": "Skill recorded successfully.", "skill": skill}), 201


@api_bp.route("/skills/<skill_id>", methods=["PUT"])
@require_auth
def matrix_update_skill(skill_id):
    actor = request.current_user
    payload = request.get_json(silent=True) or {}
    from services.skill_service import SkillService
    skill, err = SkillService.update_skill(actor, skill_id, payload)
    if err:
        return jsonify({"error": err}), 400
    return jsonify({"message": "Skill updated successfully.", "skill": skill}), 200


@api_bp.route("/skills/<skill_id>", methods=["DELETE"])
@require_auth
def matrix_delete_skill(skill_id):
    actor = request.current_user
    from services.skill_service import SkillService
    success, err = SkillService.delete_skill(actor, skill_id)
    if err or not success:
        return jsonify({"error": err or "Failed to delete skill"}), 400
    return jsonify({"message": "Skill deleted successfully."}), 200


@api_bp.route("/skills/<skill_id>/assess", methods=["POST"])
@require_roles(Role.TRAINER, Role.TEAM_LEAD, Role.HR, Role.HR_MANAGER, Role.ORGANIZATION, Role.ADMIN)
def matrix_assess_skill(skill_id):
    actor = request.current_user
    payload = request.get_json(silent=True) or {}
    from services.skill_service import SkillService
    skill, err = SkillService.assess_skill(actor, skill_id, payload)
    if err:
        return jsonify({"error": err}), 400
    return jsonify({"message": "Skill evaluation recorded.", "skill": skill}), 200


@api_bp.route("/skills/team/<team_id>", methods=["GET"])
@require_roles(Role.TRAINER, Role.TEAM_LEAD, Role.HR, Role.HR_MANAGER, Role.ORGANIZATION, Role.ADMIN)
def matrix_get_team_skills(team_id):
    actor = request.current_user
    if actor.get("role") == Role.TEAM_LEAD and actor.get("team_id") != team_id:
        return jsonify({"error": "Access Denied: You can only view your own team's skill matrix."}), 403

    from services.skill_service import SkillService
    matrix = SkillService.get_team_skill_matrix(team_id)
    return jsonify(matrix)


@api_bp.route("/skills/company", methods=["GET"])
@require_roles(Role.HR, Role.HR_MANAGER, Role.TRAINER, Role.ORGANIZATION, Role.ADMIN)
def matrix_get_company_skills():
    category = request.args.get("category")
    department = request.args.get("department")
    from services.skill_service import SkillService
    matrix = SkillService.get_company_skill_matrix(category=category, department=department)
    return jsonify(matrix)


@api_bp.route("/skills/recommend-training", methods=["POST"])
@require_roles(Role.TRAINER, Role.TEAM_LEAD, Role.HR, Role.HR_MANAGER, Role.ORGANIZATION, Role.ADMIN)
def matrix_recommend_training():
    actor = request.current_user
    payload = request.get_json(silent=True) or {}
    from services.skill_service import SkillService
    rec, err = SkillService.recommend_training(actor, payload)
    if err:
        return jsonify({"error": err}), 400
    return jsonify({"message": "Training recommendation created successfully.", "recommendation": rec}), 201


# ==========================================
# 12. ADMIN GOVERNANCE, ANALYTICS & HEALTH
# ==========================================

@api_bp.route("/admin/role-reviews", methods=["GET"])
@require_roles(Role.ADMIN)
def get_admin_role_reviews():
    """Returns legacy accounts that require authorized Admin review."""
    db = get_db()
    flagged = list(db.users.find(
        {"requires_role_review": True},
        {"password_hash": 0}
    ))
    return jsonify({"flagged_users": serialize_docs(flagged)})


@api_bp.route("/admin/users/<employee_id>/role", methods=["POST"])
@require_roles(Role.ADMIN)
def admin_assign_user_role(employee_id):
    """Authorized Admin assigns or changes a user role among the 5 canonical roles."""
    data = request.get_json(silent=True) or {}
    new_role = (data.get("role") or "").strip().lower()
    reason = (data.get("reason") or "Authorized administrative role review").strip()

    valid_roles = [Role.EMPLOYEE, Role.TEAM_LEAD, Role.HR, Role.MANAGER, Role.ADMIN]
    if new_role not in valid_roles:
        return jsonify({
            "error": f"Invalid role '{new_role}'. Must be one of: {', '.join(valid_roles)}"
        }), 400

    db = get_db()
    target_user = db.users.find_one({"employee_id": employee_id})
    if not target_user:
        return jsonify({"error": f"User '{employee_id}' not found."}), 404

    old_role = target_user.get("role")
    updates = {
        "role": new_role,
        "requires_role_review": False,
        "role_reviewed_by": request.current_user.get("employee_id"),
        "role_reviewed_at": now_utc(),
        "updated_at": now_utc()
    }

    db.users.update_one({"employee_id": employee_id}, {"$set": updates})

    AuditService.log_action(
        actor=request.current_user,
        action="ADMIN_ASSIGN_ROLE",
        target_type="user",
        target_id=employee_id,
        details={"old_role": old_role, "new_role": new_role, "reason": reason}
    )

    updated_user = db.users.find_one({"employee_id": employee_id}, {"password_hash": 0})
    return jsonify({
        "success": True,
        "message": f"Successfully updated role for {employee_id} to '{new_role}'.",
        "user": serialize_doc(updated_user)
    }), 200


@api_bp.route("/admin/analytics", methods=["GET"])
@require_roles(Role.ADMIN)
def get_admin_analytics():
    """
    Computes genuine project and operational analytics for the Admin dashboard
    using actual database records and aggregation.
    """
    db = get_db()
    today_str = get_local_date_str()

    # 1. Projects Breakdown & Status Distribution
    projects = list(db.projects.find({}))
    status_counts = {"Not Started": 0, "In Progress": 0, "At Risk": 0, "Completed": 0, "On Hold": 0}
    project_progress_list = []
    total_project_progress = 0

    for p in projects:
        st = p.get("status", "Not Started")
        if st in status_counts:
            status_counts[st] += 1
        else:
            status_counts["In Progress"] += 1

        prog = p.get("progress_percentage", 0)
        total_project_progress += prog
        project_progress_list.append({
            "project_id": p.get("project_id"),
            "name": p.get("name"),
            "status": st,
            "progress_percentage": prog,
            "members_count": len(p.get("members", [])),
            "start_date": p.get("start_date", ""),
            "end_date": p.get("end_date", "")
        })

    avg_project_progress = round(total_project_progress / len(projects), 1) if projects else 0

    # 2. Tasks Breakdown (Planned vs Completed)
    tasks = list(db.tasks.find({}))
    task_status_counts = {"Completed": 0, "In Progress": 0, "Todo": 0, "Blocked": 0}
    overdue_tasks = []
    now_date_str = today_str

    for t in tasks:
        t_st = t.get("status", "Todo")
        if t_st in task_status_counts:
            task_status_counts[t_st] += 1
        elif t_st == "Done":
            task_status_counts["Completed"] += 1
        else:
            task_status_counts["Todo"] += 1

        due = t.get("due_date", "")
        if due and due < now_date_str and t_st not in ("Completed", "Done"):
            overdue_tasks.append({
                "task_id": t.get("task_id"),
                "title": t.get("title"),
                "project_id": t.get("project_id"),
                "due_date": due,
                "priority": t.get("priority", "Medium"),
                "assignee_id": t.get("assignee_id")
            })

    total_tasks = len(tasks)
    completed_tasks = task_status_counts["Completed"]
    task_completion_rate = round((completed_tasks / total_tasks * 100), 1) if total_tasks else 0

    # 3. Team Workload & Allocation
    teams = list(db.teams.find({}))
    team_workloads = []
    for tm in teams:
        m_count = len(tm.get("members", []))
        tm_id = tm.get("team_id")
        # count tasks assigned to members of this team
        team_workloads.append({
            "team_id": tm_id,
            "name": tm.get("name"),
            "department": tm.get("department", "Engineering"),
            "members_count": m_count
        })

    # 4. Workforce & Roles Distribution
    users = list(db.users.find({"is_active": True}, {"role": 1, "department": 1, "joining_date": 1}))
    total_workforce = len(users)
    role_distribution = {
        Role.EMPLOYEE: 0,
        Role.TEAM_LEAD: 0,
        Role.HR: 0,
        Role.MANAGER: 0,
        Role.ADMIN: 0
    }
    dept_distribution = {}

    for u in users:
        r = u.get("role", Role.EMPLOYEE)
        if r in role_distribution:
            role_distribution[r] += 1
        elif r in ("hr_manager", "organization"):
            role_distribution[Role.MANAGER] += 1
        elif r == "trainer":
            role_distribution[Role.TEAM_LEAD] += 1
        else:
            role_distribution[Role.EMPLOYEE] += 1

        dept = u.get("department", "General")
        dept_distribution[dept] = dept_distribution.get(dept, 0) + 1

    # 5. Today's Attendance Overview
    att_overview = AttendanceService.get_hr_monitoring_overview(today_str)
    attendance_summary = {
        "present_count": att_overview.get("present_count", 0),
        "late_count": att_overview.get("late_count", 0),
        "incomplete_count": att_overview.get("incomplete_count", 0),
        "absent_count": att_overview.get("absent_count", 0)
    }

    # 6. Leave Summary
    leaves = list(db.leave_requests.find({}))
    leave_summary = {
        "total": len(leaves),
        "pending": sum(1 for l in leaves if l.get("status") == "Pending"),
        "approved": sum(1 for l in leaves if l.get("status") == "Approved"),
        "rejected": sum(1 for l in leaves if l.get("status") == "Rejected")
    }

    # 7. Monthly Hiring & Offboarding Trends (last 6 months)
    from datetime import datetime, timedelta
    monthly_trends = []
    current_date = datetime.now()
    for i in range(5, -1, -1):
        month_dt = current_date - timedelta(days=i * 30)
        ym_str = month_dt.strftime("%Y-%m")
        label = month_dt.strftime("%b %Y")
        hired = sum(1 for u in users if (u.get("joining_date") or "").startswith(ym_str))
        departed = db.offboardings.count_documents({"effective_date": {"$regex": f"^{ym_str}"}})
        monthly_trends.append({
            "year_month": ym_str,
            "label": label,
            "hired": hired,
            "departed": departed
        })

    # 8. Pending Role Reviews Count
    flagged_role_reviews = db.users.count_documents({"requires_role_review": True})

    return jsonify({
        "kpis": {
            "total_workforce": total_workforce,
            "total_projects": len(projects),
            "completed_projects": status_counts.get("Completed", 0),
            "avg_project_progress": avg_project_progress,
            "total_tasks": total_tasks,
            "completed_tasks": completed_tasks,
            "task_completion_rate": task_completion_rate,
            "overdue_tasks_count": len(overdue_tasks),
            "pending_leaves_count": leave_summary["pending"],
            "flagged_role_reviews": flagged_role_reviews
        },
        "project_status_distribution": status_counts,
        "project_progress_list": project_progress_list,
        "task_breakdown": {
            "status_counts": task_status_counts,
            "overdue_tasks": overdue_tasks[:10],
            "total": total_tasks,
            "completed": completed_tasks
        },
        "team_workloads": team_workloads,
        "role_distribution": role_distribution,
        "department_distribution": dept_distribution,
        "attendance_summary": attendance_summary,
        "leave_summary": leave_summary,
        "monthly_trends": monthly_trends
    })


@api_bp.route("/admin/system-health", methods=["GET"])
@require_roles(Role.ADMIN)
def get_system_health():
    """Returns system status, collection counts, and operational health without exposing credentials."""
    db = get_db()
    collections = {
        "users": db.users.count_documents({}),
        "projects": db.projects.count_documents({}),
        "tasks": db.tasks.count_documents({}),
        "attendance_records": db.attendance_records.count_documents({}),
        "leave_requests": db.leave_requests.count_documents({}),
        "complaints": db.complaints.count_documents({}),
        "audit_logs": db.audit_logs.count_documents({}),
        "teams": db.teams.count_documents({}),
        "conversations": db.conversations.count_documents({})
    }

    from config import Config
    import sys
    import os

    # Get local backup metadata safely
    from pathlib import Path
    data_dir = getattr(Config, "PERSISTENT_DATA_DIR", getattr(Config, "DATA_DIR", Path(Config.BASE_DIR) / "data" / "storage"))
    backups = []
    if Path(data_dir).exists():
        backup_files = list(Path(data_dir).glob("*.tar.gz")) + list(Path(data_dir).glob("*.zip"))
        for b in backup_files[:5]:
            backups.append({
                "filename": b.name,
                "size_kb": round(b.stat().st_size / 1024, 1),
                "modified": datetime.fromtimestamp(b.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
            })

    return jsonify({
        "status": "Healthy",
        "database": {
            "name": Config.DATABASE_NAME,
            "engine": "Local Persistent Storage / Embedded Database",
            "connected": True,
            "storage_directory": str(data_dir),
            "collection_counts": collections
        },
        "environment": {
            "python_version": sys.version.split()[0],
            "app_env": os.environ.get("FLASK_ENV", "development"),
            "scheduler_active": True
        },
        "backups": backups
    })


# ==========================================
# 10. ANALYTICS & HEALTH ENDPOINTS
# ==========================================

@api_bp.route("/analytics/overview", methods=["GET"])
@require_auth
def get_analytics_overview():
    user = request.current_user
    period = request.args.get("period", "this_month")
    filters = {
        "team_id": request.args.get("team_id"),
        "department": request.args.get("department"),
        "project_id": request.args.get("project_id")
    }
    from services.analytics_service import AnalyticsService
    data = AnalyticsService.get_analytics_for_user(user, period=period, filters=filters)
    return jsonify(data)


@api_bp.route("/analytics/export", methods=["GET"])
@require_auth
def export_analytics():
    user = request.current_user
    period = request.args.get("period", "this_month")
    filters = {
        "team_id": request.args.get("team_id"),
        "department": request.args.get("department"),
        "project_id": request.args.get("project_id")
    }
    from services.analytics_service import AnalyticsService
    csv_content, filename = AnalyticsService.export_analytics_csv(user, period=period, filters=filters)
    return Response(
        csv_content,
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@api_bp.route("/health", methods=["GET"])
def health_check():
    """Operational health check for container liveness and load balancers."""
    db = get_db()
    users_count = db.users.count_documents({})
    return jsonify({
        "status": "UP",
        "timestamp": now_utc().isoformat(),
        "database": {
            "name": db.name,
            "connected": True,
            "users_count": users_count
        },
        "roles": [Role.EMPLOYEE, Role.TEAM_LEAD, Role.MANAGER, Role.HR]
    }), 200


# ==========================================
# 16. MULTI-PAD NOTEPAD ENDPOINTS
# ==========================================

from services.notepad_service import NotepadService

@api_bp.route("/notepads", methods=["GET"])
@require_auth
def get_user_notepads():
    actor = request.current_user
    emp_id = actor.get("employee_id") or actor.get("emp_id")
    notes = NotepadService.get_user_notes(emp_id)
    return jsonify({"notes": notes, "count": len(notes)})


@api_bp.route("/notepads", methods=["POST"])
@require_auth
def create_notepad():
    actor = request.current_user
    emp_id = actor.get("employee_id") or actor.get("emp_id")
    data = request.get_json(silent=True) or {}
    note = NotepadService.create_note(emp_id, data)
    return jsonify({"success": True, "note": note}), 201


@api_bp.route("/notepads/<note_id>", methods=["PUT"])
@require_auth
def update_notepad(note_id):
    actor = request.current_user
    emp_id = actor.get("employee_id") or actor.get("emp_id")
    data = request.get_json(silent=True) or {}
    note, err = NotepadService.update_note(emp_id, note_id, data)
    if err:
        return jsonify({"error": err}), 404
    return jsonify({"success": True, "note": note}), 200


@api_bp.route("/notepads/<note_id>", methods=["DELETE"])
@require_auth
def delete_notepad(note_id):
    actor = request.current_user
    emp_id = actor.get("employee_id") or actor.get("emp_id")
    success, err = NotepadService.delete_note(emp_id, note_id)
    if err:
        return jsonify({"error": err}), 404
    return jsonify({"success": True, "message": "Notepad deleted successfully."}), 200


# ==========================================
# 17. SMART FEEDBACK & BUG REPORTING ENDPOINTS
# ==========================================

from services.feedback_service import FeedbackService

@api_bp.route("/feedback/submit", methods=["POST"])
@require_auth
def submit_system_feedback():
    actor = request.current_user
    data = request.get_json(silent=True) or {}
    res, err = FeedbackService.submit_feedback(actor, data)
    if err:
        return jsonify({"error": err}), 400

    # Seamlessly mirror to Support Tickets in Kudos & Support
    try:
        from services.enterprise_hr_service import EngagementSupportService
        ticket_payload = {
            "subject": data.get("summary") or data.get("subject") or "Feedback Submission",
            "description": data.get("details") or data.get("description") or "Feedback Details",
            "category": data.get("category") or "General Feedback",
            "priority": data.get("severity") or data.get("priority") or "Medium",
            "assigned_role": data.get("assigned_role") or "auto"
        }
        ticket, _ = EngagementSupportService.create_support_ticket(actor, ticket_payload)
        if ticket:
            res["ticket_id"] = ticket.get("ticket_id")
            res["assigned_role_name"] = ticket.get("assigned_role_name")
    except Exception:
        pass

    return jsonify({"success": True, **res}), 201


@api_bp.route("/admin/feedback/triaged", methods=["GET"])
@require_roles(Role.ADMIN)
def get_admin_triaged_feedback():
    status_filter = request.args.get("status")
    data = FeedbackService.get_triaged_feedback(status_filter)
    return jsonify(data), 200


@api_bp.route("/admin/feedback/status", methods=["POST"])
@require_roles(Role.ADMIN)
def update_admin_feedback_status():
    actor = request.current_user
    data = request.get_json(silent=True) or {}
    feedback_ids = data.get("feedback_ids", [])
    new_status = data.get("status", "Resolved")
    notes = data.get("notes", "")
    success, err = FeedbackService.update_cluster_status(actor, feedback_ids, new_status, notes)
    if err:
        return jsonify({"error": err}), 400
    return jsonify({"success": True, "message": f"Feedback status updated to {new_status}."}), 200


# ==========================================
# 18. SHIFT POLICIES & ROSTER CONFIGURATION
# ==========================================

@api_bp.route("/roster/policies", methods=["GET"])
@require_auth
def get_shift_policies():
    from services.roster_service import SHIFT_DEFINITIONS
    return jsonify({
        "shifts": SHIFT_DEFINITIONS,
        "default_shift": "General",
        "grace_period_mins": 15,
        "mandatory_cutoff_mins_prior": 45,
        "hard_cutoff_time": "19:00"
    }), 200


# ============================================================================
# 19. ENTERPRISE HR MODULES SUITE (R1-R29)
# ============================================================================
from services.enterprise_hr_service import (
    NomineeManagementService,
    AssetSoftwareService,
    FacilityBookingService,
    PerformanceLearningService,
    EngagementSupportService,
    SeparationService,
    RecruitmentTalentService,
    SecureDocumentViewerService,
    EnterprisePayrollService,
    EnterpriseMailboxService
)

# --- 19.1 Nominee Management ---
@api_bp.route("/nominees", methods=["GET"])
@require_auth
def get_nominees_route():
    actor = request.current_user
    actor_id = (actor.get("employee_id") or actor.get("emp_id") or "").strip().upper()
    emp_id = (request.args.get("employee_id") or actor_id or "").strip()
    is_self = bool(actor_id and emp_id.upper() == actor_id)
    if not is_self and normalize_role(actor.get("role")) not in (Role.HR, Role.ADMIN):
        return jsonify({"error": "Unauthorized to view other employee's nominees."}), 403
    nominees = NomineeManagementService.get_nominees(emp_id)
    return jsonify({"success": True, "employee_id": emp_id, "nominees": nominees}), 200


@api_bp.route("/nominees", methods=["POST"])
@require_auth
def save_nominees_route():
    actor = request.current_user
    payload = request.get_json(silent=True) or {}
    actor_id = (actor.get("employee_id") or actor.get("emp_id") or "").strip().upper()
    emp_id = (payload.get("employee_id") or actor_id or "").strip()
    is_self = bool(actor_id and emp_id.upper() == actor_id)
    if not is_self and normalize_role(actor.get("role")) not in (Role.HR, Role.ADMIN):
        return jsonify({"error": "Unauthorized to update other employee's nominees."}), 403
    nominees = payload.get("nominees", [])
    success, err = NomineeManagementService.save_nominees(actor, emp_id, nominees)
    if not success:
        return jsonify({"error": err}), 400
    return jsonify({"success": True, "message": err}), 200


# --- 19.2 Assets & Software Management ---
@api_bp.route("/assets/my-assets", methods=["GET"])
@require_auth
def get_my_assets_route():
    emp_id = request.current_user["employee_id"]
    assets = AssetSoftwareService.get_employee_assets(emp_id)
    return jsonify({"success": True, **assets}), 200


@api_bp.route("/assets/request", methods=["POST"])
@require_auth
def request_asset_route():
    actor = request.current_user
    data = request.get_json(silent=True) or {}
    doc, err = AssetSoftwareService.request_asset(actor, data)
    if err:
        return jsonify({"error": err}), 400
    return jsonify({"success": True, "message": "Asset request submitted successfully.", "request": doc}), 201


@api_bp.route("/assets/inventory", methods=["GET"])
@require_auth
def get_assets_inventory_route():
    inventory = AssetSoftwareService.get_global_inventory(request.current_user)
    return jsonify({"success": True, **inventory}), 200


@api_bp.route("/assets/requests/<request_id>/review", methods=["POST"])
@require_roles(Role.HR, Role.ADMIN, Role.MANAGER)
def review_asset_request_route(request_id):
    actor = request.current_user
    data = request.get_json(silent=True) or {}
    decision = data.get("decision", "Approved")
    remarks = data.get("remarks", "")
    assigned_tag = data.get("assigned_asset_tag")
    doc, err = AssetSoftwareService.review_asset_request(actor, request_id, decision, remarks, assigned_tag)
    if err:
        return jsonify({"error": err}), 400
    return jsonify({"success": True, "message": f"Asset request {decision.lower()} successfully.", "request": doc}), 200


@api_bp.route("/assets/allocate", methods=["POST"])
@require_roles(Role.HR, Role.ADMIN)
def allocate_asset_route():
    actor = request.current_user
    data = request.get_json(silent=True) or {}
    emp_id = data.get("employee_id")
    if not emp_id:
        return jsonify({"error": "Target employee_id is required."}), 400
    doc, err = AssetSoftwareService.allocate_asset(actor, emp_id, data)
    if err:
        return jsonify({"error": err}), 400
    return jsonify({"success": True, "message": "Asset allocated successfully.", "asset": doc}), 201


@api_bp.route("/assets/requests/<request_id>", methods=["DELETE"])
@require_auth
def cancel_or_delete_asset_request_route(request_id):
    from services.enterprise_hr_service import AssetSoftwareService
    actor = request.current_user
    success, err = AssetSoftwareService.cancel_or_delete_asset_request(actor, request_id)
    if not success:
        return jsonify({"success": False, "error": err}), 400
    return jsonify({"success": True, "message": f"Asset request {request_id} deleted successfully."}), 200


@api_bp.route("/assets/inventory/<asset_type>/<item_id>", methods=["DELETE"])
@require_roles(Role.HR, Role.HR_MANAGER, Role.ADMIN, Role.ORGANIZATION)
def delete_asset_inventory_route(asset_type, item_id):
    from services.enterprise_hr_service import AssetSoftwareService
    actor = request.current_user
    success, err = AssetSoftwareService.delete_asset_inventory(actor, asset_type, item_id)
    if not success:
        return jsonify({"success": False, "error": err}), 400
    return jsonify({"success": True, "message": f"Asset {item_id} decommissioned/deleted successfully."}), 200


# --- 19.2.1 Office Seating & Personal Locker Allocation ---
@api_bp.route("/assets/seating-lockers", methods=["GET"])
@require_auth
def get_seating_lockers_route():
    from services.enterprise_hr_service import SeatingLockerService
    emp_id = request.current_user.get("employee_id") or request.current_user.get("emp_id")
    my_seating = SeatingLockerService.get_employee_seating(emp_id)
    user_role = normalize_role(request.current_user.get("role"))

    all_allocs = []
    if user_role in (Role.HR, Role.MANAGER, Role.ADMIN):
        all_allocs = SeatingLockerService.get_all_seating_allocations()

    confirmed_count = len([a for a in all_allocs if a.get("is_verified")])
    provisional_count = len([a for a in all_allocs if not a.get("is_verified")])

    return jsonify({
        "success": True,
        "my_seating": my_seating,
        "all_allocations": all_allocs,
        "confirmed_allocated": confirmed_count,
        "provisional_allocated": provisional_count,
        "total_records": len(all_allocs)
    }), 200


@api_bp.route("/assets/seating-lockers/<allocation_id>/verify", methods=["POST"])
@require_roles(Role.HR, Role.ADMIN)
def verify_seating_allocation_route(allocation_id):
    from services.enterprise_hr_service import SeatingLockerService
    actor = request.current_user
    data = request.get_json(silent=True) or {}
    doc, err = SeatingLockerService.verify_allocation(actor, allocation_id, data)
    if err:
        return jsonify({"success": False, "error": err}), 403 if "Unauthorized" in err else 400
    return jsonify({
        "success": True,
        "message": f"Workstation allocation for {doc.get('employee_name')} verified successfully.",
        "allocation": doc
    }), 200


@api_bp.route("/assets/seating-lockers/allocate", methods=["POST"])
@require_roles(Role.HR, Role.ADMIN)
def allocate_seating_locker_route():
    from services.enterprise_hr_service import SeatingLockerService
    actor = request.current_user
    data = request.get_json(silent=True) or {}
    doc, err = SeatingLockerService.allocate_or_update(actor, data)
    if err:
        return jsonify({"success": False, "error": err}), 403 if "Unauthorized" in err else 400
    return jsonify({
        "success": True,
        "message": f"Verified office seat assigned to {doc.get('employee_name', 'staff member')}.",
        "allocation": doc
    }), 200


# --- 19.3 Facility & Meeting Rooms ---
@api_bp.route("/facilities/rooms", methods=["GET"])
@require_auth
def get_facility_rooms_route():
    date_str = request.args.get("date") or datetime.now().strftime("%Y-%m-%d")
    data = FacilityBookingService.get_rooms_and_bookings(date_str)
    return jsonify({"success": True, **data}), 200


@api_bp.route("/facilities/rooms/<room_id>/verify", methods=["POST"])
@require_roles(Role.HR, Role.ADMIN)
def verify_facility_room_route(room_id):
    from services.enterprise_hr_service import FacilityBookingService
    actor = request.current_user
    data = request.get_json(silent=True) or {}
    doc, err = FacilityBookingService.verify_room(actor, room_id, data)
    if err:
        return jsonify({"success": False, "error": err}), 403 if "Unauthorized" in err else 400
    return jsonify({
        "success": True,
        "message": f"Meeting room '{doc.get('name')}' verified successfully.",
        "room": doc
    }), 200


@api_bp.route("/facilities/rooms", methods=["POST"])
@require_roles(Role.HR, Role.ADMIN)
def create_facility_room_route():
    from services.enterprise_hr_service import FacilityBookingService
    actor = request.current_user
    data = request.get_json(silent=True) or {}
    room, err = FacilityBookingService.create_room(actor, data)
    if err:
        return jsonify({"success": False, "error": err}), 403 if "Unauthorized" in err else 400
    return jsonify({"success": True, "message": "Verified meeting room registered successfully.", "room": room}), 201


@api_bp.route("/facilities/rooms/<room_id>", methods=["DELETE"])
@require_roles(Role.HR, Role.ADMIN)
def delete_facility_room_route(room_id):
    from services.enterprise_hr_service import FacilityBookingService
    actor = request.current_user
    success, err = FacilityBookingService.delete_room(actor, room_id)
    if not success:
        return jsonify({"success": False, "error": err}), 403 if err and "Unauthorized" in err else 400
    return jsonify({"success": True, "message": f"Room {room_id} deleted successfully."}), 200


@api_bp.route("/facilities/book", methods=["POST"])
@require_auth
def book_facility_room_route():
    actor = request.current_user
    data = request.get_json(silent=True) or {}
    doc, err = FacilityBookingService.create_booking(actor, data)
    if err:
        return jsonify({"error": err}), 400
    return jsonify({"success": True, "message": "Meeting room booked successfully.", "booking": doc}), 201


@api_bp.route("/facilities/bookings/<booking_id>", methods=["DELETE"])
@require_auth
def cancel_facility_booking_route(booking_id):
    actor = request.current_user
    success, err = FacilityBookingService.cancel_booking(actor, booking_id)
    if not success:
        return jsonify({"error": err}), 400
    return jsonify({"success": True, "message": err}), 200


# --- 19.4 Performance & Compliance Courses (L&D) ---
@api_bp.route("/performance/hub", methods=["GET"])
@require_auth
def get_performance_hub_route():
    emp_id = request.args.get("employee_id") or request.current_user["employee_id"]
    data = PerformanceLearningService.get_employee_performance_hub(emp_id)
    return jsonify({"success": True, **data}), 200


@api_bp.route("/performance/courses/complete", methods=["POST"])
@require_auth
def complete_compliance_course_route():
    actor = request.current_user
    data = request.get_json(silent=True) or {}
    course_id = (data.get("course_id") or "").strip()
    score = data.get("score", 95)
    doc, err = PerformanceLearningService.complete_course(actor, course_id, score)
    if err:
        return jsonify({"error": err}), 400
    return jsonify({"success": True, "message": "Course completed and certificate issued.", "certificate": doc}), 200


@api_bp.route("/performance/tasks/create", methods=["POST"])
@require_auth
def create_performance_task_route():
    actor = request.current_user
    data = request.get_json(silent=True) or {}
    task, err = PerformanceLearningService.create_task(actor, data)
    if err:
        return jsonify({"error": err}), 400
    return jsonify({"success": True, "message": "Task created successfully.", "task": task}), 201


@api_bp.route("/performance/tasks/<task_id>/status", methods=["POST"])
@require_auth
def update_performance_task_status_route(task_id):
    actor = request.current_user
    data = request.get_json(silent=True) or {}
    new_status = (data.get("status") or "").strip()
    task, err = PerformanceLearningService.update_task_status(actor, task_id, new_status)
    if err:
        return jsonify({"error": err}), 400
    return jsonify({"success": True, "message": f"Task status updated to {new_status}.", "task": task}), 200


# --- 19.5 Engagement, Community, Kudos, Tickets & Claims ---
@api_bp.route("/engagement/feed", methods=["GET"])
@require_auth
def get_community_feed_route():
    posts = EngagementSupportService.get_community_feed()
    return jsonify({"success": True, "feed": posts}), 200


@api_bp.route("/engagement/feed/post", methods=["POST"])
@require_auth
def create_community_post_route():
    actor = request.current_user
    data = request.get_json(silent=True) or {}
    post, err = EngagementSupportService.create_post(actor, data.get("content", ""), data.get("badge", "Team Update"))
    if err:
        return jsonify({"error": err}), 400
    return jsonify({"success": True, "post": post}), 201


@api_bp.route("/engagement/feed/like", methods=["POST"])
@require_auth
def toggle_post_like_route():
    actor = request.current_user
    data = request.get_json(silent=True) or {}
    post_id = data.get("post_id", "")
    success, count = EngagementSupportService.toggle_like(actor, post_id)
    if not success:
        return jsonify({"error": "Post not found."}), 404
    return jsonify({"success": True, "likes_count": count}), 200


@api_bp.route("/engagement/kudos", methods=["GET"])
@require_auth
def get_kudos_leaderboard_route():
    data = EngagementSupportService.get_kudos_leaderboard()
    return jsonify({"success": True, **data}), 200


@api_bp.route("/engagement/kudos/send", methods=["POST"])
@require_auth
def send_kudos_route():
    actor = request.current_user
    data = request.get_json(silent=True) or {}
    rid = (data.get("recipient_id") or data.get("recipient_name") or "").strip()
    pts = int(data.get("points") or 50)
    cat = (data.get("category") or "Teamwork").strip()
    msg = (data.get("message") or "").strip()
    success, err = EngagementSupportService.send_kudos(actor, rid, pts, cat, msg)
    if not success:
        return jsonify({"error": err}), 400
    return jsonify({"success": True, "message": err}), 200


@api_bp.route("/support/tickets", methods=["GET"])
@require_auth
def get_support_tickets_route():
    actor = request.current_user
    emp_id = None if actor.get("role") in (Role.HR, Role.ADMIN) else actor["employee_id"]
    tickets = EngagementSupportService.get_support_tickets(emp_id)
    return jsonify({"success": True, "tickets": tickets}), 200


@api_bp.route("/support/tickets/create", methods=["POST"])
@require_auth
def create_support_ticket_route():
    actor = request.current_user
    data = request.get_json(silent=True) or {}
    ticket, err = EngagementSupportService.create_support_ticket(actor, data)
    if err:
        return jsonify({"error": err}), 400
    return jsonify({"success": True, "message": "Support ticket created successfully.", "ticket": ticket}), 201


@api_bp.route("/expenses/claims", methods=["GET"])
@require_auth
def get_expense_claims_route():
    actor = request.current_user
    claims = EngagementSupportService.get_expense_claims(actor=actor)
    return jsonify({"success": True, "claims": claims}), 200


@api_bp.route("/expenses/claims/submit", methods=["POST"])
@require_auth
def submit_expense_claim_route():
    actor = request.current_user
    data = request.get_json(silent=True) or {}
    claim, err = EngagementSupportService.submit_expense_claim(actor, data)
    if err:
        return jsonify({"error": err}), 400
    return jsonify({"success": True, "message": "Expense claim submitted for manager sign-off.", "claim": claim}), 201


@api_bp.route("/assets/requests/pending", methods=["GET"])
@require_roles(Role.HR, Role.ADMIN, Role.MANAGER, Role.HR_MANAGER)
def get_pending_asset_requests_route():
    """Get all pending asset requests for HR/Manager approval."""
    db_conn = get_db()
    actor = request.current_user
    query = {"status": "Pending Review"}
    if normalize_role(actor.get("role")) == Role.MANAGER:
        actor_id = actor.get("employee_id") or actor.get("emp_id")
        query["$or"] = [
            {"assigned_manager_id": actor_id},
            {"assigned_manager_id": {"$exists": False}, "department": actor.get("department")}
        ]
    pending = list(db_conn.asset_requests.find(query).sort("created_at", -1))
    return jsonify({"success": True, "requests": serialize_docs(pending), "count": len(pending)}), 200


@api_bp.route("/expenses/claims/<claim_id>/review", methods=["POST"])
@require_roles(Role.HR, Role.ADMIN, Role.MANAGER, Role.HR_MANAGER)
def review_expense_claim_route(claim_id):
    """Approve or reject an expense claim."""
    actor = request.current_user
    data = request.get_json(silent=True) or {}
    decision = data.get("decision", "Approved")
    remarks = data.get("remarks", "")

    db_conn = get_db()
    claim = db_conn.expense_claims.find_one({"claim_id": claim_id})
    if not claim:
        return jsonify({"error": f"Expense claim '{claim_id}' not found."}), 404
    actor_role = normalize_role(actor.get("role"))
    actor_id = actor.get("employee_id") or actor.get("emp_id")
    if actor_role == Role.MANAGER and claim.get("assigned_manager_id") != actor_id and not (
        not claim.get("assigned_manager_id") and claim.get("department") == actor.get("department")
    ):
        return jsonify({"error": "Access denied: this expense claim is assigned to another manager."}), 403
    if claim.get("status") != "Submitted":
        return jsonify({"error": f"Expense claim is already in '{claim.get('status')}' status."}), 409

    dec = decision.strip().title()
    if dec not in ("Approved", "Rejected"):
        return jsonify({"error": "Decision must be 'Approved' or 'Rejected'."}), 400

    reviewed_at = now_utc().isoformat()
    result = db_conn.expense_claims.update_one(
        {"claim_id": claim_id, "status": "Submitted"},
        {"$set": {
            "status": dec,
            "reviewed_by_id": actor["employee_id"],
            "reviewed_by_name": actor.get("full_name", ""),
            "review_remarks": remarks.strip(),
            "reviewed_at": reviewed_at,
            "updated_at": reviewed_at
        }}
    )
    if result.matched_count != 1:
        return jsonify({"error": "Expense claim was already reviewed. Refresh and try again."}), 409

    AuditService.log_action(
        actor=actor,
        action=f"EXPENSE_CLAIM_{dec.upper()}",
        target_type="expense_claim",
        target_id=claim_id,
        details=f"Decision: {dec}, Remarks: {remarks}"
    )

    updated = db_conn.expense_claims.find_one({"claim_id": claim_id})
    try:
        NotificationService.create_notification(
            title=f"Expense Claim {dec}",
            message=f"Your expense claim {claim_id} has been {dec.lower()}.",
            category="EXPENSE",
            recipient_id=claim["employee_id"],
            link="/facilities?tab=claims"
        )
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("Failed to notify employee about expense claim %s: %s", claim_id, exc)
    return jsonify({"success": True, "message": f"Expense claim {dec.lower()} successfully.", "claim": serialize_doc(updated)}), 200


@api_bp.route("/expenses/claims/pending", methods=["GET"])
@require_roles(Role.HR, Role.ADMIN, Role.MANAGER, Role.HR_MANAGER)
def get_pending_expense_claims_route():
    """Get all pending expense claims for Manager/HR review."""
    db_conn = get_db()
    actor = request.current_user
    query = {"status": "Submitted"}
    if normalize_role(actor.get("role")) == Role.MANAGER:
        actor_id = actor.get("employee_id") or actor.get("emp_id")
        query["$or"] = [
            {"assigned_manager_id": actor_id},
            {"assigned_manager_id": {"$exists": False}, "department": actor.get("department")}
        ]
    pending = list(db_conn.expense_claims.find(query).sort("created_at", -1))
    return jsonify({"success": True, "claims": serialize_docs(pending), "count": len(pending)}), 200


@api_bp.route("/policies/vault", methods=["GET"])
@api_bp.route("/policies", methods=["GET"])
@require_auth
def get_policy_vault_route():
    from services.enterprise_hr_service import EngagementSupportService
    policies = EngagementSupportService.get_company_policy_vault()
    return jsonify({"success": True, "policies": policies}), 200


@api_bp.route("/policies", methods=["POST"])
@require_roles(Role.HR, Role.HR_MANAGER, Role.ADMIN, Role.ORGANIZATION)
def create_policy_route():
    from services.enterprise_hr_service import EngagementSupportService
    actor = request.current_user
    data = request.get_json(silent=True) or {}
    policy, err = EngagementSupportService.create_policy(actor, data)
    if err:
        return jsonify({"success": False, "error": err}), 400
    return jsonify({"success": True, "message": "Policy created successfully.", "policy": policy}), 201


@api_bp.route("/policies/<policy_id>", methods=["PUT"])
@require_roles(Role.HR, Role.HR_MANAGER, Role.ADMIN, Role.ORGANIZATION)
def update_policy_route(policy_id):
    from services.enterprise_hr_service import EngagementSupportService
    actor = request.current_user
    data = request.get_json(silent=True) or {}
    policy, err = EngagementSupportService.update_policy(actor, policy_id, data)
    if err:
        return jsonify({"success": False, "error": err}), 400
    return jsonify({"success": True, "message": "Policy updated successfully.", "policy": policy}), 200


@api_bp.route("/policies/<policy_id>", methods=["DELETE"])
@require_roles(Role.HR, Role.HR_MANAGER, Role.ADMIN, Role.ORGANIZATION)
def delete_policy_route(policy_id):
    from services.enterprise_hr_service import EngagementSupportService
    actor = request.current_user
    success, err = EngagementSupportService.delete_policy(actor, policy_id)
    if not success:
        return jsonify({"success": False, "error": err}), 400
    return jsonify({"success": True, "message": f"Policy {policy_id} deleted successfully."}), 200


# --- 19.5b Travel Requisition & Logistics Allocation ---
@api_bp.route("/travel/requests", methods=["GET"])
@require_auth
def get_travel_requests_route():
    from services.enterprise_hr_service import TravelAllocationService
    actor = request.current_user
    status_filter = request.args.get("status", "ALL")
    requests_list = TravelAllocationService.get_travel_requests(actor, status_filter)
    return jsonify({"success": True, "requests": requests_list}), 200


@api_bp.route("/travel/requests", methods=["POST"])
@require_auth
def submit_travel_request_route():
    from services.enterprise_hr_service import TravelAllocationService
    actor = request.current_user
    data = request.get_json(silent=True) or {}
    req_doc, err = TravelAllocationService.submit_travel_request(actor, data)
    if err:
        return jsonify({"success": False, "error": err}), 400
    return jsonify({"success": True, "message": "Travel requisition submitted successfully.", "request": req_doc}), 201


@api_bp.route("/travel/requests/<request_id>/review", methods=["POST"])
@require_roles(Role.MANAGER, Role.ADMIN)
def review_travel_request_route(request_id):
    from services.enterprise_hr_service import TravelAllocationService
    actor = request.current_user
    data = request.get_json(silent=True) or {}
    decision = data.get("decision", "")
    remarks = data.get("remarks", "")
    req_doc, err = TravelAllocationService.review_travel_request(actor, request_id, decision, remarks)
    if err:
        return jsonify({"success": False, "error": err}), 400
    return jsonify({"success": True, "message": f"Travel request {decision.lower()} successfully.", "request": req_doc}), 200


@api_bp.route("/travel/requests/<request_id>/allocate", methods=["PUT", "POST"])
@require_roles(Role.HR, Role.HR_MANAGER, Role.ADMIN, Role.ORGANIZATION)
def allocate_travel_logistics_route(request_id):
    from services.enterprise_hr_service import TravelAllocationService
    actor = request.current_user
    data = request.get_json(silent=True) or {}
    req_doc, err = TravelAllocationService.allocate_travel(actor, request_id, data)
    if err:
        return jsonify({"success": False, "error": err}), 400
    return jsonify({"success": True, "message": "Travel tickets and logistics allocated successfully.", "request": req_doc}), 200


@api_bp.route("/travel/requests/<request_id>", methods=["DELETE"])
@require_auth
def cancel_travel_request_route(request_id):
    from services.enterprise_hr_service import TravelAllocationService
    actor = request.current_user
    success, err = TravelAllocationService.cancel_travel_request(actor, request_id)
    if not success:
        return jsonify({"success": False, "error": err}), 400
    return jsonify({"success": True, "message": "Travel request cancelled successfully."}), 200


# --- 19.6 Exit & Separation ---
@api_bp.route("/separation/status", methods=["GET"])
@require_auth
def get_separation_status_route():
    emp_id = request.args.get("employee_id") or request.current_user["employee_id"]
    data = SeparationService.get_tenure_and_status(emp_id)
    return jsonify({"success": True, **data}), 200


@api_bp.route("/separation/resign", methods=["POST"])
@require_auth
def initiate_resignation_route():
    actor = request.current_user
    data = request.get_json(silent=True) or {}
    doc, err = SeparationService.initiate_resignation(actor, data)
    if err:
        return jsonify({"error": err}), 400
    return jsonify({"success": True, "message": "Resignation submitted and routed for exit clearance.", "resignation": doc}), 201


@api_bp.route("/separation/clearance/approve", methods=["POST"])
@require_auth
def approve_clearance_stage_route():
    actor = request.current_user
    data = request.get_json(silent=True) or {}
    res_id = data.get("resignation_id")
    stage = data.get("stage")
    remarks = data.get("remarks", "")
    if not res_id or not stage:
        return jsonify({"error": "resignation_id and stage are required."}), 400
    doc, err = SeparationService.approve_clearance_stage(actor, res_id, stage, remarks)
    if err:
        return jsonify({"error": err}), 400
    return jsonify({"success": True, "message": f"{stage.capitalize()} clearance approved successfully.", "resignation": doc}), 200


# --- 19.7 Recruitment, ATS & MRF ---
@api_bp.route("/recruitment/scorecards", methods=["GET"])
@require_roles(Role.TEAM_LEAD, Role.MANAGER, Role.HR, Role.ADMIN)
def get_scorecards_route():
    cards = RecruitmentTalentService.get_candidate_scorecards()
    return jsonify({"success": True, "scorecards": cards}), 200


@api_bp.route("/recruitment/scorecards", methods=["POST"])
@require_roles(Role.TEAM_LEAD, Role.MANAGER, Role.HR, Role.ADMIN)
def submit_scorecard_route():
    actor = request.current_user
    data = request.get_json(silent=True) or {}
    doc, err = RecruitmentTalentService.submit_scorecard(actor, data)
    if err:
        return jsonify({"error": err}), 400
    return jsonify({"success": True, "message": "Candidate scorecard submitted successfully.", "scorecard": doc}), 201


@api_bp.route("/recruitment/ats", methods=["GET"])
@require_roles(Role.TEAM_LEAD, Role.MANAGER, Role.HR, Role.ADMIN)
def get_ats_pipeline_route():
    pipeline = RecruitmentTalentService.get_ats_pipeline()
    return jsonify({"success": True, **pipeline}), 200


# --- 19.8 Secure Document Viewer & PII Redaction ---
@api_bp.route("/documents/secure-records/<target_id>", methods=["GET"])
@require_roles(Role.HR, Role.ADMIN)
def get_secure_docket_route(target_id):
    docket = SecureDocumentViewerService.get_employee_secure_docket(target_id, actor=request.current_user)
    if "error" in docket:
        return jsonify({"error": docket["error"]}), docket.get("status_code", 404)
    return jsonify({"success": True, **docket}), 200


@api_bp.route("/documents/secure-records/<target_id>/preview", methods=["GET"])
@require_roles(Role.HR, Role.ADMIN)
def get_secure_doc_preview_route(target_id):
    doc_query = request.args.get("doc", "").strip()
    preview = SecureDocumentViewerService.get_secure_document_preview(target_id, doc_query, actor=request.current_user)
    if "error" in preview:
        return jsonify({"error": preview["error"]}), preview.get("status_code", 404)
    return jsonify({"success": True, **preview}), 200


# --- 19.9 Enterprise Payroll Overview & Execution (Tiimi SaaS HRM) ---
@api_bp.route("/payroll/overview", methods=["GET"])
@require_roles(Role.HR, Role.ADMIN)
def get_payroll_overview_route():
    overview = EnterprisePayrollService.get_payroll_overview()
    return jsonify({"success": True, **overview}), 200


@api_bp.route("/payroll/run", methods=["POST"])
@require_roles(Role.HR, Role.ADMIN)
def execute_payroll_run_route():
    data = request.get_json(silent=True) or {}
    cycle = data.get("cycle")
    result = EnterprisePayrollService.execute_payroll_run(cycle=cycle, executed_by=request.current_user)
    return jsonify({"success": True, "message": "Payroll cycle executed and disbursed successfully.", "payroll": result}), 200


# --- 19.10 Enterprise Official Mailbox Endpoints ---
@api_bp.route("/mailbox", methods=["GET"])
@require_auth
def get_user_mailbox_route():
    user = request.current_user
    folder = request.args.get("folder", "all").strip().lower()
    search = request.args.get("search", "").strip()
    data = EnterpriseMailboxService.get_user_mailbox(user, folder=folder, search=search)
    return jsonify({"success": True, **data}), 200


@api_bp.route("/mailbox/<mail_id>", methods=["GET"])
@require_auth
def get_mail_item_route(mail_id):
    user = request.current_user
    item = EnterpriseMailboxService.get_mail_item(user, mail_id)
    if not item:
        return jsonify({"error": "Official record not found or access unauthorized."}), 404
    return jsonify({"success": True, "item": item}), 200


@api_bp.route("/mailbox/<mail_id>/delete", methods=["POST", "DELETE"])
@api_bp.route("/mailbox/<mail_id>", methods=["DELETE"])
@require_auth
def delete_mail_route(mail_id):
    user = request.current_user
    success, msg = EnterpriseMailboxService.delete_mail(user, mail_id)
    if not success:
        return jsonify({"error": msg}), 400
    return jsonify({"success": True, "message": msg}), 200


@api_bp.route("/mailbox/dispatch", methods=["POST"])
@require_roles(Role.ADMIN, Role.HR, Role.MANAGER)
def dispatch_official_notice_route():
    actor = request.current_user
    body = request.get_json(silent=True) or {}
    item, err = EnterpriseMailboxService.dispatch_official_notice(actor, body)
    if err:
        return jsonify({"error": err}), 400
    return jsonify({"success": True, "item": item}), 201


@api_bp.route("/mailbox/send", methods=["POST"])
@require_auth
def send_internal_mail_route():
    actor = request.current_user
    body = request.get_json(silent=True) or {}
    item, err = EnterpriseMailboxService.send_user_mail(actor, body)
    if err:
        return jsonify({"error": err}), 400
    return jsonify({"success": True, "message": "Official corporate mail dispatched successfully.", "item": item}), 201


@api_bp.route("/chat/compose-email", methods=["POST"])
@require_auth
def chat_compose_email_route():
    """Universal Inbuilt Corporate Mail dispatch endpoint for Chat & Direct Comms."""
    actor = request.current_user
    body = request.get_json(silent=True) or {}
    to_val = (body.get("to") or body.get("recipient_id") or body.get("recipient_email") or "").strip()
    payload = {
        "recipient_id": to_val if "@" not in to_val else "",
        "recipient_email": to_val if "@" in to_val else "",
        "subject": body.get("subject") or "Direct Corporate Memo",
        "category": "MEMO",
        "content": body.get("message") or body.get("content") or "Official communication from chat room.",
        "is_confidential": False
    }
    item, err = EnterpriseMailboxService.send_user_mail(actor, payload)
    if err:
        return jsonify({"error": err, "status": "FAILED"}), 400
    return jsonify({
        "success": True, 
        "status": "DELIVERED", 
        "message": "Official corporate memo dispatched and delivered to recipient's Inbuilt Mailbox.",
        "item": item
    }), 201


@api_bp.route("/payroll/batch-email", methods=["POST"])
@require_roles(Role.HR, Role.ADMIN)
def payroll_batch_email_route():
    """Dispatches digital payslip delivery memos to all active employees via Inbuilt Mailbox."""
    actor = request.current_user
    if normalize_role(actor.get("role")) not in (Role.ADMIN, Role.HR):
        return jsonify({"error": "Unauthorized to execute payroll batch communications"}), 403
    
    db = get_db()
    users_col = db["users"]
    active_staff = list(users_col.find({"is_active": True}, {"employee_id": 1, "full_name": 1, "email": 1}))
    count = 0
    cycle = (request.get_json(silent=True) or {}).get("cycle") or "CURRENT_CYCLE"
    for s in active_staff:
        emp_id = s.get("employee_id")
        if emp_id and emp_id != actor.get("employee_id"):
            payload = {
                "recipient_id": emp_id,
                "recipient_email": s.get("email") or "",
                "subject": f"Confidential: Digital Payslip Dispatched & Available ({cycle})",
                "category": "PAYSLIP",
                "content": f"Dear {s.get('full_name') or emp_id},\n\nYour official digital payslip for cycle {cycle} has been authenticated, encrypted, and deposited into your HRMS portal.\n\nYou may view and download your verified payslip by navigating to Payroll & Compensation in your employee portal.\n\nWarm regards,\nFinance & Corporate Payroll Team\nAI Samrat Technologies",
                "is_confidential": True
            }
            EnterpriseMailboxService.send_user_mail(actor, payload)
            count += 1
            if count >= 20: # Batch sensible limit for immediate notification dispatch
                break
    return jsonify({
        "success": True,
        "message": f"Digital payslips notifications successfully dispatched to {count} active staff via Inbuilt Corporate Mailbox."
    }), 200


@api_bp.route("/search/global", methods=["GET"])
@require_auth
def global_enterprise_search_route():
    actor = request.current_user
    q = (request.args.get("q") or "").strip()
    
    db = get_db()
    staff_results = []
    project_results = []
    nav_results = []

    # Navigation catalog with permissions
    all_nav_routes = [
        {"title": "Employee Attendance & Biometrics", "desc": "Check clock-in, punch times & monthly roster", "url": "/attendance", "icon": "bi-clock-history", "roles": [Role.EMPLOYEE, Role.TEAM_LEAD, Role.MANAGER, Role.HR, Role.ADMIN], "keywords": ["attendance", "punch", "clock", "shift", "roster", "biometric", "in", "out"]},
        {"title": "Leave Administration & Requests", "desc": "Apply for casual, sick & progressive leaves", "url": "/leaves", "icon": "bi-calendar2-check", "roles": [Role.EMPLOYEE, Role.TEAM_LEAD, Role.MANAGER, Role.HR, Role.ADMIN], "keywords": ["leave", "vacation", "wfh", "time off", "permission", "apply"]},
        {"title": "Daily Work Diary & Deliverables", "desc": "Submit daily work logs before 7:00 PM cutoff", "url": "/work-diary", "icon": "bi-journal-check", "roles": [Role.EMPLOYEE, Role.TEAM_LEAD, Role.MANAGER, Role.HR, Role.ADMIN], "keywords": ["diary", "work", "log", "task", "daily", "sprint"]},
        {"title": "Official Corporate Mailbox", "desc": "Internal memos, formal communications & dispatches", "url": "/mailbox", "icon": "bi-envelope-paper", "roles": [Role.EMPLOYEE, Role.TEAM_LEAD, Role.MANAGER, Role.HR, Role.ADMIN], "keywords": ["mail", "mailbox", "memo", "email", "inbox", "message"]},
        {"title": "Team & Project Direct Chat", "desc": "Real-time communication channels & direct messages", "url": "/inbox", "icon": "bi-chat-dots", "roles": [Role.EMPLOYEE, Role.TEAM_LEAD, Role.MANAGER, Role.HR, Role.ADMIN], "keywords": ["chat", "message", "conversation", "team", "dm"]},
        {"title": "Staff Directory & Profiles", "desc": "Browse workforce profiles, skills & employment records", "url": "/profiles", "icon": "bi-people", "roles": [Role.TEAM_LEAD, Role.MANAGER, Role.HR, Role.ADMIN], "keywords": ["staff", "directory", "profile", "users", "employee", "roster"]},
        {"title": "Project Portfolio & Kanban", "desc": "Sprint boards, deliverables & task execution", "url": "/projects", "icon": "bi-kanban", "roles": [Role.TEAM_LEAD, Role.MANAGER, Role.HR, Role.ADMIN], "keywords": ["project", "projects", "kanban", "sprint", "milestone", "task"]},
        {"title": "Payroll Center & Payslips", "desc": "Salary structure, allowances, tax breakdown & slips", "url": "/payroll-center", "icon": "bi-wallet2", "roles": [Role.HR, Role.ADMIN], "keywords": ["payroll", "salary", "payslip", "slips", "compensation", "tax", "ctc"]},
        {"title": "Enterprise Recruitment & ATS", "desc": "Candidate pipelines, resume scanner & interviews", "url": "/recruitment", "icon": "bi-person-plus", "roles": [Role.TEAM_LEAD, Role.MANAGER, Role.HR, Role.ADMIN], "keywords": ["recruitment", "ats", "candidate", "interview", "hiring", "mrf"]},
        {"title": "Hardware Assets & Software Licenses", "desc": "Laptop allocation, monitors, peripheral requests", "url": "/assets", "icon": "bi-laptop", "roles": [Role.EMPLOYEE, Role.TEAM_LEAD, Role.MANAGER, Role.HR, Role.ADMIN], "keywords": ["asset", "hardware", "software", "license", "laptop", "equipment"]},
        {"title": "Meeting Rooms & Facility Booking", "desc": "Conference room availability and reservations", "url": "/facilities", "icon": "bi-door-open", "roles": [Role.EMPLOYEE, Role.TEAM_LEAD, Role.MANAGER, Role.HR, Role.ADMIN], "keywords": ["facility", "room", "meeting", "conference", "boardroom"]},
        {"title": "Corporate Policy Vault", "desc": "Company standards, compliance, code of conduct", "url": "/policies", "icon": "bi-file-earmark-lock", "roles": [Role.EMPLOYEE, Role.TEAM_LEAD, Role.MANAGER, Role.HR, Role.ADMIN], "keywords": ["policy", "vault", "guideline", "rules", "handbook", "code"]},
        {"title": "Company Holidays Calendar", "desc": "Statutory holidays, festival calendar & long weekends", "url": "/holidays", "icon": "bi-calendar-event", "roles": [Role.EMPLOYEE, Role.TEAM_LEAD, Role.MANAGER, Role.HR, Role.ADMIN], "keywords": ["holiday", "calendar", "festival", "vacation"]},
        {"title": "Team Birthdays & Celebrations", "desc": "Upcoming colleague birthdays & anniversary cheer", "url": "/birthdays", "icon": "bi-cake2", "roles": [Role.EMPLOYEE, Role.TEAM_LEAD, Role.MANAGER, Role.HR, Role.ADMIN], "keywords": ["birthday", "celebration", "anniversary"]},
        {"title": "Platform Security Audit Trail", "desc": "Immutable security ledger & compliance tracking", "url": "/audit-logs", "icon": "bi-shield-lock", "roles": [Role.HR, Role.ADMIN], "keywords": ["audit", "log", "security", "governance", "trail"]},
        {"title": "Organizational Platform Settings", "desc": "System parameters, thresholds & enterprise configuration", "url": "/settings", "icon": "bi-sliders", "roles": [Role.HR, Role.ADMIN], "keywords": ["setting", "config", "organization", "company", "system"]}
    ]

    actor_role = normalize_role(actor.get("role"))

    if q:
        q_lower = q.lower()
        # 1. Navigation search
        for item in all_nav_routes:
            item_roles = {normalize_role(r) for r in item["roles"]}
            if actor_role in item_roles:
                if q_lower in item["title"].lower() or q_lower in item["desc"].lower() or any(q_lower in kw for kw in item["keywords"]):
                    nav_results.append({
                        "title": item["title"],
                        "desc": item["desc"],
                        "url": item["url"],
                        "icon": item["icon"],
                        "category": "Navigation"
                    })

        # 2. Staff directory search (strictly RBAC-filtered via can_view_profile)
        query = {
            "$or": [
                {"employee_id": {"$regex": q, "$options": "i"}},
                {"full_name": {"$regex": q, "$options": "i"}},
                {"email": {"$regex": q, "$options": "i"}},
                {"department": {"$regex": q, "$options": "i"}},
                {"designation": {"$regex": q, "$options": "i"}}
            ]
        }
        for u in list(db["users"].find(query).limit(30)):
            if not can_view_profile(actor, u):
                continue
            staff_results.append({
                "employee_id": u.get("employee_id"),
                "full_name": u.get("full_name") or u.get("employee_id"),
                "role": (u.get("role") or "employee").replace("_", " ").title(),
                "department": u.get("department", "General"),
                "designation": u.get("designation", "Staff"),
                "email": u.get("email", ""),
                "url": f"/profile/{u.get('employee_id')}"
            })
            if len(staff_results) >= 8:
                break

        # 3. Project search (strictly gated by can_view_projects; HR has zero project access)
        if can_view_projects(actor):
            proj_query = {
                "$or": [
                    {"name": {"$regex": q, "$options": "i"}},
                    {"project_code": {"$regex": q, "$options": "i"}},
                    {"code": {"$regex": q, "$options": "i"}},
                    {"department": {"$regex": q, "$options": "i"}}
                ]
            }
            for p in list(db["projects"].find(proj_query).limit(5)):
                project_results.append({
                    "name": p.get("name") or p.get("project_code"),
                    "code": p.get("project_code") or p.get("code") or "PROJ",
                    "status": p.get("status", "Active"),
                    "url": "/projects"
                })
    else:
        # Default quick recommendations
        for item in all_nav_routes[:6]:
            item_roles = {normalize_role(r) for r in item["roles"]}
            if actor_role in item_roles:
                nav_results.append({
                    "title": item["title"],
                    "desc": item["desc"],
                    "url": item["url"],
                    "icon": item["icon"],
                    "category": "Quick Links"
                })

    return jsonify({
        "success": True,
        "query": q,
        "results": {
            "navigation": nav_results[:6],
            "staff": staff_results,
            "projects": project_results
        }
    }), 200


# --- 19.11 ATS Resume Scanner ---
@api_bp.route("/recruitment/ats/scan", methods=["POST"])
@require_roles(Role.HR, Role.ADMIN, Role.MANAGER, Role.TEAM_LEAD)
def scan_ats_resume_route():
    body = request.get_json(silent=True) or {}
    resume_text = body.get("resume_text", "").strip()
    target_role = body.get("target_role", "Software Engineer").strip()
    required_skills = body.get("required_skills")
    if not resume_text:
        return jsonify({"error": "Resume text content is required for ATS analysis."}), 400

    result = RecruitmentTalentService.scan_resume(resume_text, target_role, required_skills)
    return jsonify({"success": True, **result}), 200


@api_bp.route("/recruitment/ats/upload-scan", methods=["POST"])
@require_roles(Role.HR, Role.ADMIN, Role.MANAGER, Role.TEAM_LEAD, Role.TL)
def upload_scan_ats_resume_route():
    file = request.files.get("resume_file") or request.files.get("file")
    if not file or not file.filename:
        return jsonify({"error": "No resume file was attached to the request."}), 400

    filename = file.filename
    target_role = request.form.get("target_role", "Senior Backend Architect").strip()

    text, err = RecruitmentTalentService.extract_text_from_file(file, filename)
    if err or not text:
        return jsonify({"error": err or "Failed to extract readable text from document."}), 400

    scan_result = RecruitmentTalentService.scan_resume(text, target_role)
    word_count = len(text.split())

    return jsonify({
        "success": True,
        "filename": filename,
        "word_count": word_count,
        "extracted_text": text,
        **scan_result
    }), 200


# ============================================================================
#   TIIMI SAAS HRM - OVERTIME & TIME MANAGEMENT SUITE
# ============================================================================

@api_bp.route("/overtime/list", methods=["GET"])
@require_auth
def get_overtime_list():
    """Returns overtime requests with optional employee, month, or status filters, strictly RBAC-scoped."""
    from services.overtime_service import OvertimeService
    emp_id = request.args.get("employee_id")
    status = request.args.get("status")
    month = request.args.get("month")

    actor = request.current_user
    # Employees are strictly forced to self records
    if actor.get("role") == Role.EMPLOYEE:
        emp_id = actor.get("employee_id") or actor.get("emp_id")

    requests_list = OvertimeService.get_overtime_requests(
        employee_id=emp_id,
        status=status,
        month=month,
        actor=actor
    )
    return jsonify({"success": True, "overtime_requests": requests_list}), 200


@api_bp.route("/overtime/request", methods=["POST"])
@require_auth
def submit_overtime_request():
    """Allows an employee or manager to submit a new overtime request."""
    from services.overtime_service import OvertimeService
    data = request.get_json(silent=True) or {}
    emp_id = data.get("employee_id") or request.current_user["employee_id"]
    overtime_date = data.get("overtime_date")
    start_time = data.get("start_time") or "07:00 PM"
    end_time = data.get("end_time") or "09:00 PM"
    reason = data.get("reason", "").strip()
    ot_type = data.get("overtime_type", "After shift")

    if not overtime_date or not reason:
        return jsonify({"error": "Overtime date and reason are required."}), 400

    try:
        req = OvertimeService.request_overtime(
            employee_id=emp_id,
            overtime_date=overtime_date,
            start_time=start_time,
            end_time=end_time,
            reason=reason,
            overtime_type=ot_type,
            notes=data.get("notes", "")
        )
        return jsonify({"success": True, "message": "Overtime request submitted successfully.", "request": req}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@api_bp.route("/overtime/review", methods=["POST"])
@require_roles(Role.TEAM_LEAD, Role.MANAGER, Role.HR, Role.ADMIN)
def review_overtime_request():
    """Approves or rejects an overtime request with optional approved hours adjustment."""
    from services.overtime_service import OvertimeService
    data = request.get_json(silent=True) or {}
    request_id = data.get("request_id")
    action = data.get("action")  # 'Approved' or 'Rejected'
    approved_start = data.get("approved_start_time")
    approved_end = data.get("approved_end_time")
    remarks = data.get("reviewer_remarks")

    if not request_id or not action:
        return jsonify({"error": "request_id and action ('Approved'/'Rejected') are required."}), 400

    actor = request.current_user
    reviewer_name = actor.get("full_name") or actor.get("name") or actor["employee_id"]

    try:
        result = OvertimeService.review_overtime_request(
            request_id=request_id,
            reviewer_id=actor["employee_id"],
            reviewer_name=reviewer_name,
            action=action,
            approved_start_time=approved_start,
            approved_end_time=approved_end,
            reviewer_remarks=remarks
        )
        return jsonify({"success": True, "message": f"Overtime request {action.lower()} successfully.", "request": result}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@api_bp.route("/overtime/kpi", methods=["GET"])
@require_auth
def get_overtime_kpi():
    """Computes month-over-month Overtime KPIs matching Tiimi SaaS HRM design."""
    from services.overtime_service import OvertimeService
    emp_id = request.args.get("employee_id") or request.current_user["employee_id"]
    month = request.args.get("month")
    kpis = OvertimeService.get_overtime_kpis(employee_id=emp_id, month=month)
    return jsonify({"success": True, "kpis": kpis}), 200


@api_bp.route("/attendance/tiimi-timeline", methods=["GET"])
@require_auth
def get_tiimi_timeline():
    """Returns visual timeline and month-over-month KPIs matching Tiimi design."""
    from services.attendance_service import AttendanceService
    emp_id = request.args.get("employee_id") or request.current_user["employee_id"]
    month = request.args.get("month")
    data = AttendanceService.get_tiimi_timeline_data(employee_id=emp_id, month=month)
    return jsonify({"success": True, **data}), 200


@api_bp.route("/users/pagination-meta", methods=["GET"])
@require_auth
def get_user_pagination_meta():
    """
    Computes previous, current, next, and total employee count for staff switcher.
    Strictly RBAC-scoped:
    - Employees: CANNOT paginate other employees (returns can_paginate: False).
    - Team Leads: Can only paginate members of their assigned team.
    - Managers: Can only paginate employees within their department/projects.
    - HR & Admin: Full company directory pagination (100 users).
    """
    actor = request.current_user
    role = normalize_role(actor.get("role"))
    actor_id = actor.get("employee_id") or actor.get("emp_id")
    db = get_db()
    current_emp_id = request.args.get("employee_id") or actor_id

    # 1. Employee Isolation: Zero access to other employee IDs
    if role == Role.EMPLOYEE:
        return jsonify({
            "success": True,
            "current_id": actor_id,
            "current_index": 1,
            "total_count": 1,
            "prev_id": None,
            "next_id": None,
            "can_paginate": False
        }), 200

    # 2. Team Lead Scope: Only assigned active employees
    query = {"is_active": True}
    if role == Role.TL:
        query["role"] = Role.EMPLOYEE
        tl_teams = [t["team_id"] for t in db.teams.find({"$or": [{"lead_employee_id": actor_id}, {"lead_id": actor_id}]}, {"team_id": 1}) if t.get("team_id")]
        if actor.get("team_id"):
            tl_teams.append(actor.get("team_id"))
        tl_clauses = [{"assigned_tl_id": actor_id}, {"team_lead_id": actor_id}]
        if tl_teams:
            tl_clauses.append({"team_id": {"$in": list(set(tl_teams))}})
        query["$or"] = tl_clauses

    # 3. Manager Scope: Direct reports and department Employees / TLs (never Admin/HR or cross-department)
    elif role == Role.MANAGER:
        query["role"] = {"$in": [Role.EMPLOYEE, Role.TEAM_LEAD, Role.TL]}
        mgr_clauses = [{"manager_id": actor_id}, {"reporting_manager_id": actor_id}]
        dept = actor.get("department")
        if dept and dept not in ("Management", "Executive", "Executive HR"):
            mgr_clauses.append({"department": dept})
        elif actor.get("team_id"):
            mgr_clauses.append({"team_id": actor.get("team_id")})
        query["$or"] = mgr_clauses

    users = list(db.users.find(query, {"employee_id": 1, "emp_id": 1}).sort("employee_id", 1))
    emp_ids = [u.get("employee_id") or u.get("emp_id") for u in users if (u.get("employee_id") or u.get("emp_id"))]

    total_count = len(emp_ids)
    if total_count == 0:
        return jsonify({
            "success": True,
            "current_id": current_emp_id,
            "current_index": 1,
            "total_count": 1,
            "prev_id": None,
            "next_id": None,
            "can_paginate": False
        }), 200

    try:
        cur_idx = emp_ids.index(current_emp_id)
    except ValueError:
        cur_idx = 0

    prev_id = emp_ids[cur_idx - 1] if cur_idx > 0 else emp_ids[-1] if total_count > 1 else current_emp_id
    next_id = emp_ids[cur_idx + 1] if cur_idx < total_count - 1 else emp_ids[0] if total_count > 1 else current_emp_id

    return jsonify({
        "success": True,
        "current_id": current_emp_id,
        "current_index": cur_idx + 1,
        "total_count": total_count,
        "prev_id": prev_id,
        "next_id": next_id,
        "can_paginate": total_count > 1
    }), 200


@api_bp.route("/users/<employee_id>/update-tiimi-profile", methods=["POST"])
@require_auth
def update_tiimi_profile(employee_id):
    """Updates Tiimi profile fields: personal info, contacts, addresses, notes, and tags."""
    actor = request.current_user
    db = get_db()
    target = db.users.find_one({"$or": [{"employee_id": employee_id}, {"emp_id": employee_id}]})
    if not target:
        return jsonify({"error": f"Employee {employee_id} not found."}), 404

    actor_id = (actor.get("employee_id") or actor.get("emp_id") or "").strip().upper()
    target_id = (target.get("employee_id") or target.get("emp_id") or "").strip().upper()
    is_self = bool(actor_id and target_id and actor_id == target_id)
    is_admin_or_hr = normalize_role(actor.get("role")) in (Role.ADMIN, Role.HR)

    if not is_self and not is_admin_or_hr:
        return jsonify({"error": "Unauthorized: You can only edit your own profile."}), 403

    body = request.get_json(silent=True) or {}
    allowed_fields = [
        "gender", "marital_status", "religion", "place_of_birth", "birthdate", "blood_type", "age",
        "phone_number", "other_contact", "residential_address", "citizen_id_address", "notes", "tags"
    ]
    if is_admin_or_hr:
        allowed_fields.extend(["job_role", "job_level", "employment_status", "date_started"])

    updates = {}
    for f in allowed_fields:
        if f in body:
            updates[f] = body[f]

    if updates:
        db.users.update_one({"$or": [{"employee_id": employee_id}, {"emp_id": employee_id}]}, {"$set": updates})

    updated_user = db.users.find_one({"$or": [{"employee_id": employee_id}, {"emp_id": employee_id}]})
    if updated_user:
        updated_user.pop("activation_token", None)
    return jsonify({"success": True, "message": "Profile updated successfully.", "user": serialize_doc(updated_user)}), 200


# =========================================================================
# SHIFT PROFILES & EMPLOYEE SHIFT ALLOCATION (ORGANIZATION SETTINGS)
# =========================================================================

@api_bp.route("/shifts", methods=["GET"])
@require_auth
def get_shift_profiles():
    shifts = RosterService.get_shift_profiles(actor=request.current_user)
    return jsonify({"success": True, "shifts": shifts}), 200


@api_bp.route("/shifts", methods=["POST"])
@require_roles(Role.HR, Role.ADMIN)
def save_shift_profile():
    actor = request.current_user
    data = request.get_json(silent=True) or {}
    saved, err = RosterService.save_shift_profile(actor, data)
    if err:
        return jsonify({"error": err}), 403 if "Unauthorized" in err else 400
    return jsonify({"success": True, "shift": saved}), 200


@api_bp.route("/shifts/<shift_id>", methods=["DELETE"])
@require_roles(Role.HR, Role.ADMIN)
def delete_shift_profile(shift_id):
    actor = request.current_user
    ok, err = RosterService.delete_shift_profile(actor, shift_id)
    if err:
        return jsonify({"error": err}), 403 if "Unauthorized" in err else 400
    return jsonify({"success": True, "message": "Shift profile deleted."}), 200


@api_bp.route("/shifts/assign", methods=["POST"])
@require_roles(Role.HR, Role.ADMIN, Role.MANAGER)
def assign_shift_employees():
    actor = request.current_user
    data = request.get_json(silent=True) or {}
    shift_id = data.get("shift_id")
    employee_ids = data.get("employee_ids") or []
    department = data.get("department")

    result, err = RosterService.assign_employees_to_shift(actor, shift_id, employee_ids=employee_ids, department=department)
    if err:
        code = 403 if ("Unauthorized" in err or "Access Denied" in err) else 400
        return jsonify({"error": err}), code
    return jsonify(result), 200




