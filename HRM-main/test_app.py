import pytest
import re
from flask import session, get_flashed_messages
from werkzeug.security import check_password_hash

from app import initialize_users, create_app
from config import TestConfig
from backend.database.connection import DatabaseManager
from backend.database.indexes import setup_indexes
from backend.auth.security import generate_jwt_token


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture(scope="session")
def app():
    app_instance = create_app(config_class=TestConfig, start_scheduler=False)
    yield app_instance
    db_cleanup = DatabaseManager.get_db(db_name=TestConfig.DATABASE_NAME)
    try:
        db_cleanup.client.drop_database(TestConfig.DATABASE_NAME)
    except Exception:
        pass


@pytest.fixture(scope="session")
def client(app):
    return app.test_client()


@pytest.fixture(scope="function")
def db(app):
    database = DatabaseManager.get_db(db_name=TestConfig.DATABASE_NAME)
    database.users.delete_many({})
    setup_indexes(database)
    DatabaseManager.set_db(database)
    return database


# ============================================================================
# 1. DATABASE & SEEDING INTEGRITY
# ============================================================================

def test_database_seeding_integrity(db):
    """
    Verify that initialize_users() successfully loads the complete 100-person
    enterprise roster (including the 5 standard test accounts and 34 real interns)
    without crashing.
    """
    users = initialize_users(db)
    assert users is not None

    total_count = db.users.count_documents({})
    assert total_count == 100, f"Expected 100 users, found {total_count}"

    # 1. Verify 5 standard test accounts exist with their roles
    expected_dummies = [
        ("EMP-1001", "Dummy Employee", "employee", "employee@aisamrat.com"),
        ("TL-1001", "Dummy Team Lead", "tl", "tl@aisamrat.com"),
        ("MGR-1001", "Dummy Manager", "manager", "manager@aisamrat.com"),
        ("HR-1001", "Dummy HR Admin", "hr", "hr@aisamrat.com"),
        ("ADMIN-1001", "Dummy System Admin", "admin", "admin@aisamrat.com"),
    ]

    for emp_id, name, role, email in expected_dummies:
        user = db.users.find_one({"emp_id": emp_id})
        assert user is not None, f"Dummy account {emp_id} should exist in database"
        assert user.get("name") == name, f"Name mismatch for {emp_id}"
        assert user.get("role") == role, f"Role mismatch for {emp_id}"
        assert user.get("email") == email, f"Email mismatch for {emp_id}"
        assert user.get("is_active") is True
        assert user.get("is_email_verified") is True

    # 2. Verify all 34 real intern records exist (AS-1001 to AS-1034)
    for s_no in range(1, 35):
        intern_id = f"AS-{1000 + s_no}"
        intern = db.users.find_one({"emp_id": intern_id})
        assert intern is not None, f"Intern record {intern_id} should exist in database"
        assert intern.get("role") == "employee", f"Intern {intern_id} should have role 'employee'"
        assert bool(intern.get("name")), f"Intern {intern_id} should have a non-empty name"
        assert bool(intern.get("email")), f"Intern {intern_id} should have a non-empty email"
        assert bool(intern.get("contact")), f"Intern {intern_id} should have a contact number"
        assert bool(intern.get("dob")), f"Intern {intern_id} should have a date of birth"

    # 3. Verify enterprise squads and facility meeting rooms
    teams_count = db.teams.count_documents({})
    assert teams_count >= 10, f"Expected at least 10 teams, found {teams_count}"

    rooms_count = db.facility_rooms.count_documents({})
    assert rooms_count >= 3, f"Expected 3 meeting rooms, found {rooms_count}"
    assert db.facility_rooms.find_one({"room_id": "ROOM-MANTHAN"}) is not None
    assert db.facility_rooms.find_one({"room_id": "ROOM-GURUKOOL"}) is not None


def test_user_record_keys(db):
    """
    Verify that every user record contains required keys:
    ('emp_id', 'name', 'role', 'email', 'password_hash').
    """
    initialize_users(db)
    all_users = list(db.users.find())
    assert len(all_users) == 100

    required_keys = ["emp_id", "name", "role", "email", "password_hash"]

    for user in all_users:
        emp_id = user.get("emp_id")
        for key in required_keys:
            assert key in user, f"Missing required key '{key}' in user record {emp_id}"
            assert user[key] is not None and str(user[key]).strip() != "", (
                f"Key '{key}' in user record {emp_id} must have a non-empty value"
            )


# ============================================================================
# 2. AUTHENTICATION & SECURITY
# ============================================================================

def test_password_hashing_and_verification(db):
    """
    Test password hashing and verification (check_password_hash) using 'password123'
    for both dummy accounts and real interns.
    """
    initialize_users(db)

    # Test 5 dummy accounts
    dummy_ids = ["EMP-1001", "TL-1001", "MGR-1001", "HR-1001", "ADMIN-1001"]
    for eid in dummy_ids:
        user = db.users.find_one({"emp_id": eid})
        assert user is not None
        pw_hash = user.get("password_hash")
        assert pw_hash is not None and len(pw_hash) > 20
        # Positive verification
        assert check_password_hash(pw_hash, "password123") is True, f"Failed for {eid}"
        # Negative verification
        assert check_password_hash(pw_hash, "wrongpassword") is False
        assert check_password_hash(pw_hash, "") is False

    # Test sample real interns across the full range
    sample_intern_ids = ["AS-1001", "AS-1010", "AS-1020", "AS-1030", "AS-1034"]
    for iid in sample_intern_ids:
        user = db.users.find_one({"emp_id": iid})
        assert user is not None
        pw_hash = user.get("password_hash")
        assert pw_hash is not None
        assert check_password_hash(pw_hash, "password123") is True, f"Failed for intern {iid}"
        assert check_password_hash(pw_hash, "invalid_pw") is False


def test_login_valid_credentials_employee_and_intern(client, db):
    """
    Test login route (/login) with valid credentials (EMP-1001, AS-1001)
    and ensure successful session creation.
    """
    initialize_users(db)

    # 1. Test Employee login (EMP-1001)
    res = client.post("/login", json={
        "emp_id": "EMP-1001",
        "password": "password123"
    })
    assert res.status_code == 200
    data = res.get_json()
    assert data["success"] is True
    assert data["role"] == "employee"
    assert data["redirect_url"] == "/dashboard/employee"

    with client.session_transaction() as sess:
        assert sess.get("emp_id") == "EMP-1001"
        assert sess.get("role") == "employee"
        assert sess.get("user_id") is not None

    # Clear session for next test
    client.get("/logout")

    # 2. Test Real Intern login (AS-1001)
    res_intern = client.post("/login", json={
        "emp_id": "AS-1001",
        "password": "password123"
    })
    assert res_intern.status_code == 200
    data_intern = res_intern.get_json()
    assert data_intern["success"] is True
    assert data_intern["role"] == "employee"
    assert data_intern["redirect_url"] == "/dashboard/employee"

    with client.session_transaction() as sess:
        assert sess.get("emp_id") == "AS-1001"
        assert sess.get("role") == "employee"
        assert sess.get("user_id") is not None


def test_invalid_login_handling_and_flash_message(client, db):
    """
    Test invalid login handling and flash message triggering.
    """
    initialize_users(db)

    # 1. JSON Request with wrong password
    res_json = client.post("/login", json={
        "emp_id": "EMP-1001",
        "password": "wrongpassword"
    })
    assert res_json.status_code == 401
    data_json = res_json.get_json()
    assert data_json.get("success") is False or "error" in data_json

    # 2. Form submission with wrong password (triggers flash message and renders template)
    res_form = client.post("/login", data={
        "emp_id": "EMP-1001",
        "password": "incorrect_password"
    }, follow_redirects=True)

    # Status code is 200 (re-renders login page)
    assert res_form.status_code == 200
    html = res_form.get_data(as_text=True)
    # Verifies error notification is rendered
    assert "Invalid Employee ID or password" in html or "Authentication failed" in html or "danger" in html

    # 3. Form submission with nonexistent Employee ID
    res_nonexistent = client.post("/login", data={
        "emp_id": "NONEXISTENT-9999",
        "password": "password123"
    }, follow_redirects=True)
    assert res_nonexistent.status_code == 200
    html_nonexistent = res_nonexistent.get_data(as_text=True)
    assert "Invalid Employee ID or password" in html_nonexistent or "Authentication failed" in html_nonexistent or "danger" in html_nonexistent


# ============================================================================
# 3. ROLE-BASED ROUTING
# ============================================================================

@pytest.mark.parametrize("emp_id,expected_role,expected_redirect", [
    ("ADMIN-1001", "admin", "/admin/dashboard"),
    ("HR-1001", "hr", "/dashboard/hr"),
    ("MGR-1001", "manager", "/dashboard/manager"),
    ("TL-1001", "tl", "/dashboard/team-lead"),
    ("EMP-1001", "employee", "/dashboard/employee"),
    ("AS-1001", "employee", "/dashboard/employee"),
])
def test_role_based_routing(client, db, emp_id, expected_role, expected_redirect):
    """
    Verify that logging in with ADMIN-1001 correctly routes to the admin dashboard,
    HR-1001 to HR, MGR-1001 to manager, TL-1001 to TL, and EMP-1001 / AS-1001 to the employee dashboard.
    """
    initialize_users(db)

    # Test via JSON API
    res = client.post("/login", json={
        "emp_id": emp_id,
        "password": "password123"
    })
    assert res.status_code == 200
    data = res.get_json()
    assert data["success"] is True
    assert data["role"] == expected_role
    assert data["redirect_url"] == expected_redirect

    # Test via Form submission (redirect 302 with Location header)
    res_form = client.post("/login", data={
        "emp_id": emp_id,
        "password": "password123"
    })
    assert res_form.status_code == 302
    assert res_form.headers["Location"].endswith(expected_redirect)


# ============================================================================
# 4. SESSION MANAGEMENT & LOGOUT
# ============================================================================

def test_session_management_and_logout(client, db):
    """
    Test the /logout route to ensure session.clear() successfully wipes user credentials
    and redirects back to the login page.
    """
    initialize_users(db)

    # 1. Log in to establish authenticated session
    res = client.post("/login", json={
        "emp_id": "EMP-1001",
        "password": "password123"
    })
    assert res.status_code == 200

    # Verify session variables exist
    with client.session_transaction() as sess:
        assert sess.get("emp_id") == "EMP-1001"
        assert sess.get("role") == "employee"
        assert sess.get("user_id") is not None

    # 2. Call /logout
    res_logout = client.get("/logout")
    assert res_logout.status_code == 302
    assert res_logout.headers["Location"].endswith("/login")

    # 3. Verify session is completely wiped
    with client.session_transaction() as sess:
        assert sess.get("emp_id") is None
        assert sess.get("role") is None
        assert sess.get("user_id") is None
        assert len(sess) == 0

    # 4. Verify accessing protected dashboard redirects to login
    res_protected = client.get("/dashboard/employee")
    assert res_protected.status_code in (302, 401)


# ============================================================================
# 5. FRONTEND TEMPLATE ACCESSIBILITY
# ============================================================================

def test_frontend_template_accessibility_login(client, db):
    """
    Test unauthenticated /login route ensures status code 200
    (template renders correctly without 500 internal server errors).
    """
    res = client.get("/login")
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    assert "Sign in" in html or "AI Samrat HRMS" in html or "emp_id" in html.lower()


@pytest.mark.parametrize("emp_id,dashboard_url", [
    ("EMP-1001", "/dashboard/employee"),
    ("TL-1001", "/dashboard/team-lead"),
    ("MGR-1001", "/dashboard/manager"),
    ("HR-1001", "/dashboard/hr"),
    ("ADMIN-1001", "/admin/dashboard"),
    ("ADMIN-1001", "/dashboard/admin"),
])
def test_frontend_template_accessibility_dashboards(client, db, emp_id, dashboard_url):
    """
    Test all main dashboard endpoints using Flask's test client to ensure status code 200
    (templates render correctly without 500 internal server errors).
    """
    initialize_users(db)

    # Fetch user from database
    user = db.users.find_one({"emp_id": emp_id})
    assert user is not None

    # Authenticate client with JWT cookie and session
    token = generate_jwt_token(user)
    client.set_cookie("hrm_jwt_token", token)
    with client.session_transaction() as sess:
        sess["user_id"] = str(user["_id"])
        sess["emp_id"] = emp_id
        sess["role"] = user["role"]

    res = client.get(dashboard_url)
    assert res.status_code == 200, (
        f"Failed rendering {dashboard_url} for {emp_id}: status {res.status_code}\n{res.get_data(as_text=True)[:500]}"
    )
    html = res.get_data(as_text=True)
    assert "<!DOCTYPE html>" in html or "<html" in html
    assert "500 Internal Server Error" not in html


def test_admin_dashboard_access_control(client, db):
    """
    Verify that accessing /admin/dashboard without admin role redirects to /login with flash message,
    and accessing with admin role (ADMIN-1001) successfully renders admin_dashboard.html.
    """
    initialize_users(db)

    # 1. Unauthenticated access -> redirects to /login
    client.get("/logout")
    res_unauth = client.get("/admin/dashboard")
    assert res_unauth.status_code == 302
    assert res_unauth.headers["Location"].endswith("/login")

    # 2. Authenticated as Employee -> unauthorized redirect to /login
    with client.session_transaction() as sess:
        sess["user_id"] = "test-emp"
        sess["role"] = "employee"
    res_emp = client.get("/admin/dashboard")
    assert res_emp.status_code == 302
    assert res_emp.headers["Location"].endswith("/login")

    # 3. Authenticated as Admin -> renders admin_dashboard.html (200 OK)
    with client.session_transaction() as sess:
        sess["user_id"] = "test-admin"
        sess["role"] = "admin"
    res_admin = client.get("/admin/dashboard")
    assert res_admin.status_code == 200
    html = res_admin.get_data(as_text=True)
    assert "AI Samrat HRMS" in html

    # 4. Case-insensitive role check ('Admin')
    with client.session_transaction() as sess:
        sess["role"] = "Admin"
    res_case = client.get("/admin/dashboard")
    assert res_case.status_code == 200


# ============================================================================
# 6. SQLALCHEMY or_ AUTHENTICATION & MULTI-IDENTIFIER LOOKUP
# ============================================================================

def test_sqlalchemy_or_query_lookup(db):
    """
    Verify that SQLAlchemy or_ correctly queries users by either their email,
    employee ID (emp_id / employee_id), or username across all enterprise roles.
    """
    from sqlalchemy import or_
    from backend.models.user import User, sync_users_from_db

    initialize_users(db)
    sync_users_from_db(db)

    test_identifiers = [
        ("AS-1001", "employee"),
        ("AS-1015", "employee"),
        ("AS-1034", "employee"),
        ("EMP-1001", "employee"),
        ("TL-1001", "tl"),
        ("MGR-1001", "manager"),
        ("HR-1001", "hr"),
        ("ADMIN-1001", "admin"),
        ("employee@aisamrat.com", "employee"),
        ("admin@aisamrat.com", "admin"),
        ("manager@aisamrat.com", "manager"),
        ("tl@aisamrat.com", "tl"),
        ("hr@aisamrat.com", "hr"),
    ]

    for identifier, expected_role in test_identifiers:
        user = User.query.filter(
            or_(
                User.email == identifier.lower(),
                User.emp_id == identifier.upper(),
                User.employee_id == identifier.upper(),
                User.username == identifier.lower()
            )
        ).first()

        assert user is not None, f"SQLAlchemy or_ lookup failed for identifier: {identifier}"
        assert user.role.lower() == expected_role.lower(), (
            f"Expected role {expected_role} for {identifier}, got {user.role}"
        )
        assert user.check_password("password123"), f"Password verification failed for {identifier}"


def test_platform_wide_id_and_email_form_login(client, db):
    """
    Verify platform-wide form login using either unique IDs or email addresses
    for Interns, Employees, TLs, Managers, HR, and Admins.
    """
    initialize_users(db)

    test_logins = [
        ("AS-1001", "/dashboard/employee"),
        ("AS-1034", "/dashboard/employee"),
        ("EMP-1001", "/dashboard/employee"),
        ("TL-1001", "/dashboard/team-lead"),
        ("MGR-1001", "/dashboard/manager"),
        ("HR-1001", "/dashboard/hr"),
        ("ADMIN-1001", "/admin/dashboard"),
        ("employee@aisamrat.com", "/dashboard/employee"),
        ("admin@aisamrat.com", "/admin/dashboard"),
    ]

    for cred_id, expected_dest in test_logins:
        client.get("/logout")
        res = client.post("/login", data={
            "username": cred_id,
            "password": "password123"
        }, follow_redirects=False)

        assert res.status_code == 302, f"Expected 302 redirect for {cred_id}, got {res.status_code}"
        assert expected_dest in res.headers["Location"], (
            f"Expected redirect to {expected_dest} for {cred_id}, got {res.headers['Location']}"
        )

