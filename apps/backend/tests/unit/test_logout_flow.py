import pytest
from flask import session, url_for
from database.seeds import seed_default_users
from config import Config


def test_logout_route_get_clears_session_and_redirects(client, db):
    """Verify GET /logout clears session, clears cookie, and redirects to /login."""
    seed_default_users(db)

    # 1. Log in
    login_resp = client.post("/login", data={
        "emp_id": "EMP-1001",
        "password": "password123"
    })
    assert login_resp.status_code == 302

    # Check session is active
    with client.session_transaction() as sess:
        assert sess.get("user_id") is not None
        assert sess.get("role") == "employee"

    # 2. Call GET /logout
    logout_resp = client.get("/logout")
    assert logout_resp.status_code == 302
    assert logout_resp.headers["Location"].endswith("/login")

    # 3. Check session is completely cleared
    with client.session_transaction() as sess:
        assert sess.get("user_id") is None
        assert sess.get("role") is None
        assert sess.get("emp_id") is None
        assert len(sess) == 0

    # 4. Check cookie is deleted/expired
    set_cookie = logout_resp.headers.get("Set-Cookie", "")
    assert Config.JWT_COOKIE_NAME in set_cookie
    assert "Expires=Thu, 01 Jan 1970" in set_cookie or "Max-Age=0" in set_cookie or f"{Config.JWT_COOKIE_NAME}=;" in set_cookie


def test_logout_route_post_clears_session_and_redirects(client, db):
    """Verify POST /logout clears session, clears cookie, and redirects to /login."""
    seed_default_users(db)

    # 1. Log in
    login_resp = client.post("/login", data={
        "emp_id": "HR-1001",
        "password": "password123"
    })
    assert login_resp.status_code == 302

    with client.session_transaction() as sess:
        assert sess.get("role") == "hr"

    # 2. Call POST /logout
    logout_resp = client.post("/logout")
    assert logout_resp.status_code == 302
    assert logout_resp.headers["Location"].endswith("/login")

    # 3. Check session is completely cleared
    with client.session_transaction() as sess:
        assert sess.get("user_id") is None
        assert sess.get("role") is None

    # 4. Verify accessing protected dashboard now redirects back to login
    dash_resp = client.get("/dashboard/hr")
    assert dash_resp.status_code == 302
    assert "/login" in dash_resp.headers["Location"]


def test_url_for_login_and_logout_resolution(client):
    """Verify url_for('login') and url_for('logout') resolve cleanly."""
    with client.application.test_request_context():
        login_url = url_for("login")
        logout_url = url_for("logout")
        assert login_url == "/login"
        assert logout_url == "/logout"


def test_frontend_templates_point_to_logout_route(client, db):
    """Verify rendered dashboard templates include the /logout route link."""
    seed_default_users(db)

    client.post("/login", data={
        "emp_id": "EMP-1001",
        "password": "password123"
    })
    resp = client.get("/dashboard/employee")
    assert resp.status_code == 200
    html = resp.data.decode("utf-8")

    # Ensure link pointing to /logout exists in HTML
    assert 'href="/logout"' in html
    assert 'Sign Out' in html

