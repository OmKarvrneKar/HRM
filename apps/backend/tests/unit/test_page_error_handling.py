def set_user_session(client, employee_id, role):
    with client.session_transaction() as session:
        session["user_id"] = employee_id
        session["emp_id"] = employee_id
        session["employee_id"] = employee_id
        session["role"] = role
        session["name"] = employee_id


def test_missing_profile_renders_404_page(client, seeded_users):
    user = seeded_users["emp1"]
    set_user_session(client, user["employee_id"], "employee")

    response = client.get("/profile/DOES-NOT-EXIST")

    assert response.status_code == 404
    assert b"Page not found" in response.data
    assert b"Return to My Dashboard" in response.data


def test_admin_audit_center_link_uses_existing_page_route(client):
    set_user_session(client, "ADMIN-TEST", "admin")

    response = client.get("/dashboard/admin")

    assert response.status_code == 200
    assert b'href="/audit-logs"' in response.data
    assert b'href="/audit/logs"' not in response.data


def test_team_lead_assets_page_only_shows_authorized_actions(client):
    set_user_session(client, "TL-TEST", "team_lead")

    response = client.get("/assets")

    assert response.status_code == 200
    assert b"Allocate Seat &amp; Locker" in response.data
    assert b"Allocate Hardware / Tool" not in response.data
    assert b"Global Enterprise Inventory" not in response.data
