import pytest
from permissions.rbac import Role
from services.analytics_service import AnalyticsService
from auth.security import generate_jwt_token


def test_analytics_service_all_roles(db, seeded_users):
    """Verifies that AnalyticsService generates valid data for all 4 canonical roles."""
    emp = seeded_users["emp1"]
    lead = seeded_users["team_lead"]
    mgr = seeded_users["manager"]
    hr = seeded_users["hr"]

    # 1. Employee Analytics
    emp_res = AnalyticsService.get_analytics_for_user(emp, period="this_month")
    assert emp_res["scope"] == "personal_workplace"
    assert "summary_kpis" in emp_res["data"]
    assert "present_days" in emp_res["data"]["summary_kpis"]
    assert "attendance_breakdown" in emp_res["data"]
    assert "task_status_distribution" in emp_res["data"]

    # 2. Team Lead Analytics
    lead_res = AnalyticsService.get_analytics_for_user(lead, period="this_month")
    assert lead_res["scope"] == "team_engineering"
    assert "team_members_count" in lead_res["data"]["summary_kpis"]
    assert "project_status_distribution" in lead_res["data"]
    assert "member_workload" in lead_res["data"]

    # 3. Manager Analytics
    mgr_res = AnalyticsService.get_analytics_for_user(mgr, period="this_month")
    assert mgr_res["scope"] == "operations_oversight"
    assert "total_projects" in mgr_res["data"]["summary_kpis"]
    assert "attendance_trend" in mgr_res["data"]
    assert "department_headcount" in mgr_res["data"]

    # 4. HR Analytics (Must NOT contain project data)
    hr_res = AnalyticsService.get_analytics_for_user(hr, period="this_month")
    assert hr_res["scope"] == "hr_operations"
    assert "total_active_employees" in hr_res["data"]["summary_kpis"]
    assert "department_distribution" in hr_res["data"]
    assert "hiring_trends" in hr_res["data"]
    assert "project_status_distribution" not in hr_res["data"]
    assert "total_projects" not in hr_res["data"]["summary_kpis"]


def test_analytics_csv_export(db, seeded_users):
    """Verifies CSV export generates valid formatted CSV streams."""
    hr = seeded_users["hr"]
    content, filename = AnalyticsService.export_analytics_csv(hr, period="this_month")
    assert "AI SAMRAT HRMS" in content
    assert "KEY PERFORMANCE INDICATORS" in content
    assert filename.startswith("ai_samrat_analytics_hr_this_month_")
    assert filename.endswith(".csv")


def test_api_analytics_endpoints(client, seeded_users):
    """Verifies /api/analytics/overview and /api/analytics/export endpoints."""
    # Authenticate as Employee
    emp = seeded_users["emp1"]
    token = generate_jwt_token(emp)
    headers = {"Authorization": f"Bearer {token}"}

    res = client.get("/api/analytics/overview?period=this_month", headers=headers)
    assert res.status_code == 200
    json_data = res.get_json()
    assert json_data["scope"] == "personal_workplace"

    export_res = client.get("/api/analytics/export?period=this_month", headers=headers)
    assert export_res.status_code == 200
    assert "text/csv" in export_res.content_type
    assert "attachment" in export_res.headers.get("Content-Disposition", "")


def test_api_health_endpoint(client):
    """Verifies operational health check endpoint returns 200 without authentication."""
    res = client.get("/api/health")
    assert res.status_code == 200
    json_data = res.get_json()
    assert json_data["status"] == "UP"
    assert json_data["database"]["connected"] is True
    assert "roles" in json_data
    assert len(json_data["roles"]) == 4


def test_login_tab_and_role_routing(client, seeded_users):
    """
    Verifies that:
    - Employee tab authenticates Employee, Team Lead, and Manager accounts.
    - HR tab authenticates ONLY HR accounts.
    - HR trying Employee tab is rejected with 403.
    - Employee/Team Lead/Manager trying HR tab is rejected with 403.
    """
    emp = seeded_users["emp1"]
    lead = seeded_users["team_lead"]
    mgr = seeded_users["manager"]
    hr = seeded_users["hr"]

    # 1. Employee on Employee tab -> Success
    res_emp = client.post("/api/auth/login", json={
        "email": emp["email"],
        "password": "Emp1@Pass123",
        "role": "employee"
    })
    assert res_emp.status_code == 200
    assert res_emp.get_json()["redirect_url"] == "/dashboard/employee"

    # 2. Team Lead on Employee tab -> Success
    res_lead = client.post("/api/auth/login", json={
        "email": lead["email"],
        "password": "Lead@123",
        "role": "employee"
    })
    assert res_lead.status_code == 200
    assert res_lead.get_json()["redirect_url"] == "/dashboard/team-lead"

    # 3. Manager on Employee tab -> Success
    res_mgr = client.post("/api/auth/login", json={
        "email": mgr["email"],
        "password": "Manager@123",
        "role": "employee"
    })
    assert res_mgr.status_code == 200
    assert res_mgr.get_json()["redirect_url"] == "/dashboard/manager"

    # 4. HR on HR tab -> Success
    res_hr = client.post("/api/auth/login", json={
        "email": hr["email"],
        "password": "Hr@Pass123",
        "role": "hr"
    })
    assert res_hr.status_code == 200
    assert res_hr.get_json()["redirect_url"] == "/dashboard/hr"

    # 5. HR attempting Employee tab -> Authenticated & correctly routed to /dashboard/hr per DB role
    res_hr_on_emp = client.post("/api/auth/login", json={
        "email": hr["email"],
        "password": "Hr@Pass123",
        "role": "employee"
    })
    assert res_hr_on_emp.status_code == 200
    assert res_hr_on_emp.get_json()["redirect_url"] == "/dashboard/hr"

    # 6. Employee attempting HR tab -> Authenticated & correctly routed to /dashboard/employee per DB role
    res_emp_on_hr = client.post("/api/auth/login", json={
        "email": emp["email"],
        "password": "Emp1@Pass123",
        "role": "hr"
    })
    assert res_emp_on_hr.status_code == 200
    assert res_emp_on_hr.get_json()["redirect_url"] == "/dashboard/employee"

    # 7. Team Lead attempting HR tab -> Authenticated & correctly routed to /dashboard/team-lead per DB role
    res_lead_on_hr = client.post("/api/auth/login", json={
        "email": lead["email"],
        "password": "Lead@123",
        "role": "hr"
    })
    assert res_lead_on_hr.status_code == 200
    assert res_lead_on_hr.get_json()["redirect_url"] == "/dashboard/team-lead"

    # 8. Manager attempting HR tab -> Authenticated & correctly routed to /dashboard/manager per DB role
    res_mgr_on_hr = client.post("/api/auth/login", json={
        "email": mgr["email"],
        "password": "Manager@123",
        "role": "hr"
    })
    assert res_mgr_on_hr.status_code == 200
    assert res_mgr_on_hr.get_json()["redirect_url"] == "/dashboard/manager"
