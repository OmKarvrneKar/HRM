import pytest
from services.captcha_service import CaptchaService
from auth.security import hash_password
from permissions.rbac import Role


@pytest.fixture
def setup_users(db):
    """Seed test users into test db."""
    db.users.update_one(
        {"employee_id": "EMP-1005"},
        {
            "$set": {
                "full_name": "Deepak S J",
                "email": "deepaksj.in@gmail.com",
                "personal_email": "deepaksj.in@gmail.com",
                "password_hash": hash_password("EmpPassword@123"),
                "is_email_verified": True,
                "account_status": "active",
                "is_active": True,
                "role": Role.EMPLOYEE,
                "assigned_tl_id": "LEAD-1001",
                "assigned_manager_id": "MGR-1001"
            }
        },
        upsert=True
    )
    db.users.update_one(
        {"employee_id": "HR-1001"},
        {
            "$set": {
                "full_name": "Ramya HR",
                "email": "ramya.hr@aisamrat.com",
                "personal_email": "ramya.hr@aisamrat.com",
                "password_hash": hash_password("HrPassword@123"),
                "is_email_verified": True,
                "account_status": "active",
                "is_active": True,
                "role": Role.HR
            }
        },
        upsert=True
    )


def test_login_with_employee_id(client, db, setup_users):
    """Test login using Employee ID as primary credential."""
    c_id, _ = CaptchaService.generate_captcha()
    sol = CaptchaService.get_solution_for_testing(c_id)

    # Successful login with lowercase solution (case-insensitivity test)
    resp = client.post("/api/auth/login", json={
        "employee_id": "EMP-1005",
        "password": "EmpPassword@123",
        "role": "employee",
        "captcha_id": c_id,
        "captcha_answer": sol.lower()
    })
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert data["user"]["employee_id"] == "EMP-1005"
    assert data["redirect_url"] == "/dashboard/employee"


def test_login_with_hr_id(client, db, setup_users):
    """Test login using HR Employee ID for HR Portal."""
    c_id, _ = CaptchaService.generate_captcha()
    sol = CaptchaService.get_solution_for_testing(c_id)

    resp = client.post("/api/auth/login", json={
        "employee_id": "HR-1001",
        "password": "HrPassword@123",
        "role": "hr",
        "captcha_id": c_id,
        "captcha_answer": sol.upper()
    })
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert data["user"]["employee_id"] == "HR-1001"
    assert data["redirect_url"] == "/dashboard/hr"


def test_login_automatic_backend_role_routing(client, db, setup_users):
    """Test automatic backend role routing redirects employee to their authentic dashboard regardless of role payload."""
    c_id, _ = CaptchaService.generate_captcha()
    sol = CaptchaService.get_solution_for_testing(c_id)

    resp = client.post("/api/auth/login", json={
        "employee_id": "EMP-1005",
        "password": "EmpPassword@123",
        "captcha_id": c_id,
        "captcha_answer": sol
    })
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["redirect_url"] == "/dashboard/employee"
    assert data["user"]["role"] == "employee"


def test_login_invalid_password(client, db, setup_users):
    """Test rejection with invalid password."""
    c_id, _ = CaptchaService.generate_captcha()
    sol = CaptchaService.get_solution_for_testing(c_id)

    resp = client.post("/api/auth/login", json={
        "employee_id": "EMP-1005",
        "password": "WrongPassword999!",
        "role": "employee",
        "captcha_id": c_id,
        "captcha_answer": sol
    })
    assert resp.status_code == 401
    data = resp.get_json()
    assert "Invalid Employee ID or password" in data["error"]


def test_login_invalid_captcha(client, db, setup_users):
    """Test rejection with incorrect captcha."""
    c_id, _ = CaptchaService.generate_captcha()

    resp = client.post("/api/auth/login", json={
        "employee_id": "EMP-1005",
        "password": "EmpPassword@123",
        "role": "employee",
        "captcha_id": c_id,
        "captcha_answer": "WRONG"
    })
    assert resp.status_code == 400
    data = resp.get_json()
    assert "captcha" in data["error"].lower()


def test_forgot_password_by_employee_id(client, db, setup_users):
    """Test forgot password endpoint accepts Employee ID."""
    resp = client.post("/api/auth/forgot-password", json={
        "identifier": "EMP-1005"
    })
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
