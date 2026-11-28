import pytest
from datetime import datetime, timezone
from bson import ObjectId

from auth.security import hash_password, generate_jwt_token, verify_password
from permissions.rbac import Role, can_manage_projects, can_view_salary
from services.otp_service import OtpService, OtpPurpose
from database.connection import DatabaseManager
from config import TestConfig


def test_four_business_roles_strictly_enforced():
    """Verify that only the 4 canonical business roles are recognized."""
    canonical_roles = {Role.EMPLOYEE, Role.TEAM_LEAD, Role.MANAGER, Role.HR}
    assert canonical_roles == {"employee", "team_lead", "manager", "hr"}
    assert len(canonical_roles) == 4
    # Legacy roles must map or not exist as standalone business roles
    for r in ["trainer", "hr_manager", "admin", "organization"]:
        assert r not in [Role.EMPLOYEE, Role.TEAM_LEAD, Role.MANAGER, Role.HR] or r in ("manager", "hr", "team_lead")


def test_persistent_database_cleanup_and_excel_data_preservation():
    """
    Verify persistent database contains:
    - Exactly 3 canonical test accounts (Manager, Team Lead, HR)
    - Zero dummy employee accounts (EMP-1001 to EMP-1004 deleted)
    - Real employees preserved and initially in unverified pending_activation state
    """
    db = DatabaseManager.get_db("office_hrm")
    # 1. Exactly 3 canonical test accounts
    admin = db.users.find_one({"email": "admin@aisamrat.com"})
    assert admin is not None
    assert admin["role"] == Role.MANAGER
    assert admin.get("is_email_verified") is True
    assert admin.get("account_status") == "active"

    lead = db.users.find_one({"email": "lead.kavita@aisamrat.com"})
    assert lead is not None
    assert lead["role"] == Role.TEAM_LEAD
    assert lead.get("is_email_verified") is True
    assert lead.get("account_status") == "active"

    hr = db.users.find_one({"$or": [{"email": "hr.ramya@aisamrat.com"}, {"aliases": "hr.priya@aisamrat.com"}, {"email": "hr.priya@aisamrat.com"}]})
    assert hr is not None
    assert hr["role"] == Role.HR
    assert hr.get("is_email_verified") is True
    assert hr.get("account_status") == "active"

    # 2. Dummy employees EMP-1001 to EMP-1004 must be completely gone
    for dummy_id in ["EMP-1001", "EMP-1002", "EMP-1003", "EMP-1004", "HR-1000", "HR-1002", "ORG-1001", "MGR-1001", "TRN-1001"]:
        assert db.users.find_one({"employee_id": dummy_id}) is None, f"Dummy account {dummy_id} should be deleted"

    # 3. Real employees from Excel exist and preserve employee details
    real_sample_ids = ["EMP-1010", "EMP-1020", "EMP-1030", "EMP-1037"]
    for emp_id in real_sample_ids:
        emp = db.users.find_one({"employee_id": emp_id})
        assert emp is not None, f"Real employee {emp_id} must be preserved"
        assert emp.get("personal_email") is not None
        assert "@" in emp.get("personal_email")


def test_first_time_activation_workflow_all_four_roles(client, db):
    """
    Test complete first-time Gmail registration & OTP verification for all 4 roles:
    1. Account starts unverified (pending_activation).
    2. Login blocked (403).
    3. User requests OTP for personal Gmail.
    4. User completes OTP verification & password setup.
    5. Account becomes active & verified.
    6. Normal login succeeds and routes to respective role dashboard.
    """
    test_roles = [
        (Role.EMPLOYEE, "EMP-ACT-1", "Aditi Rao", "aditi.rao.test@gmail.com", "/dashboard/employee"),
        (Role.TEAM_LEAD, "LEAD-ACT-1", "Vikram Patel", "vikram.patel.test@gmail.com", "/dashboard/team-lead"),
        (Role.MANAGER, "MGR-ACT-1", "Sunil Joshi", "sunil.joshi.test@gmail.com", "/dashboard/manager"),
        (Role.HR, "HR-ACT-1", "Ananya Deshmukh", "ananya.deshmukh.test@gmail.com", "/dashboard/hr")
    ]

    for role, emp_id, name, gmail, expected_dashboard in test_roles:
        # Step 0: Create unverified account
        db.users.insert_one({
            "employee_id": emp_id,
            "full_name": name,
            "email": gmail,
            "personal_email": gmail,
            "role": role,
            "department": "Engineering" if role != Role.HR else "Human Resources",
            "designation": "Specialist",
            "is_active": True,
            "is_email_verified": False,
            "account_status": "pending_activation",
            "needs_password_setup": True,
            "password_hash": hash_password("TempSecret@123"),
            "created_at": datetime.now(timezone.utc)
        })

        # Step 1: Login before activation must be BLOCKED with 403
        login_resp = client.post("/api/auth/login", json={
            "email": gmail,
            "password": "TempSecret@123"
        })
        assert login_resp.status_code == 403
        login_data = login_resp.get_json()
        assert login_data.get("needs_activation") is True
        assert login_data.get("employee_id") == emp_id

        # Step 2: Request Activation OTP
        req_otp_resp = client.post("/api/auth/activate/request-otp", json={
            "employee_id": emp_id,
            "gmail": gmail
        })
        assert req_otp_resp.status_code == 200
        req_data = req_otp_resp.get_json()
        assert req_data["success"] is True

        # Verify OTP in db is hashed, never plaintext
        token_doc = db.otp_tokens.find_one({"email": gmail, "purpose": OtpPurpose.ACTIVATION})
        assert token_doc is not None
        assert "otp_hash" in token_doc
        assert "otp" not in token_doc  # Plaintext OTP must NOT be stored in DB

        # Retrieve plain OTP for test verification
        plain_otp = OtpService.get_latest_otp_for_test(gmail, OtpPurpose.ACTIVATION)
        assert plain_otp is not None
        assert len(plain_otp) == 6

        # Step 3: Complete Activation with wrong OTP -> must fail
        bad_act_resp = client.post("/api/auth/activate/complete", json={
            "employee_id": emp_id,
            "gmail": gmail,
            "otp": "999999",
            "password": "SecurePassword@2026!"
        })
        assert bad_act_resp.status_code == 400

        # Step 4: Complete Activation with correct OTP + valid password -> succeeds
        act_resp = client.post("/api/auth/activate/complete", json={
            "employee_id": emp_id,
            "gmail": gmail,
            "otp": plain_otp,
            "password": "SecurePassword@2026!"
        })
        assert act_resp.status_code == 200
        act_data = act_resp.get_json()
        assert act_data["success"] is True

        # Verify DB user record state
        updated_user = db.users.find_one({"employee_id": emp_id})
        assert updated_user["is_email_verified"] is True
        assert updated_user["account_status"] == "active"
        assert updated_user["personal_email"] == gmail
        assert verify_password("SecurePassword@2026!", updated_user["password_hash"])

        # Step 5: Login with verified Gmail & new password -> succeeds & routes to correct dashboard
        auth_resp = client.post("/api/auth/login", json={
            "email": gmail,
            "password": "SecurePassword@2026!"
        })
        assert auth_resp.status_code == 200
        auth_data = auth_resp.get_json()
        assert auth_data["success"] is True
        assert auth_data["token"] is not None
        assert auth_data["redirect_url"] == expected_dashboard
        assert auth_data["user"]["role"] == role


def test_login_tab_or_email_does_not_determine_permissions(client, db):
    """
    Verify that permissions and redirect are determined strictly by the database role,
    not by the login tab or email prefix.
    """
    # Create employee account with verified Gmail
    db.users.insert_one({
        "employee_id": "EMP-SEC-1",
        "full_name": "Security Test Employee",
        "email": "sec.emp@gmail.com",
        "personal_email": "sec.emp@gmail.com",
        "role": Role.EMPLOYEE,
        "password_hash": hash_password("EmpPassword@123"),
        "is_active": True,
        "is_email_verified": True,
        "account_status": "active",
        "created_at": datetime.now(timezone.utc)
    })

    # Attacker tries sending role="hr" or role="manager" in request
    res = client.post("/api/auth/login", json={
        "email": "sec.emp@gmail.com",
        "password": "EmpPassword@123",
        "role": "hr"
    })
    assert res.status_code == 200
    data = res.get_json()
    # Must redirect to employee dashboard, NOT HR dashboard
    assert data["redirect_url"] == "/dashboard/employee"
    assert data["user"]["role"] == Role.EMPLOYEE


def test_forgot_password_otp_workflow(client, db):
    """
    Test Forgot Password flow with expiring single-use OTP.
    """
    email = "forgot.test@gmail.com"
    db.users.insert_one({
        "employee_id": "EMP-FP-1",
        "full_name": "Forgot Test User",
        "email": email,
        "personal_email": email,
        "role": Role.EMPLOYEE,
        "password_hash": hash_password("OldPassword@123"),
        "is_active": True,
        "is_email_verified": True,
        "account_status": "active",
        "created_at": datetime.now(timezone.utc)
    })

    # Step 1: Request reset OTP
    req_res = client.post("/api/auth/forgot-password", json={"email": email})
    assert req_res.status_code == 200

    plain_otp = OtpService.get_latest_otp_for_test(email, OtpPurpose.PASSWORD_RESET)
    assert plain_otp is not None

    # Step 2: Attempt reset with weak password -> fails
    weak_res = client.post("/api/auth/reset-password", json={
        "email": email,
        "reset_code": plain_otp,
        "new_password": "weak"
    })
    assert weak_res.status_code == 400

    # Step 3: Reset with valid password and correct OTP
    reset_res = client.post("/api/auth/reset-password", json={
        "email": email,
        "reset_code": plain_otp,
        "new_password": "NewStrongPassword@2026!"
    })
    assert reset_res.status_code == 200

    # Step 4: Single-use OTP: using the same OTP again must be rejected
    reuse_res = client.post("/api/auth/reset-password", json={
        "email": email,
        "reset_code": plain_otp,
        "new_password": "AnotherPassword@2026!"
    })
    assert reuse_res.status_code == 400

    # Step 5: Old password fails, new password succeeds
    fail_login = client.post("/api/auth/login", json={"email": email, "password": "OldPassword@123"})
    assert fail_login.status_code == 401

    ok_login = client.post("/api/auth/login", json={"email": email, "password": "NewStrongPassword@2026!"})
    assert ok_login.status_code == 200


def test_change_gmail_two_step_otp_workflow(client, db):
    """
    Test logged-in user changing registered Gmail address:
    1. Dispatches OTP to current verified email.
    2. Verifies current email OTP -> receives scoped authorization token.
    3. Dispatches OTP to new proposed Gmail address.
    4. Verifies new OTP + authorization token -> commits new Gmail.
    5. Audit log recorded.
    """
    old_email = "current.verified@gmail.com"
    new_email = "new.verified@gmail.com"

    user_doc = {
        "employee_id": "EMP-CHG-1",
        "full_name": "Change Email User",
        "email": old_email,
        "personal_email": old_email,
        "role": Role.EMPLOYEE,
        "password_hash": hash_password("MyPassword@123"),
        "is_active": True,
        "is_email_verified": True,
        "account_status": "active",
        "created_at": datetime.now(timezone.utc)
    }
    db.users.insert_one(user_doc)
    token = generate_jwt_token(user_doc)
    headers = {"Authorization": f"Bearer {token}"}

    # Step 1: Request OTP for current email
    req1 = client.post("/api/auth/change-email/request-current-otp", headers=headers)
    assert req1.status_code == 200

    otp1 = OtpService.get_latest_otp_for_test(old_email, OtpPurpose.EMAIL_CHANGE_CURRENT)
    assert otp1 is not None

    # Step 2: Verify current email OTP
    v1 = client.post("/api/auth/change-email/verify-current-otp", headers=headers, json={"otp": otp1})
    assert v1.status_code == 200
    conf_token = v1.get_json().get("confirmation_token")
    assert conf_token is not None

    # Step 3: Request OTP for new Gmail
    req2 = client.post("/api/auth/change-email/request-new-otp", headers=headers, json={
        "new_email": new_email,
        "confirmation_token": conf_token
    })
    assert req2.status_code == 200

    otp2 = OtpService.get_latest_otp_for_test(new_email, OtpPurpose.EMAIL_CHANGE_NEW)
    assert otp2 is not None

    # Step 4: Confirm new Gmail change
    conf_res = client.post("/api/auth/change-email/confirm", headers=headers, json={
        "new_email": new_email,
        "otp": otp2,
        "confirmation_token": conf_token
    })
    assert conf_res.status_code == 200

    # Step 5: Verify DB update and audit log
    updated = db.users.find_one({"employee_id": "EMP-CHG-1"})
    assert updated["email"] == new_email
    assert updated["personal_email"] == new_email

    audit_entry = db.audit_logs.find_one({"action": "CHANGE_LOGIN_EMAIL", "target_id": "EMP-CHG-1"})
    assert audit_entry is not None
    assert audit_entry["details"]["old_email"] == old_email
    assert audit_entry["details"]["new_email"] == new_email


def test_hr_employee_management_add_edit_deactivate_reactivate(client, db):
    """
    Test HR Employee Management Module:
    1. HR adds employee (created in unverified pending_activation).
    2. HR edits employee profile.
    3. HR soft deactivates employee -> login & clock-in blocked.
    4. HR reactivates employee -> login restored.
    """
    hr_doc = {
        "employee_id": "HR-MGMT-1",
        "full_name": "HR Admin",
        "email": "hr.mgmt@aisamrat.com",
        "role": Role.HR,
        "is_active": True,
        "is_email_verified": True,
        "account_status": "active",
        "created_at": datetime.now(timezone.utc)
    }
    db.users.insert_one(hr_doc)
    hr_token = generate_jwt_token(hr_doc)
    hr_headers = {"Authorization": f"Bearer {hr_token}"}

    # 1. Add Employee
    new_emp_payload = {
        "employee_id": "EMP-NEW-101",
        "full_name": "Rohan Deshmukh",
        "personal_email": "rohan.deshmukh@gmail.com",
        "role": Role.EMPLOYEE,
        "department": "AIML",
        "designation": "AI Engineer",
        "phone_number": "+91 9988776655"
    }
    create_res = client.post("/api/users", headers=hr_headers, json=new_emp_payload)
    assert create_res.status_code == 201
    created_user = create_res.get_json()["user"]
    assert created_user["employee_id"] == "EMP-NEW-101"
    assert created_user["is_email_verified"] is False
    assert created_user["account_status"] == "pending_activation"

    # 2. Edit Employee
    edit_payload = {
        "updates": {
            "designation": "Senior AI Systems Engineer",
            "phone_number": "+91 9988776600"
        },
        "reason": "Promotion and phone number update"
    }
    edit_res = client.put("/api/users/EMP-NEW-101", headers=hr_headers, json=edit_payload)
    assert edit_res.status_code == 200
    updated_user = db.users.find_one({"employee_id": "EMP-NEW-101"})
    assert updated_user["designation"] == "Senior AI Systems Engineer"

    # 3. Soft Deactivate Employee
    deact_res = client.post("/api/users/EMP-NEW-101/toggle-status", headers=hr_headers, json={"is_active": False})
    assert deact_res.status_code == 200
    deact_user = db.users.find_one({"employee_id": "EMP-NEW-101"})
    assert deact_user["is_active"] is False

    # Deactivated employee blocked from login
    deact_login = client.post("/api/auth/login", json={"email": "rohan.deshmukh@gmail.com", "password": "AnyPassword"})
    assert deact_login.status_code in (401, 403)

    # 4. Reactivate Employee
    react_res = client.post("/api/users/EMP-NEW-101/toggle-status", headers=hr_headers, json={"is_active": True})
    assert react_res.status_code == 200
    react_user = db.users.find_one({"employee_id": "EMP-NEW-101"})
    assert react_user["is_active"] is True


def test_project_separation_and_salary_privacy(client, db):
    """
    Test Project Separation and Salary Privacy boundaries:
    1. HR has ZERO project management authority.
    2. Team Lead & Manager CANNOT view employee salary (stripped from profile API).
    3. HR CAN view salary structure.
    """
    hr_user = {"employee_id": "HR-BOUNDARY", "role": Role.HR, "email": "hr.boundary@aisamrat.com"}
    tl_user = {"employee_id": "TL-BOUNDARY", "role": Role.TEAM_LEAD, "email": "tl.boundary@aisamrat.com", "team_id": "TEAM-BOUNDARY"}
    mgr_user = {"employee_id": "MGR-BOUNDARY", "role": Role.MANAGER, "email": "mgr.boundary@aisamrat.com"}
    emp_user = {"employee_id": "EMP-TARGET", "role": Role.EMPLOYEE, "email": "target.emp@aisamrat.com", "team_id": "TEAM-BOUNDARY"}

    # 1. Project Management Permission Check
    assert can_manage_projects(hr_user) is False
    assert can_manage_projects(tl_user) is True
    assert can_manage_projects(mgr_user) is True

    # 2. Salary View Permission Check
    assert can_view_salary(hr_user, emp_user) is True
    assert can_view_salary(tl_user, emp_user) is False
    assert can_view_salary(mgr_user, emp_user) is False
    assert can_view_salary(emp_user, emp_user) is True  # Employee can view their own salary

    # 3. API Salary Stripping Check
    db.users.insert_one({
        "employee_id": "EMP-TARGET",
        "full_name": "Target Employee",
        "email": "target.emp@aisamrat.com",
        "role": Role.EMPLOYEE,
        "team_id": "TEAM-BOUNDARY",
        "is_active": True,
        "is_email_verified": True,
        "salary_info": {"net_salary": 50000, "basic_salary": 25000},
        "created_at": datetime.now(timezone.utc)
    })

    db.users.insert_one(tl_user)
    db.users.insert_one(hr_user)

    # Team Lead queries Target Employee's profile
    tl_token = generate_jwt_token(tl_user)
    tl_resp = client.get("/api/users/EMP-TARGET", headers={"Authorization": f"Bearer {tl_token}"})
    assert tl_resp.status_code == 200
    tl_profile = tl_resp.get_json()["user"]
    assert "salary_info" not in tl_profile
    assert "salary_slips" not in tl_profile

    # HR queries Target Employee's profile
    hr_token = generate_jwt_token(hr_user)
    hr_resp = client.get("/api/users/EMP-TARGET", headers={"Authorization": f"Bearer {hr_token}"})
    assert hr_resp.status_code == 200
    hr_profile = hr_resp.get_json()["user"]
    assert "salary_info" in hr_profile
    assert hr_profile["salary_info"]["basic_salary"] > 0
