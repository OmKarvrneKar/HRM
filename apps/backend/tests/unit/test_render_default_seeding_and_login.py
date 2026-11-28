import pytest
import re
from database.seeds import seed_default_users, DEFAULT_USERS_TO_SEED
from auth.security import verify_password


def test_seed_default_users_function(db):
    """Verify seed_default_users creates all 4 required default accounts."""
    # Ensure test db starts without default users
    for spec in DEFAULT_USERS_TO_SEED:
        db.users.delete_many({"$or": [{"emp_id": spec["emp_id"]}, {"employee_id": spec["emp_id"]}]})

    count = seed_default_users(db)
    assert count == 4

    # Verify each user in database
    for spec in DEFAULT_USERS_TO_SEED:
        emp_id = spec["emp_id"]
        user = db.users.find_one({"$or": [{"emp_id": emp_id}, {"employee_id": emp_id}]})
        assert user is not None, f"Seeded user {emp_id} should exist in db"
        assert user.get("role") == spec["role"], f"Role mismatch for {emp_id}"
        assert user.get("is_active") is True
        assert user.get("is_email_verified") is True
        assert verify_password("password123", user.get("password_hash")), f"Password verification failed for {emp_id}"

    # Re-running seed_default_users should be idempotent (0 new users added)
    recount = seed_default_users(db)
    assert recount == 0


def test_login_via_emp_id_json_employee(client, db):
    """Test login using emp_id via JSON for Employee."""
    seed_default_users(db)

    res = client.post("/login", json={
        "emp_id": "EMP-1001",
        "password": "password123"
    })
    assert res.status_code == 200
    data = res.get_json()
    assert data["success"] is True
    assert data["redirect_url"] == "/dashboard/employee"
    assert data["role"] == "employee"

    with client.session_transaction() as sess:
        assert sess.get("role") == "employee"
        assert sess.get("user_id") is not None


def test_login_via_emp_id_form_tl(client, db):
    """Test login using emp_id via Form data for Team Lead (role tl)."""
    seed_default_users(db)

    res = client.post("/login", data={
        "emp_id": "TL-1001",
        "password": "password123"
    })
    # Form post redirects to dashboard
    assert res.status_code == 302
    assert res.headers["Location"].endswith("/dashboard/team-lead")

    with client.session_transaction() as sess:
        assert sess.get("role") == "tl"
        assert sess.get("user_id") is not None


def test_login_via_emp_id_form_manager(client, db):
    """Test login using emp_id via Form data for Manager (role manager)."""
    seed_default_users(db)

    res = client.post("/login", data={
        "emp_id": "MGR-1001",
        "password": "password123"
    })
    assert res.status_code == 302
    assert res.headers["Location"].endswith("/dashboard/manager")

    with client.session_transaction() as sess:
        assert sess.get("role") == "manager"
        assert sess.get("user_id") is not None


def test_login_via_emp_id_form_hr(client, db):
    """Test login using emp_id via Form data for HR Admin (role hr)."""
    seed_default_users(db)

    res = client.post("/login", data={
        "emp_id": "HR-1001",
        "password": "password123"
    })
    assert res.status_code == 302
    assert res.headers["Location"].endswith("/dashboard/hr")

    with client.session_transaction() as sess:
        assert sess.get("role") == "hr"
        assert sess.get("user_id") is not None


def test_login_invalid_password_rejection(client, db):
    """Test login rejects invalid password."""
    seed_default_users(db)

    res = client.post("/login", json={
        "emp_id": "EMP-1001",
        "password": "wrongpassword"
    })
    assert res.status_code == 401
    data = res.get_json()
    assert data["success"] is False or "error" in data


def test_login_case_insensitivity(client, db):
    """Test login accepts case-insensitive emp_id (e.g. emp-1001 or EMP-1001)."""
    seed_default_users(db)

    res = client.post("/login", json={
        "emp_id": "emp-1001",
        "password": "password123"
    })
    assert res.status_code == 200
    data = res.get_json()
    assert data["success"] is True
    assert data["redirect_url"] == "/dashboard/employee"

