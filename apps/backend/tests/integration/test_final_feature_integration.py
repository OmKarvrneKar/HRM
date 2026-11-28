import pytest
from datetime import datetime, timezone
from permissions.rbac import Role
from auth.security import hash_password, generate_jwt_token
from services.chat_service import ChatService
from services.notification_service import NotificationService
from services.skill_service import SkillService
from services.audit_service import AuditService


@pytest.fixture
def test_setup(db):
    """Seed users for all testing roles."""
    users = {
        "hr_manager": {
            "employee_id": "MGR-001",
            "full_name": "Admin Director",
            "email": "mgr@aisamrat.test",
            "password_hash": hash_password("Mgr@Secret2026!"),
            "role": Role.MANAGER,
            "department": "Management",
            "is_active": True,
            "status": "active",
            "created_at": datetime.now(timezone.utc)
        },
        "hr": {
            "employee_id": "HR-001",
            "full_name": "Priya Sharma",
            "email": "hr@aisamrat.test",
            "password_hash": hash_password("Hr@Secret2026!"),
            "role": Role.HR,
            "department": "Human Resources",
            "is_active": True,
            "status": "active",
            "created_at": datetime.now(timezone.utc)
        },
        "team_lead": {
            "employee_id": "TL-001",
            "full_name": "Kavita Verma",
            "email": "lead@aisamrat.test",
            "password_hash": hash_password("Lead@Secret2026!"),
            "role": Role.TEAM_LEAD,
            "department": "Engineering",
            "is_active": True,
            "status": "active",
            "created_at": datetime.now(timezone.utc)
        },
        "trainer": {
            "employee_id": "TR-001",
            "full_name": "Rajesh Kumar",
            "email": "trainer@aisamrat.test",
            "password_hash": hash_password("Trainer@Secret2026!"),
            "role": Role.TEAM_LEAD,
            "department": "Training",
            "is_active": True,
            "status": "active",
            "created_at": datetime.now(timezone.utc)
        },
        "emp1": {
            "employee_id": "EMP-001",
            "full_name": "Rahul Verma",
            "email": "emp1@aisamrat.test",
            "password_hash": hash_password("Emp@Secret2026!"),
            "role": Role.EMPLOYEE,
            "department": "Engineering",
            "is_active": True,
            "status": "active",
            "created_at": datetime.now(timezone.utc)
        },
        "emp2": {
            "employee_id": "EMP-002",
            "full_name": "Sneha Roy",
            "email": "emp2@aisamrat.test",
            "password_hash": hash_password("Emp@Secret2026!"),
            "role": Role.EMPLOYEE,
            "department": "Engineering",
            "is_active": True,
            "status": "active",
            "created_at": datetime.now(timezone.utc)
        },
        "emp3": {
            "employee_id": "EMP-003",
            "full_name": "Amit Patel",
            "email": "emp3@aisamrat.test",
            "password_hash": hash_password("Emp@Secret2026!"),
            "role": Role.EMPLOYEE,
            "department": "Design",
            "is_active": True,
            "status": "active",
            "created_at": datetime.now(timezone.utc)
        }
    }
    for u in users.values():
        res = db.users.insert_one(u)
        u["_id"] = res.inserted_id
    return users


def auth_headers(user):
    token = generate_jwt_token(user)
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }


def test_unified_login_role_routing(client, test_setup):
    """Section 2: Team Lead & Trainer sign in via Employee selector, HR & Org Admin via HR selector."""
    # 1. Team lead signs in through Employee selector
    res = client.post("/api/auth/login", json={
        "email": "lead@aisamrat.test",
        "password": "Lead@Secret2026!",
        "role": "employee"
    })
    assert res.status_code == 200
    assert res.get_json()["redirect_url"] == "/dashboard/team-lead"

    # 2. Trainer signs in through Employee selector
    res = client.post("/api/auth/login", json={
        "email": "trainer@aisamrat.test",
        "password": "Trainer@Secret2026!",
        "role": "employee"
    })
    assert res.status_code == 200
    assert res.get_json()["redirect_url"] in ("/dashboard/trainer", "/dashboard/team-lead")

    # 3. Regular employee signs in through Employee selector
    res = client.post("/api/auth/login", json={
        "email": "emp1@aisamrat.test",
        "password": "Emp@Secret2026!",
        "role": "employee"
    })
    assert res.status_code == 200
    assert res.get_json()["redirect_url"] == "/dashboard/employee"

    # 4. HR signs in through HR selector
    res = client.post("/api/auth/login", json={
        "email": "hr@aisamrat.test",
        "password": "Hr@Secret2026!",
        "role": "hr"
    })
    assert res.status_code == 200
    assert res.get_json()["redirect_url"] == "/dashboard/hr"

    # 5. Manager signs in through Employee selector
    res = client.post("/api/auth/login", json={
        "email": "mgr@aisamrat.test",
        "password": "Mgr@Secret2026!",
        "role": "employee"
    })
    assert res.status_code == 200
    assert res.get_json()["redirect_url"] == "/dashboard/manager"

    # 5b. Manager attempting HR selector is rejected (403)
    res_mgr_hr = client.post("/api/auth/login", json={
        "email": "mgr@aisamrat.test",
        "password": "Mgr@Secret2026!",
        "role": "hr"
    })
    assert res_mgr_hr.status_code == 403

    # 6. Privilege escalation: Employee attempting to select HR role
    res = client.post("/api/auth/login", json={
        "email": "emp1@aisamrat.test",
        "password": "Emp@Secret2026!",
        "role": "hr"
    })
    assert res.status_code == 403


def test_employee_offboarding_and_session_invalidation(client, db, test_setup):
    """Section 3: HR offboards employee, session invalidated, check-in blocked, project memberships updated."""
    hr = test_setup["hr"]
    emp = test_setup["emp1"]
    lead = test_setup["team_lead"]

    # Pre-condition: Create an active project with emp1 as member
    proj_res = client.post("/api/projects", headers=auth_headers(lead), json={
        "name": "Apollo Mission",
        "description": "High priority project",
        "members": ["EMP-001", "EMP-002"],
        "assigned_trainer_id": "TR-001"
    })
    assert proj_res.status_code in (200, 201)
    proj_id = proj_res.get_json()["project"]["project_id"]

    # Generate active token for EMP-001
    emp_token = generate_jwt_token(emp)
    emp_headers = {"Authorization": f"Bearer {emp_token}", "Content-Type": "application/json"}

    # Verify token currently works
    test_res = client.get(f"/api/users/{emp['employee_id']}", headers=emp_headers)
    assert test_res.status_code == 200

    # HR offboards employee
    offboard_res = client.post(f"/api/users/{emp['employee_id']}/offboard", headers=auth_headers(hr), json={
        "reason": "Contract Completion",
        "last_working_day": "2026-10-31",
        "effective_date": "2026-10-31",
        "notes": "All company assets returned"
    })
    assert offboard_res.status_code == 200
    assert offboard_res.get_json()["success"] is True

    # 1. Existing token must now be invalidated/rejected
    revoked_res = client.get(f"/api/users/{emp['employee_id']}", headers=emp_headers)
    assert revoked_res.status_code in (401, 403)

    # 2. Login must be blocked
    login_res = client.post("/api/auth/login", json={
        "email": emp["email"],
        "password": "Emp@Secret2026!",
        "role": "employee"
    })
    assert login_res.status_code in (401, 403)

    # 3. Attendance check-in must be blocked
    checkin_res = client.post("/api/attendance/check-in", headers=emp_headers, json={
        "employee_id": emp["employee_id"]
    })
    assert checkin_res.status_code in (401, 403)

    # 4. Project membership must be updated: detached from members to former_members
    updated_proj = db.projects.find_one({"project_id": proj_id})
    assert "EMP-001" not in updated_proj.get("members", [])
    assert "EMP-001" in updated_proj.get("former_members", [])

    # 5. Offboarding historical record must be preserved
    record = db.offboardings.find_one({"employee_id": emp["employee_id"]})
    assert record is not None
    assert record["reason"] == "Contract Completion"
    assert record["processed_by_id"] == hr["employee_id"]


def test_automatic_project_chat_and_rbac(client, db, test_setup):
    """Section 5: Auto project group chat creation, member access, non-member rejection, member sync."""
    lead = test_setup["team_lead"]
    emp1 = test_setup["emp1"]
    emp2 = test_setup["emp2"]
    emp3 = test_setup["emp3"]

    # 1. Team lead creates a project with members emp1 and emp2
    create_res = client.post("/api/projects", headers=auth_headers(lead), json={
        "name": "Quantum Shield Project",
        "description": "Defensive security architecture",
        "members": ["EMP-001", "EMP-002"],
        "assigned_trainer_id": "TR-001"
    })
    assert create_res.status_code in (200, 201)
    proj_data = create_res.get_json()["project"]
    proj_id = proj_data["project_id"]
    conv_id = proj_data.get("conversation_id")
    assert conv_id == f"PRJ-CHAT-{proj_id}"

    # 2. Verify auto-created conversation in database
    chat = db.conversations.find_one({"conversation_id": conv_id})
    assert chat is not None
    assert chat["type"] in ("project", "PROJECT_GROUP")
    assert chat["title"] == "Quantum Shield Project"
    # Participants must include lead, emp1, emp2, and assigned trainer
    assert set(chat["participants"]).issuperset({"TL-001", "EMP-001", "EMP-002", "TR-001"})

    # 3. Authorized member (emp1) can read conversation and send message
    emp1_headers = auth_headers(emp1)
    get_conv_res = client.get(f"/api/conversations/{conv_id}", headers=emp1_headers)
    assert get_conv_res.status_code == 200

    msg_res = client.post(f"/api/conversations/{conv_id}/messages", headers=emp1_headers, json={
        "content": "Hello team, kickoff meeting at 10 AM!"
    })
    assert msg_res.status_code in (200, 201)

    # 4. Unrelated employee (emp3) cannot read or send messages (403 Forbidden)
    emp3_headers = auth_headers(emp3)
    unauthorized_res = client.get(f"/api/conversations/{conv_id}", headers=emp3_headers)
    assert unauthorized_res.status_code == 403

    unauth_send_res = client.post(f"/api/conversations/{conv_id}/messages", headers=emp3_headers, json={
        "content": "I should not be able to send this"
    })
    assert unauth_send_res.status_code == 403

    # 5. Add emp3 to project members -> access to chat is immediately granted
    update_res = client.put(f"/api/projects/{proj_id}/members", headers=auth_headers(lead), json={
        "members": ["EMP-001", "EMP-002", "EMP-003"]
    })
    assert update_res.status_code == 200

    # emp3 can now access the chat
    emp3_access_res = client.get(f"/api/conversations/{conv_id}", headers=emp3_headers)
    assert emp3_access_res.status_code == 200

    # 6. Remove emp1 from project members -> access is immediately revoked
    update_remove_res = client.put(f"/api/projects/{proj_id}/members", headers=auth_headers(lead), json={
        "members": ["EMP-002", "EMP-003"]
    })
    assert update_remove_res.status_code == 200

    emp1_revoked_res = client.get(f"/api/conversations/{conv_id}", headers=emp1_headers)
    assert emp1_revoked_res.status_code == 403

    # Historical messages in the conversation are preserved
    msgs_after = client.get(f"/api/conversations/{conv_id}/messages", headers=emp3_headers).get_json()["messages"]
    assert any("kickoff meeting" in m["content"] for m in msgs_after)


def test_notification_destination_urls():
    """Section 8: Explicit destination URL resolution for every actionable notification category."""
    # Leave approval for HR
    url_leave = NotificationService.resolve_destination_url("LEAVE", "REQ-101", "hr")
    assert url_leave == "/leaves/approvals?request_id=REQ-101"

    # Leave update for Employee
    url_leave_emp = NotificationService.resolve_destination_url("LEAVE", "REQ-101", "employee")
    assert url_leave_emp == "/leaves?request_id=REQ-101"

    # Project chat message
    url_chat = NotificationService.resolve_destination_url("PROJECT_CHAT", "PRJ-999", "employee")
    assert url_chat == "/inbox?project_id=PRJ-999"

    # Direct message
    url_dm = NotificationService.resolve_destination_url("DIRECT_MESSAGE", "CONV-DIRECT-123", "employee")
    assert url_dm == "/inbox?conversation_id=CONV-DIRECT-123"

    # Project assignment
    url_proj = NotificationService.resolve_destination_url("PROJECT", "PRJ-888", "employee")
    assert url_proj == "/projects/PRJ-888"

    # Complaint update
    url_comp = NotificationService.resolve_destination_url("COMPLAINT", "CASE-456", "employee")
    assert url_comp == "/complaints/CASE-456"

    # Skill assessment feedback
    url_skill = NotificationService.resolve_destination_url("SKILL", "SKL-789", "employee")
    assert url_skill == "/skills"

    # Attendance alert
    url_att = NotificationService.resolve_destination_url("ATTENDANCE", "ATT-123", "employee")
    assert url_att == "/attendance"


def test_standardized_skill_matrix_levels():
    """Section 10: Verify the 6 standardized proficiency levels."""
    expected_levels = [
        "No Experience",
        "Beginner",
        "Basic",
        "Competent",
        "Advanced",
        "Expert"
    ]
    assert SkillService.PROFICIENCY_LEVELS == expected_levels
    for lvl in expected_levels:
        assert lvl in SkillService.PROFICIENCY_SCORES
        assert isinstance(SkillService.PROFICIENCY_SCORES[lvl], (int, float))


def test_audit_logs_filtering_and_scope(client, test_setup):
    """Section 7: Activity and audit logs with multi-field filtering."""
    mgr = test_setup["hr_manager"]
    hr = test_setup["hr"]

    # Log actions
    AuditService.log_action(
        actor=mgr,
        action="UPDATE_ORGANIZATION_POLICY",
        target_type="system",
        target_id="SYS-POLICY-01",
        details={"policy": "Remote work guidelines"}
    )
    AuditService.log_action(
        actor=hr,
        action="OFFBOARD_EMPLOYEE",
        target_type="offboarding",
        target_id="EMP-TEST-OFF",
        details={"reason": "Retirement"}
    )

    # 1. Org admin (HR Manager) can see all logs
    res_mgr = client.get("/api/audit-logs", headers=auth_headers(mgr))
    assert res_mgr.status_code == 200
    logs_all = res_mgr.get_json()["audit_logs"]
    actions = [l["action"] for l in logs_all]
    assert "UPDATE_ORGANIZATION_POLICY" in actions
    assert "OFFBOARD_EMPLOYEE" in actions

    # 2. Filter by target_type
    res_filtered = client.get("/api/audit-logs?target_type=offboarding", headers=auth_headers(mgr))
    assert res_filtered.status_code == 200
    offboard_logs = res_filtered.get_json()["audit_logs"]
    assert all(l["target_type"] == "offboarding" for l in offboard_logs)

    # 3. Filter by action
    res_action = client.get("/api/audit-logs?action=OFFBOARD_EMPLOYEE", headers=auth_headers(mgr))
    assert res_action.status_code == 200
    action_logs = res_action.get_json()["audit_logs"]
    assert all(l["action"] == "OFFBOARD_EMPLOYEE" for l in action_logs)
