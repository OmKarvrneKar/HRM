import pytest
from permissions.rbac import Role


def test_employee_cannot_access_hr_endpoints(client, tokens):
    """Employee must be forbidden from accessing HR operational endpoints."""
    headers = {"Authorization": f"Bearer {tokens['emp1']}"}
    res = client.get("/api/attendance/hr-monitor", headers=headers)
    assert res.status_code == 403


def test_hr_cannot_access_project_endpoints(client, tokens):
    """HR role must be strictly forbidden from project management functionality."""
    headers = {"Authorization": f"Bearer {tokens['hr']}"}
    # API endpoints
    res_api = client.get("/api/projects", headers=headers)
    assert res_api.status_code == 403

    # Project detail
    res_detail = client.get("/api/projects/PRJ-101", headers=headers)
    assert res_detail.status_code == 403

    # Frontend project pages
    res_page = client.get("/projects", headers=headers)
    assert res_page.status_code == 403


def test_manager_cannot_access_private_salary_or_complaints(client, tokens, seeded_users):
    """Manager must be strictly forbidden from accessing private employee salary or confidential HR complaints."""
    headers = {"Authorization": f"Bearer {tokens['manager']}"}
    emp_id = seeded_users["emp1"]["employee_id"]

    # Salary slip PDF export / download
    res_slip = client.get(f"/api/salary/slips/{emp_id}/2026-10", headers=headers)
    assert res_slip.status_code == 403

    # Confidential employee complaints
    res_complaints = client.get("/api/complaints", headers=headers)
    assert res_complaints.status_code == 403


def test_team_lead_cannot_access_private_salary_or_complaints(client, tokens, seeded_users):
    """Team Lead must be strictly forbidden from accessing employee salary or confidential HR complaints."""
    headers = {"Authorization": f"Bearer {tokens['team_lead']}"}
    emp_id = seeded_users["emp1"]["employee_id"]

    res_slip = client.get(f"/api/salary/slips/{emp_id}/2026-10", headers=headers)
    assert res_slip.status_code == 403

    res_complaints = client.get("/api/complaints", headers=headers)
    assert res_complaints.status_code == 403


def test_employee_cannot_view_other_employee_attendance(client, tokens, seeded_users):
    """IDOR protection: Employee 1 cannot access Employee 2's individual attendance records."""
    headers = {"Authorization": f"Bearer {tokens['emp1']}"}
    emp2_id = seeded_users["emp2"]["employee_id"]
    res = client.get(f"/api/attendance/user/{emp2_id}", headers=headers)
    assert res.status_code == 403


def test_inactive_account_cannot_authenticate(client):
    """Deactivated user accounts must be rejected with 403 Forbidden."""
    res = client.post("/api/auth/login", json={
        "email": "inactive.test@hrm.local",
        "password": "Inactive@123"
    })
    assert res.status_code == 403


def test_invalid_role_provisioning_rejected(client, tokens):
    """Creation of accounts with deprecated roles (admin, trainer, hr_manager) must be rejected."""
    headers = {"Authorization": f"Bearer {tokens['hr']}"}
    for old_role in ["admin", "trainer", "hr_manager", "organization"]:
        payload = {
            "full_name": f"Invalid {old_role}",
            "email": f"invalid_{old_role}@hrm.local",
            "role": old_role,
            "password": "Password@123",
            "department": "Engineering"
        }
        res = client.post("/api/users", json=payload, headers=headers)
        assert res.status_code in (400, 403)
