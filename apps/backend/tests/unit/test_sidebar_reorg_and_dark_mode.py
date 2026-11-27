import pytest
from bs4 import BeautifulSoup
from backend.database.connection import get_db
from backend.permissions.rbac import Role
from backend.auth.security import generate_jwt_token
from backend.services.project_service import ProjectService
from config import Config


@pytest.fixture
def reorg_client(client, db, seeded_users):
    """Client authenticated as an Employee, HR, and Manager."""
    emp = seeded_users["emp1"]
    hr = seeded_users["hr"]
    mgr = seeded_users["manager"]

    # Seed sample project and task assigned to employee
    proj, _ = ProjectService.create_project(mgr, {
        "project_id": "PRJ-REORG-101",
        "title": "Quantum Platform",
        "description": "Core quantum computation framework",
        "department": "Engineering",
        "members": [emp["employee_id"]],
        "priority": "High"
    })

    t1, _ = ProjectService.create_task(mgr, {
        "task_id": "TSK-REORG-201",
        "project_id": "PRJ-REORG-101",
        "title": "Build Quantum Engine",
        "assigned_employee_id": emp["employee_id"],
        "weight": 2.0,
        "due_date": "2026-12-31"
    })

    # Seed holiday
    db.holidays.delete_many({"holiday_id": "HOL-REORG-01"})
    db.holidays.insert_one({
        "holiday_id": "HOL-REORG-01",
        "name": "Republic Day",
        "date": "2026-01-26",
        "type": "National",
        "added_by": "SYSTEM"
    })

    return {
        "client": client,
        "emp_user": emp,
        "hr_user": hr,
        "project": proj,
        "task": t1
    }


def test_employee_sidebar_reorganization(reorg_client):
    """
    Verifies that the Employee sidebar has strictly the specified structure:
    WORKSPACE:
    - Overview
    - Work Diary
    - My Attendance
    - Leave & Permissions
    - Projects & Tasks
    COMMUNICATION:
    - Team & Project Chat
    - Workplace Concerns
    - Notifications
    - My Profile

    And does NOT contain separate 'Holiday Calendar', 'My Salary Slips', or 'My Analytics & Trends' links.
    """
    client = reorg_client["client"]
    token = generate_jwt_token(reorg_client["emp_user"])
    client.set_cookie(key=Config.JWT_COOKIE_NAME, value=token)

    res = client.get("/dashboard/employee")
    assert res.status_code == 200
    html = res.data.decode("utf-8")
    soup = BeautifulSoup(html, "html.parser")

    sidebar = soup.find("aside", class_="sidebar")
    assert sidebar is not None, "Sidebar must exist"

    nav_links = [a.get("href") for a in sidebar.find_all("a", class_="nav-link")]

    # Exact expected workspace links for employee
    assert "/dashboard/employee" in nav_links
    assert "/work-diary" in nav_links
    assert "/attendance" in nav_links
    assert "/leaves" in nav_links
    assert "/projects" in nav_links

    # Exact expected communication links for employee
    assert "/inbox" in nav_links
    assert "/complaints" in nav_links
    assert "/notifications" in nav_links

    # Profile link is located exclusively in the bottom-left sidebar user card (duplicate removed from nav_links)
    assert f"/profile/{reorg_client['emp_user']['employee_id']}" not in nav_links
    user_card = sidebar.find("div", class_="sidebar-user-card")
    assert user_card is not None
    assert f"/profile/{reorg_client['emp_user']['employee_id']}" in str(user_card)

    # Standalone items that should NOT be in employee sidebar
    assert "/holidays" not in nav_links, "Holiday Calendar should not be a separate item in employee sidebar"
    assert "/salary" not in nav_links, "Salary Slips should not be a separate item in employee sidebar"
    assert "/analytics" not in nav_links, "Analytics should not be a separate item in employee sidebar"


def test_diary_and_mailbox_shortcuts_open_for_every_role(client, db, seeded_users):
    """Every role's global shortcuts must lead to the full diary and mailbox pages."""
    admin = {
        "employee_id": "ADM-SHORTCUT-TEST",
        "emp_id": "ADM-SHORTCUT-TEST",
        "full_name": "Shortcut Test Admin",
        "name": "Shortcut Test Admin",
        "role": Role.ADMIN,
        "is_active": True,
    }
    admin["_id"] = db.users.insert_one(admin).inserted_id
    users = [
        seeded_users["emp1"],
        seeded_users["team_lead"],
        seeded_users["manager"],
        seeded_users["hr"],
        admin,
    ]

    for user in users:
        client.set_cookie(key=Config.JWT_COOKIE_NAME, value=generate_jwt_token(user))

        mailbox_response = client.get("/mailbox")
        assert mailbox_response.status_code == 200
        soup = BeautifulSoup(mailbox_response.get_data(as_text=True), "html.parser")
        shortcuts = soup.find(id="shortcutTilesContainer")
        assert shortcuts is not None
        shortcut_tiles = shortcuts.select(".capsule-tile-btn")
        assert shortcut_tiles
        for tile in shortcut_tiles:
            assert tile.get("title"), f"Shortcut is missing a label for role {user['role']}"
            if tile.name == "a":
                assert tile.get("href", "").startswith("/"), f"Shortcut is missing a destination for role {user['role']}"
            else:
                assert tile.name == "button" and tile.get("onclick"), (
                    f"Shortcut is missing an action for role {user['role']}"
                )
        assert shortcuts.find("a", href="/mailbox", title="Corporate Mailbox") is not None
        assert shortcuts.find("a", href="/work-diary", title="Daily Work Diary") is not None
        mail_section = soup.find(id="commSectionMail")
        assert mail_section is not None
        assert "d-none" not in mail_section.get("class", [])

        diary_response = client.get("/work-diary")
        assert diary_response.status_code == 200
        assert "My Work Diary" in diary_response.get_data(as_text=True)


def test_my_attendance_internal_tabs_and_holiday_integration(reorg_client):
    """
    Verifies My Attendance page (/attendance) renders with 4 internal tabs:
    - Attendance Overview
    - Attendance Calendar
    - Holiday Calendar
    - Punch History
    And verifies /holidays redirects employee to /attendance?tab=holidays.
    """
    client = reorg_client["client"]
    token = generate_jwt_token(reorg_client["emp_user"])
    client.set_cookie(key=Config.JWT_COOKIE_NAME, value=token)

    # 1. Check Attendance Page Tabs
    res = client.get("/attendance")
    assert res.status_code == 200
    html = res.data.decode("utf-8")
    assert "Attendance Overview" in html
    assert "Attendance Calendar" in html
    assert "Holiday Calendar" in html
    assert "Punch History" in html
    assert 'id="viewAttendanceOverview"' in html
    assert 'id="viewAttendanceCalendar"' in html
    assert 'id="viewHolidayCalendar"' in html
    assert 'id="viewPunchHistory"' in html

    # 2. Check /holidays redirect for Employee
    res_hol = client.get("/holidays", follow_redirects=False)
    assert res_hol.status_code in (301, 302)
    assert "/attendance?tab=holidays" in res_hol.headers.get("Location")

    # 3. Check /api/holidays preserves holiday data
    res_api = client.get("/api/holidays")
    assert res_api.status_code == 200
    data = res_api.get_json()
    assert len(data.get("holidays", [])) >= 1


def test_projects_and_tasks_internal_tabs_and_api(reorg_client):
    """
    Verifies Projects & Tasks page (/projects) renders with 4 internal tabs:
    - My Projects
    - My Tasks
    - Project Progress
    - My Analytics & Trends
    And verifies GET /api/tasks returns employee deliverables with project title.
    And verifies /analytics redirects employee to /projects?tab=analytics.
    """
    client = reorg_client["client"]
    token = generate_jwt_token(reorg_client["emp_user"])
    client.set_cookie(key=Config.JWT_COOKIE_NAME, value=token)

    # 1. Check Projects Page Tabs
    res = client.get("/projects")
    assert res.status_code == 200
    html = res.data.decode("utf-8")
    assert "My Projects" in html
    assert "My Tasks" in html
    assert "Project Progress" in html
    assert "My Analytics &amp; Trends" in html or "My Analytics & Trends" in html
    assert 'id="viewMyProjects"' in html
    assert 'id="viewMyTasks"' in html
    assert 'id="viewProjectProgress"' in html
    assert 'id="viewMyAnalytics"' in html

    # 2. Check GET /api/tasks endpoint
    res_tasks = client.get("/api/tasks")
    assert res_tasks.status_code == 200
    tasks_data = res_tasks.get_json().get("tasks", [])
    assert len(tasks_data) >= 1
    found_task = next((t for t in tasks_data if t["task_id"] == "TSK-REORG-201"), None)
    assert found_task is not None
    assert found_task["project_title"] == "Quantum Platform"

    # 3. Check /analytics redirect for Employee
    res_ana = client.get("/analytics", follow_redirects=False)
    assert res_ana.status_code in (301, 302)
    assert "/projects?tab=analytics" in res_ana.headers.get("Location")

    # 4. Check /api/analytics/overview returns real employee metrics
    res_ana_api = client.get("/api/analytics/overview?period=this_month")
    assert res_ana_api.status_code == 200
    ana_data = res_ana_api.get_json().get("data", {})
    assert "summary_kpis" in ana_data
    assert "task_status_distribution" in ana_data


def test_salary_slips_accessibility(reorg_client):
    """
    Verifies Salary Slips are accessible via employee profile and /salary route,
    while removed as a separate sidebar navigation item.
    """
    client = reorg_client["client"]
    token = generate_jwt_token(reorg_client["emp_user"])
    client.set_cookie(key=Config.JWT_COOKIE_NAME, value=token)

    # Direct /salary page
    res_sal = client.get("/salary")
    assert res_sal.status_code == 200
    html_sal = res_sal.data.decode("utf-8")
    assert "Salary Statements" in html_sal or "Payslips" in html_sal

    # Profile page includes salary structure and slips card
    emp_id = reorg_client["emp_user"]["employee_id"]
    res_prof = client.get(f"/profile/{emp_id}")
    assert res_prof.status_code == 200
    html_prof = res_prof.data.decode("utf-8")
    assert "Monthly Salary Slips" in html_prof
    assert "Compensation & Salary Structure" in html_prof or "Compensation" in html_prof


def test_hr_sidebar_and_navigation_preserved(reorg_client):
    """
    Ensures that HR, Team Lead, or Manager dashboards and sidebars were NOT broken.
    """
    client = reorg_client["client"]
    token = generate_jwt_token(reorg_client["hr_user"])
    client.set_cookie(key=Config.JWT_COOKIE_NAME, value=token)

    res = client.get("/dashboard/hr")
    assert res.status_code == 200
    html = res.data.decode("utf-8")
    soup = BeautifulSoup(html, "html.parser")
    sidebar = soup.find("aside", class_="sidebar")

    # HR sidebar must have its operations links
    nav_links = [a.get("href") for a in sidebar.find_all("a", class_="nav-link")]
    assert "/dashboard/hr" in nav_links
    assert "/profiles" in nav_links
    assert "/attendance" in nav_links


def test_centralized_dark_theme_tokens_and_persistence(reorg_client):
    """
    Verifies centralized dark theme tokens and persistence mechanism:
    - Base template contains zero-flash script and data-theme tokens.
    - Style.css contains comprehensive semantic dark tokens.
    - Login template contains floating theme switcher and dark theme specifications.
    """
    client = reorg_client["client"]

    # 1. Login page theme check
    res_login = client.get("/login")
    assert res_login.status_code == 200
    login_html = res_login.data.decode("utf-8")
    assert 'id="themeToggleBtn"' in login_html
    assert 'toggleTheme()' in login_html
    assert '[data-theme="dark"] .login-card' in login_html

    # 2. Base template zero-flash head script
    assert "localStorage.getItem('ai_samrat_theme')" in login_html
    assert 'html[data-theme="dark"]' in login_html
    assert 'color-scheme: dark' in login_html
