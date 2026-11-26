import pytest
from datetime import datetime, timezone, timedelta
from backend.services.leave_service import LeaveService
from backend.services.attendance_service import AttendanceService
from backend.services.project_service import ProjectService
from backend.services.otp_service import OtpService, OtpPurpose
from backend.permissions.rbac import Role, can_approve_leave, can_view_profile, can_edit_profile
from backend.auth.security import hash_password, generate_jwt_token
from backend.utils.timezone import now_utc, get_local_date_str


def test_section_1_two_stage_leave_approval_workflow(db, seeded_users):
    """
    Section 1: Leave Request — Two-Stage Approval Workflow
    - Employee submit -> PENDING_TEAM_LEAD
    - TL approves -> PENDING_MANAGER
    - Manager approves -> APPROVED
    - TL rejects -> REJECTED, stops workflow
    - TL personal leave -> PENDING_MANAGER
    - TL cannot self-approve
    - Manager cannot self-approve -> PENDING_AUTHORIZATION
    """
    emp = seeded_users["emp1"]
    tl = seeded_users["team_lead"]
    mgr = seeded_users["manager"]
    emp2 = seeded_users["emp2"]

    # Configure reporting: emp is in tl's team, tl reports to mgr
    db.users.update_one({"employee_id": emp["employee_id"]}, {"$set": {"team_id": tl.get("team_id", "TEAM-TEST-ENG"), "reporting_manager_id": tl["employee_id"]}})
    emp["team_id"] = tl.get("team_id", "TEAM-TEST-ENG")
    emp["reporting_manager_id"] = tl["employee_id"]

    db.users.update_one({"employee_id": tl["employee_id"]}, {"$set": {"reporting_manager_id": mgr["employee_id"]}})
    tl["reporting_manager_id"] = mgr["employee_id"]

    # 1. Employee submits leave request
    leave_doc, err = LeaveService.apply_leave(emp, {
        "leave_type": "Casual Leave",
        "start_date": "2026-11-20",
        "end_date": "2026-11-21",
        "reason": "Family wedding attendance"
    })
    assert err is None
    req_id = leave_doc["request_id"]
    assert leave_doc["status"] == "PENDING_TEAM_LEAD"
    assert leave_doc["assigned_tl_id"] == tl["employee_id"]
    assert leave_doc["assigned_manager_id"] == mgr["employee_id"]

    # 2. Team Lead approval moves request to PENDING_MANAGER
    tl_doc, err_tl = LeaveService.verify_request(tl, req_id, "Approved", "TL approved for project coverage")
    assert err_tl is None
    assert tl_doc["status"] == "PENDING_MANAGER"
    assert tl_doc["tl_reviewed_by_id"] == tl["employee_id"]
    assert tl_doc["tl_review_remarks"] == "TL approved for project coverage"
    assert len(tl_doc["approval_history"]) >= 1

    # 3. Manager final approval marks APPROVED
    mgr_doc, err_mgr = LeaveService.verify_request(mgr, req_id, "Approved", "Final approval granted by Manager")
    assert err_mgr is None
    assert mgr_doc["status"] in ("Approved", "APPROVED")
    assert mgr_doc["reviewed_by_id"] == mgr["employee_id"]
    assert mgr_doc["review_remarks"] == "Final approval granted by Manager"

    # 4. Rejection at TL stage stops workflow
    perm_doc, _ = LeaveService.apply_permission(emp, {
        "permission_date": "2026-11-22",
        "early_exit_time": "15:00",
        "reason": "Personal errands"
    })
    perm_id = perm_doc["request_id"]
    rej_doc, err_rej = LeaveService.verify_request(tl, perm_id, "Rejected", "Workload is critical on this date")
    assert err_rej is None
    assert rej_doc["status"] in ("Rejected", "REJECTED")
    assert rej_doc["rejection_reason"] == "Workload is critical on this date"

    # 5. Team Lead personal leave goes directly to Manager
    tl_leave, err_tl_apply = LeaveService.apply_leave(tl, {
        "leave_type": "Sick Leave",
        "start_date": "2026-11-25",
        "end_date": "2026-11-25",
        "reason": "Medical appointment"
    })
    assert err_tl_apply is None
    assert tl_leave["status"] == "PENDING_MANAGER"
    assert tl_leave["assigned_manager_id"] == mgr["employee_id"]

    # TL cannot self-approve
    _, err_tl_self = LeaveService.verify_request(tl, tl_leave["request_id"], "Approved", "Self approve")
    assert "Self-approval of leave requests is strictly forbidden" in err_tl_self

    # Manager approves TL personal leave
    approved_tl_leave, err_mgr_tl = LeaveService.verify_request(mgr, tl_leave["request_id"], "Approved", "Approved for medical leave")
    assert err_mgr_tl is None
    assert approved_tl_leave["status"] in ("Approved", "APPROVED")

    # 6. Manager personal leave enters PENDING_AUTHORIZATION
    mgr_leave, _ = LeaveService.apply_leave(mgr, {
        "leave_type": "Casual Leave",
        "start_date": "2026-11-28",
        "end_date": "2026-11-29",
        "reason": "Personal leave"
    })
    assert mgr_leave["status"] == "PENDING_AUTHORIZATION"
    _, err_mgr_self = LeaveService.verify_request(mgr, mgr_leave["request_id"], "Approved", "Self approve")
    assert "Self-approval of leave requests is strictly forbidden" in err_mgr_self


def test_section_2_manager_to_hr_leave_forwarding_and_hr_correspondence(client, db, seeded_users):
    """
    Section 2: Manager-to-HR Leave Email Forwarding & HR Correspondence
    - Manager forwards approved leave email
    - Recorded in leave_requests.email_history
    - HR correspondence endpoint GET /api/leaves/correspondence displays forwarded items
    - HR cannot approve leave
    """
    emp = seeded_users["emp1"]
    mgr = seeded_users["manager"]
    hr = seeded_users["hr"]

    # Seed an approved leave
    db.leave_requests.insert_one({
        "request_id": "LR-FWD-101",
        "employee_id": emp["employee_id"],
        "employee_name": emp["full_name"],
        "department": emp.get("department", "Engineering"),
        "request_type": "LEAVE",
        "leave_type": "Casual Leave",
        "start_date": "2026-12-01",
        "end_date": "2026-12-02",
        "days_count": 2.0,
        "reason": "Conference",
        "status": "APPROVED",
        "review_remarks": "Approved by Manager",
        "reviewed_by_id": mgr["employee_id"],
        "reviewed_by_name": mgr["full_name"],
        "reviewed_at": now_utc(),
        "email_history": [],
        "created_at": now_utc()
    })

    # Manager sends notification to HR
    mgr_token = generate_jwt_token(mgr)
    fwd_res = client.post("/api/leaves/LR-FWD-101/send-email", headers={"Authorization": f"Bearer {mgr_token}"}, json={
        "to": "hr@aisamrat.com",
        "cc": "operations@aisamrat.com",
        "subject": "Leave Approval Notification — Employee One",
        "message": "Employee One has been approved for leave on Dec 1-2."
    })
    assert fwd_res.status_code == 200
    data = fwd_res.get_json()
    assert data["success"] is True

    # HR queries correspondence
    hr_token = generate_jwt_token(hr)
    corr_res = client.get("/api/leaves/correspondence", headers={"Authorization": f"Bearer {hr_token}"})
    assert corr_res.status_code == 200
    corr_data = corr_res.get_json()
    assert "correspondence" in corr_data
    assert len(corr_data["correspondence"]) >= 1
    found_corr = next((c for c in corr_data["correspondence"] if c["request_id"] == "LR-FWD-101"), None)
    assert found_corr is not None
    assert found_corr["sender_name"] == mgr["full_name"]
    assert found_corr["recipient"] == "hr@aisamrat.com"
    assert found_corr["subject"] == "Leave Approval Notification — Employee One"

    # HR cannot approve leave requests
    verify_res = client.post("/api/leaves/verify/LR-FWD-101", headers={"Authorization": f"Bearer {hr_token}"}, json={
        "action": "Approved", "remarks": "HR attempt"
    })
    assert verify_res.status_code == 403


def test_section_3_chat_room_email_composer(client, db, seeded_users):
    """
    Section 3: Email Composer Inside Chat Room Only
    - GET /api/chat/authorized-email-recipients returns real company registered emails
    - POST /api/chat/compose-email dispatches email and logs record
    """
    emp = seeded_users["emp1"]
    mgr = seeded_users["manager"]
    token = generate_jwt_token(emp)

    # 1. Authorized email recipients lookup
    recip_res = client.get("/api/chat/authorized-email-recipients", headers={"Authorization": f"Bearer {token}"})
    assert recip_res.status_code == 200
    recips = recip_res.get_json().get("recipients", [])
    assert len(recips) >= 1
    mgr_entry = next((r for r in recips if r["employee_id"] == mgr["employee_id"]), None)
    assert mgr_entry is not None
    assert mgr_entry["email"] == mgr["email"]

    # 2. Compose and dispatch email
    comp_res = client.post("/api/chat/compose-email", headers={"Authorization": f"Bearer {token}"}, json={
        "to_email": mgr["email"],
        "cc_email": "",
        "subject": "Sprint Progress Update",
        "message": "Hello Manager, here is the sprint progress update."
    })
    assert comp_res.status_code == 200
    comp_data = comp_res.get_json()
    assert comp_data["success"] is True
    assert comp_data["status"] in ("SENT", "SIMULATED", "FAILED")

    # Check external message logs
    log_doc = db.external_message_logs.find_one({"sender_id": emp["employee_id"], "subject": "Sprint Progress Update"})
    assert log_doc is not None
    assert (log_doc.get("to") or log_doc.get("recipient_target")) == mgr["email"]


def test_section_4_change_password_with_verified_otp(client, db):
    """
    Section 4: Profile and Account Menu — Change Password with Email OTP
    - Request OTP to registered email
    - OTP required to change password
    - Invalid OTP rejected
    """
    email = "passchange.user@aisamrat.com"
    emp_user = {
        "employee_id": "EMP-PASS-01",
        "full_name": "Password Test User",
        "email": email,
        "role": Role.EMPLOYEE,
        "password_hash": hash_password("OldSecret@2026!"),
        "is_active": True,
        "is_email_verified": True,
        "created_at": now_utc()
    }
    db.users.insert_one(emp_user)
    token = generate_jwt_token(emp_user)
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Request OTP
    otp_req = client.post("/api/auth/change-password/request-otp", headers=headers)
    assert otp_req.status_code == 200
    assert otp_req.get_json()["success"] is True

    plain_otp = OtpService.get_latest_otp_for_test(email, OtpPurpose.PASSWORD_CHANGE)
    assert plain_otp is not None

    # 2. Attempt change with wrong OTP -> 400
    bad_res = client.post("/api/auth/change-password", headers=headers, json={
        "current_password": "OldSecret@2026!",
        "new_password": "NewSecret@2026!Strong",
        "otp_code": "000000"
    })
    assert bad_res.status_code == 400

    # 3. Attempt change with correct OTP -> 200
    ok_res = client.post("/api/auth/change-password", headers=headers, json={
        "current_password": "OldSecret@2026!",
        "new_password": "NewSecret@2026!Strong",
        "otp_code": plain_otp
    })
    assert ok_res.status_code == 200
    assert ok_res.get_json()["success"] is True

    # 4. Old password rejected, new password accepted
    old_login = client.post("/api/auth/login", json={"email": email, "password": "OldSecret@2026!", "role": "employee"})
    assert old_login.status_code == 401
    new_login = client.post("/api/auth/login", json={"email": email, "password": "NewSecret@2026!Strong", "role": "employee"})
    assert new_login.status_code == 200


def test_section_6_automated_7pm_attendance_cutoff(db, seeded_users):
    """
    Section 6: Automatic 7 PM Attendance Hard Cutoff
    - Closes eligible active login sessions
    - Sets SYSTEM_CUTOFF event
    - Auto-closes active break
    - Sets is_online=False
    - Idempotent: running again does not double-close or duplicate
    """
    emp = seeded_users["emp1"]
    today = get_local_date_str()
    session_id = f"SESS-{emp['employee_id']}-CUTOFF"

    # Seed an open session and open break for today
    t0 = datetime(2026, 11, 1, 9, 0, 0, tzinfo=timezone.utc)
    t_break = datetime(2026, 11, 1, 13, 0, 0, tzinfo=timezone.utc)

    db.attendance_events.insert_many([
        {
            "employee_id": emp["employee_id"],
            "session_id": session_id,
            "event_type": "LOGIN",
            "timestamp": t0,
            "date": today,
            "is_closed": False
        },
        {
            "employee_id": emp["employee_id"],
            "session_id": session_id,
            "event_type": "BREAK_START",
            "timestamp": t_break,
            "date": today,
            "is_closed": False,
            "notes": "Lunch"
        }
    ])
    db.users.update_one({"employee_id": emp["employee_id"]}, {"$set": {"is_online": True}})

    # Execute Cutoff
    closed_sessions = AttendanceService.execute_7pm_attendance_cutoff()
    assert len(closed_sessions) >= 1

    # Check login event is marked closed
    login_evt = db.attendance_events.find_one({"session_id": session_id, "event_type": "LOGIN"})
    assert login_evt["is_closed"] is True

    # Check break is closed
    break_end_evt = db.attendance_events.find_one({"session_id": session_id, "event_type": "BREAK_END"})
    assert break_end_evt is not None
    assert break_end_evt["event_source"] == "SYSTEM_CUTOFF"

    # Check system checkout logout event is created
    logout_evt = db.attendance_events.find_one({"session_id": session_id, "event_type": "LOGOUT"})
    assert logout_evt is not None
    assert logout_evt["event_source"] == "SYSTEM_CUTOFF"
    assert "7 PM" in logout_evt["reason"]

    # Check user online flag is cleared
    user_doc = db.users.find_one({"employee_id": emp["employee_id"]})
    assert user_doc.get("is_online") is False

    # Check daily summary has_open_session is False
    daily_doc = db.attendance_daily.find_one({
        "employee_id": emp["employee_id"],
        "$or": [{"attendance_date": today}, {"date": today}]
    })
    assert daily_doc is not None
    assert daily_doc["has_open_session"] is False

    # Idempotency check: running again closes 0 sessions and creates NO duplicate logout
    closed_sessions2 = AttendanceService.execute_7pm_attendance_cutoff()
    assert len(closed_sessions2) == 0
    logout_count = db.attendance_events.count_documents({"session_id": session_id, "event_type": "LOGOUT"})
    assert logout_count == 1


def test_section_7_and_8_project_management_edit_delete_approval(db, seeded_users):
    """
    Sections 7 & 8: Projects Create, Edit, Delete, Approval & Real Member Assignment
    - TL creates project proposal -> PENDING_APPROVAL, no chat yet
    - Manager approves -> ACTIVE, creates group chat
    - Edit project updates fields
    - Manager safe delete/archive sets is_deleted=True
    - Manager can query dummy project candidates
    """
    emp1 = seeded_users["emp1"]
    emp2 = seeded_users["emp2"]
    tl = seeded_users["team_lead"]
    mgr = seeded_users["manager"]

    # 1. TL creates proposal
    proj_doc, err = ProjectService.create_project(tl, {
        "name": "Cloud Security Portal",
        "description": "Enterprise cloud security governance suite",
        "objectives": "Zero-trust IAM and container security scanning",
        "deliverables": "Auth service, telemetry agent, report generator",
        "start_date": "2026-11-15",
        "expected_completion_date": "2026-12-30",
        "priority": "High",
        "status": "In Progress",
        "category": "Security",
        "assigned_manager": mgr["employee_id"],
        "selected_members": [emp1["employee_id"], emp2["employee_id"]],
        "project_lead": tl["employee_id"]
    })
    assert err is None
    project_id = proj_doc["project_id"]
    assert proj_doc["status"] == "PENDING_APPROVAL"

    # No chat before approval
    assert db.conversations.find_one({"project_id": project_id}) is None

    # 2. Manager approves
    app_doc, app_err = ProjectService.approve_project(mgr, project_id, review_notes="Approved for Q4")
    assert app_err is None
    assert app_doc["status"] == "ACTIVE"

    # Chat created after approval
    conv = db.conversations.find_one({"project_id": project_id})
    assert conv is not None
    assert conv["is_group"] is True
    assert tl["employee_id"] in conv["participants"]
    assert mgr["employee_id"] in conv["participants"]
    assert emp1["employee_id"] in conv["participants"]

    # 3. Edit project
    edited_doc, edit_err = ProjectService.edit_project(mgr, project_id, {
        "objectives": "Updated zero-trust IAM scope with FedRAMP compliance",
        "priority": "Critical"
    })
    assert edit_err is None
    assert edited_doc["objectives"] == "Updated zero-trust IAM scope with FedRAMP compliance"
    assert edited_doc["priority"] == "Critical"

    # 4. Dummy candidates query
    db.projects.insert_one({
        "project_id": "PRJ-DUMMY-99",
        "name": "Test Sandbox Demo Project",
        "status": "PENDING_APPROVAL",
        "is_deleted": False,
        "is_demo_project": True
    })
    dummy_cands = ProjectService.get_dummy_projects_for_review(mgr)
    assert any(p["project_id"] == "PRJ-DUMMY-99" for p in dummy_cands)

    # 5. Safe delete / archive
    ok_del, del_msg = ProjectService.delete_or_archive_project(mgr, "PRJ-DUMMY-99", reason="Cleaned dummy demo")
    assert ok_del is True
    del_doc = db.projects.find_one({"project_id": "PRJ-DUMMY-99"})
    assert del_doc["is_deleted"] is True
    assert del_doc["status"] == "ARCHIVED"


def test_section_9_and_10_staff_directory_rbac_and_profile_edit_restriction(client, db, seeded_users):
    """
    Sections 9 & 10: Staff Directory Role Visibility & Manager/TL Profile Edit Restrictions
    - TL sees ONLY normal active employees on their team
    - Manager sees ONLY normal active employees in scope
    - TL and Manager CANNOT edit employee profile (403 Forbidden)
    - Direct API access enforces this restriction
    """
    tl = seeded_users["team_lead"]
    mgr = seeded_users["manager"]
    hr = seeded_users["hr"]
    emp1 = seeded_users["emp1"]
    emp2 = seeded_users["emp2"]

    # Assign emp1 to tl's team, emp2 to another team
    tl_team = tl.get("team_id", "TEAM-TEST-ENG")
    db.users.update_one({"employee_id": emp1["employee_id"]}, {"$set": {"team_id": tl_team}})
    db.users.update_one({"employee_id": emp2["employee_id"]}, {"$set": {"team_id": "TEAM-OTHER"}})
    emp1["team_id"] = tl_team
    emp2["team_id"] = "TEAM-OTHER"

    # 1. Staff Directory listing via API: TL query
    tl_token = generate_jwt_token(tl)
    tl_users_res = client.get("/api/users?active_only=true", headers={"Authorization": f"Bearer {tl_token}"})
    assert tl_users_res.status_code == 200
    tl_user_list = tl_users_res.get_json().get("users", [])
    # TL must ONLY see employees in their team
    user_ids = [u["employee_id"] for u in tl_user_list]
    assert emp1["employee_id"] in user_ids
    assert emp2["employee_id"] not in user_ids
    assert hr["employee_id"] not in user_ids
    assert mgr["employee_id"] not in user_ids

    # 2. can_view_profile RBAC helper
    assert can_view_profile(tl, emp1) is True
    assert can_view_profile(tl, emp2) is False
    assert can_view_profile(tl, hr) is False
    assert can_view_profile(tl, mgr) is False

    # 3. TL cannot edit Employee profile
    tl_edit_res = client.put(f"/api/users/{emp1['employee_id']}", headers={"Authorization": f"Bearer {tl_token}"}, json={
        "designation": "Staff Architect",
        "department": "Executive"
    })
    assert tl_edit_res.status_code == 403

    # 4. Manager cannot edit Employee profile
    mgr_token = generate_jwt_token(mgr)
    mgr_edit_res = client.put(f"/api/users/{emp1['employee_id']}", headers={"Authorization": f"Bearer {mgr_token}"}, json={
        "designation": "Principal Engineer"
    })
    assert mgr_edit_res.status_code == 403

    # 5. can_edit_profile helper
    assert can_edit_profile(tl, emp1) is False
    assert can_edit_profile(mgr, emp1) is False
    assert can_edit_profile(hr, emp1) is True
    assert can_edit_profile(emp1, emp1) is True
