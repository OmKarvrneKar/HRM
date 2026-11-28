import pytest
import os
from config import Config
from services.test_account_service import TestAccountService
from permissions.rbac import Role
from auth.security import hash_password


def test_ensure_test_employee_dev(db):
    """Verify test employee is provisioned with exact employee role and isolated test data in development."""
    user = TestAccountService.ensure_test_employee(db)
    assert user is not None
    assert user["employee_id"] == "EMP-TEST-999"
    assert user["role"] == Role.EMPLOYEE
    assert user["is_test_account"] is True
    assert user["is_active"] is True

    # Check isolated data
    proj = db.projects.find_one({"project_id": "PRJ-TEST-001"})
    assert proj is not None
    assert "EMP-TEST-999" in proj.get("members", [])

    task = db.tasks.find_one({"task_id": "TSK-TEST-001"})
    assert task is not None
    assert task.get("assigned_employee_id") == "EMP-TEST-999"

    notif = db.notifications.find_one({"employee_id": "EMP-TEST-999"})
    assert notif is not None


def test_dev_test_employee_login_endpoint(client, db):
    """Verify dev shortcut endpoint is disabled per Section 13 instructions."""
    res = client.post("/api/auth/dev-test-employee-login")
    assert res.status_code in (403, 404, 405)


def test_dev_test_employee_rbac_isolation(client, db):
    """Verify normal employee has Employee permissions only and is blocked from HR/Manager endpoints."""
    # Seed a standard employee
    db.users.insert_one({
        "employee_id": "EMP-ISO-1",
        "full_name": "Iso Employee",
        "email": "iso.emp@aisamrat.com",
        "role": Role.EMPLOYEE,
        "password_hash": hash_password("IsoPassword@123"),
        "is_active": True,
        "is_email_verified": True,
        "account_status": "active"
    })
    login_res = client.post("/api/auth/login", json={
        "email": "iso.emp@aisamrat.com",
        "password": "IsoPassword@123",
        "role": "employee"
    })
    assert login_res.status_code == 200

    # Employee dashboard is accessible
    res_emp = client.get("/dashboard/employee")
    assert res_emp.status_code == 200

    # HR monitor endpoint is strictly 403 Forbidden
    res_hr = client.get("/api/attendance/hr-monitor")
    assert res_hr.status_code == 403

    # Manager system health endpoint is strictly 403 Forbidden
    res_mgr = client.get("/api/admin/system-health")
    assert res_mgr.status_code == 403


def test_production_safety(client, db):
    """Verify dev test login and test account are disabled in production."""
    TestAccountService.ensure_test_employee(db)

    os.environ["FLASK_ENV"] = "production"
    try:
        assert Config.is_production() is True
        assert Config.allows_test_account() is False

        # Endpoint returns 403 in production
        res = client.post("/api/auth/dev-test-employee-login")
        assert res.status_code == 403

        # Account is deactivated in production
        TestAccountService.ensure_test_employee(db)
        user = db.users.find_one({"employee_id": "EMP-TEST-999"})
        assert user["is_active"] is False
        assert user["account_status"] == "disabled_production"
    finally:
        os.environ["FLASK_ENV"] = "development"


def test_no_demo_password_bypass(client, db):
    """Verify login requires verified password and rejects demo bypass attempts."""
    db.users.insert_one({
        "employee_id": "HR-TEST-001",
        "email": "hr.test@aisamrat.com",
        "role": Role.HR,
        "password_hash": hash_password("CorrectSecret@2026!"),
        "is_active": True,
        "is_email_verified": True,
        "account_status": "active"
    })

    # Wrong password must return 401
    res_fail = client.post("/api/auth/login", json={
        "email": "hr.test@aisamrat.com",
        "password": "Hr@Samrat2026!",  # Old demo password bypass
        "role": "hr"
    })
    assert res_fail.status_code == 401

    # Correct password must succeed
    res_ok = client.post("/api/auth/login", json={
        "email": "hr.test@aisamrat.com",
        "password": "CorrectSecret@2026!",
        "role": "hr"
    })
    assert res_ok.status_code == 200


def test_activation_page_elements(client):
    """Verify activation page renders with compact layout, OTP input, and theme toggle."""
    res = client.get("/activate")
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    assert "Account Activation" in html
    assert "otpInput" in html
    assert "passwordInput" in html
    assert "confirmPasswordInput" in html
    assert "themeToggleBtn" in html
