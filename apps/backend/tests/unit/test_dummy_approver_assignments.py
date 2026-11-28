from database.seeds import seed_real_and_dummy_users
from permissions.rbac import Role
from services.attendance_service import AttendanceService
from services.leave_service import LeaveService
from services.overtime_service import OvertimeService


def test_seeded_employees_use_dummy_team_lead_and_manager(db):
    seed_real_and_dummy_users(db)

    employees = list(db.users.find({"role": Role.EMPLOYEE}))
    assert employees
    for employee in employees:
        assert employee["assigned_tl_id"] == "TL-1001"
        assert employee["manager_id"] == "MGR-1001"
        assert employee["reporting_manager_id"] == "MGR-1001"

    team_lead = db.users.find_one({"employee_id": "TL-1001"})
    assert team_lead["role"] == "tl"
    assert team_lead["reporting_manager_id"] == "MGR-1001"
    assert db.users.find_one({"employee_id": "MGR-1001"})["role"] == "manager"

    hr_user = db.users.find_one({"employee_id": "HR-1001"})
    admin_user = db.users.find_one({"employee_id": "ADMIN-1001"})
    assert hr_user["role"] == Role.HR
    assert admin_user["role"] == Role.ADMIN

    employee = next(user for user in employees if user["employee_id"] != "EMP-1001")
    status, assigned_tl_id, assigned_manager_id = LeaveService.determine_approver_and_initial_status(employee)
    assert status == "PENDING_TEAM_LEAD"
    assert assigned_tl_id == "TL-1001"
    assert assigned_manager_id == "MGR-1001"


def test_dummy_team_lead_attendance_overview_includes_assigned_employees_across_teams(db):
    seed_real_and_dummy_users(db)
    team_lead = db.users.find_one({"employee_id": "TL-1001"})
    employees = list(db.users.find({"role": Role.EMPLOYEE, "is_active": True}))

    overview = AttendanceService.get_team_attendance_overview(team_lead, "2026-11-10")

    assert {member["employee_id"] for member in overview["members"]} == {
        employee["employee_id"] for employee in employees
    }


def test_manager_overtime_view_includes_assigned_employees_outside_department(db):
    seed_real_and_dummy_users(db)
    manager = db.users.find_one({"employee_id": "MGR-1001"})
    employee = db.users.find_one({"role": Role.EMPLOYEE, "department": {"$ne": manager["department"]}})
    db.overtime_requests.insert_one({
        "request_id": "OT-CROSS-DEPT",
        "employee_id": employee["employee_id"],
        "employee_name": employee["full_name"],
        "department": employee["department"],
        "status": "Pending"
    })

    requests = OvertimeService.get_overtime_requests(actor=manager)

    assert any(request["request_id"] == "OT-CROSS-DEPT" for request in requests)
