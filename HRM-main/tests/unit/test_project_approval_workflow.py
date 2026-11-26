import pytest
from datetime import datetime, timezone
from backend.services.project_service import ProjectService
from backend.services.chat_service import ChatService
from backend.permissions.rbac import Role
from backend.auth.security import generate_jwt_token


def test_team_lead_creates_project_proposal_pending_approval(db, seeded_users):
    """
    Requirement 1 & 2:
    Team Lead creates a project proposal:
      - Status must be PENDING_APPROVAL.
      - is_approved must be False.
      - Selected members must NOT receive active project assignments yet (members is empty).
      - No group chat is created.
      - Not marked as started.
      - Notification sent to authorized Manager.
    """
    tl = seeded_users["team_lead"]
    mgr = seeded_users["manager"]
    emp1 = seeded_users["emp1"]
    emp2 = seeded_users["emp2"]

    payload = {
        "name": "Cloud Native Orchestrator",
        "description": "High performance orchestration pipeline",
        "objectives": "Deploy microservices with 99.99% uptime",
        "deliverables": "Helm charts, CI runner, monitoring alerts",
        "start_date": "2026-11-10",
        "expected_completion_date": "2026-12-30",
        "priority": "Critical",
        "manager_employee_id": mgr["employee_id"],
        "selected_members": [emp1["employee_id"], emp2["employee_id"]],
        "responsibilities": "emp1 handles infrastructure, emp2 handles tests",
        "required_skills": "Kubernetes, Docker, Go, Python",
        "notes": "Requires access to staging cloud cluster"
    }

    project, err = ProjectService.create_project(tl, payload)
    assert err is None
    assert project is not None

    project_id = project["project_id"]
    assert project["status"] == "PENDING_APPROVAL"
    assert project["is_approved"] is False
    assert project["members"] == []  # Not activated yet
    assert project["selected_members"] == [emp1["employee_id"], emp2["employee_id"]]
    assert project["assigned_manager"] == mgr["employee_id"]
    assert project["objectives"] == "Deploy microservices with 99.99% uptime"
    assert project["deliverables"] == "Helm charts, CI runner, monitoring alerts"
    assert project["required_skills"] == ["Kubernetes", "Docker", "Go", "Python"]

    # Verify NO group chat created
    conv = db.conversations.find_one({"project_id": project_id})
    assert conv is None

    # Verify notification sent to Manager
    notif = db.notifications.find_one({"recipient_id": mgr["employee_id"], "category": "PROJECT"})
    assert notif is not None
    assert project_id in notif["message"]


def test_pending_projects_are_isolated_from_employees(db, seeded_users, client):
    """
    Requirement 1 & 2:
    Pending projects are not active. Selected employees must not receive active assignments,
    cannot see the project in user projects, and are forbidden from project endpoints.
    """
    tl = seeded_users["team_lead"]
    mgr = seeded_users["manager"]
    emp1 = seeded_users["emp1"]

    payload = {
        "title": "Secret R&D Initiative",
        "objectives": "Research quantum algorithms",
        "deliverables": "Whitepaper and simulator",
        "manager_employee_id": mgr["employee_id"],
        "selected_members": [emp1["employee_id"]]
    }
    project, err = ProjectService.create_project(tl, payload)
    assert err is None
    project_id = project["project_id"]

    # In user projects service
    emp_projects = ProjectService.get_user_projects(emp1)
    matching = [p for p in emp_projects if p["project_id"] == project_id]
    assert len(matching) == 0

    # In API endpoint GET /api/projects/<id>
    token = generate_jwt_token(emp1)
    res = client.get(
        f"/api/projects/{project_id}",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert res.status_code == 403
    data = res.get_json()
    assert "Access Denied" in data.get("error", "")


def test_no_group_chat_before_approval(db, seeded_users):
    """
    Requirement 3:
    Group chat must not be created when project is in DRAFT, PENDING_APPROVAL,
    CHANGES_REQUESTED, or REJECTED.
    """
    tl = seeded_users["team_lead"]
    mgr = seeded_users["manager"]
    emp1 = seeded_users["emp1"]

    payload = {
        "title": "Data Warehouse Migration",
        "objectives": "Migrate MySQL to PostgreSQL",
        "deliverables": "ETL scripts and verification benchmarks",
        "manager_employee_id": mgr["employee_id"],
        "selected_members": [emp1["employee_id"]],
        "is_draft": True
    }
    draft_proj, _ = ProjectService.create_project(tl, payload)
    assert draft_proj["status"] == "DRAFT"

    # Verify chat service safeguard
    chat_result = ChatService.ensure_project_chat(draft_proj)
    assert chat_result is None
    assert db.conversations.find_one({"project_id": draft_proj["project_id"]}) is None


def test_manager_pending_approvals_queue_and_review(db, seeded_users):
    """
    Requirement 2:
    Manager pending approvals queue displays submitted proposals with
    designations, skills, and workload telemetry.
    """
    tl = seeded_users["team_lead"]
    mgr = seeded_users["manager"]
    emp1 = seeded_users["emp1"]

    payload = {
        "title": "Observability Stack 2.0",
        "objectives": "Prometheus & Grafana deployment",
        "deliverables": "Dashboard templates and metric collectors",
        "manager_employee_id": mgr["employee_id"],
        "selected_members": [emp1["employee_id"]],
        "priority": "High"
    }
    proj, _ = ProjectService.create_project(tl, payload)

    approvals = ProjectService.get_pending_approvals(mgr)
    assert approvals["total_pending"] >= 1
    found = next((p for p in approvals["proposals"] if p["project_id"] == proj["project_id"]), None)
    assert found is not None
    assert found["title"] == "Observability Stack 2.0"
    assert len(found["selected_member_details"]) == 1

    member_detail = found["selected_member_details"][0]
    assert member_detail["employee_id"] == emp1["employee_id"]
    assert "availability" in member_detail
    assert "active_projects_count" in member_detail


def test_manager_requests_changes_and_tl_resubmits(db, seeded_users):
    """
    Requirement 2 & 5:
    Manager requests changes with required comments.
    Proposal status becomes CHANGES_REQUESTED.
    TL can edit and resubmit proposal back to PENDING_APPROVAL with revision history preserved.
    """
    tl = seeded_users["team_lead"]
    mgr = seeded_users["manager"]
    emp1 = seeded_users["emp1"]

    payload = {
        "title": "Mobile App V2",
        "objectives": "Flutter rewrite",
        "deliverables": "iOS and Android builds",
        "manager_employee_id": mgr["employee_id"],
        "selected_members": [emp1["employee_id"]]
    }
    proj, _ = ProjectService.create_project(tl, payload)
    project_id = proj["project_id"]

    # Attempt requesting changes without comments -> fails
    _, err_no_comments = ProjectService.request_changes_project(mgr, project_id, "")
    assert err_no_comments is not None

    # Valid change request
    updated, err = ProjectService.request_changes_project(
        mgr, project_id, "Please include end-to-end integration test deliverables."
    )
    assert err is None
    assert updated["status"] == "CHANGES_REQUESTED"
    assert updated["change_request_comments"] == "Please include end-to-end integration test deliverables."
    assert len(updated["approval_history"]) >= 2
    assert updated["approval_history"][-1]["action"] == "CHANGES_REQUESTED"

    # Verify notification sent to TL
    notif = db.notifications.find_one({"recipient_id": tl["employee_id"], "title": {"$regex": "Changes Requested"}})
    assert notif is not None

    # TL edits and resubmits
    resubmitted, resub_err = ProjectService.update_project_proposal(
        tl, project_id,
        {
            "deliverables": "iOS and Android builds + Cypress integration test suite",
            "notes": "Added integration tests per manager request"
        },
        submit_for_approval=True
    )
    assert resub_err is None
    assert resubmitted["status"] == "PENDING_APPROVAL"
    assert resubmitted["deliverables"] == "iOS and Android builds + Cypress integration test suite"
    assert len(resubmitted["approval_history"]) >= 3
    assert resubmitted["approval_history"][-1]["action"] in ("RESUBMITTED", "RESUBMITTED_FOR_APPROVAL")


def test_manager_rejects_project_proposal(db, seeded_users):
    """
    Requirement 2:
    Manager rejects proposal:
      - Requires rejection reason.
      - Status becomes REJECTED.
      - Proposal and history kept for reference.
      - No group chat is created.
      - Project never becomes active.
    """
    tl = seeded_users["team_lead"]
    mgr = seeded_users["manager"]
    emp1 = seeded_users["emp1"]

    payload = {
        "title": "Blockchain Ledger Experiment",
        "objectives": "Explore distributed ledger",
        "deliverables": "POC smart contracts",
        "manager_employee_id": mgr["employee_id"],
        "selected_members": [emp1["employee_id"]]
    }
    proj, _ = ProjectService.create_project(tl, payload)
    project_id = proj["project_id"]

    # Reject without reason -> fails
    _, err = ProjectService.reject_project(mgr, project_id, "   ")
    assert err is not None

    # Valid rejection
    rejected, err = ProjectService.reject_project(mgr, project_id, "Strategic priority shift: focus on Core AI.")
    assert err is None
    assert rejected["status"] == "REJECTED"
    assert rejected["is_approved"] is False
    assert rejected["rejection_reason"] == "Strategic priority shift: focus on Core AI."

    # Verify TL notified
    notif = db.notifications.find_one({"recipient_id": tl["employee_id"], "title": {"$regex": "Proposal Rejected"}})
    assert notif is not None

    # Verify no group chat
    assert db.conversations.find_one({"project_id": project_id}) is None


def test_manager_approves_project_and_creates_exactly_one_group_chat(db, seeded_users):
    """
    Requirement 2 & 3:
    Manager approves project proposal:
      - Status becomes ACTIVE.
      - is_approved becomes True.
      - Records approval date, manager ID, and approval history.
      - Creates exactly one private group chat associated with project.
      - Includes TL, Manager as supervisor, and approved members.
      - Chat named using project name.
      - Chat creation is idempotent (no duplicate chats).
    """
    tl = seeded_users["team_lead"]
    mgr = seeded_users["manager"]
    emp1 = seeded_users["emp1"]
    emp2 = seeded_users["emp2"]

    payload = {
        "title": "Quantum ML Pipeline",
        "objectives": "Quantum optimization algorithms",
        "deliverables": "Production inference gateway",
        "manager_employee_id": mgr["employee_id"],
        "selected_members": [emp1["employee_id"], emp2["employee_id"]],
        "priority": "High"
    }
    proj, _ = ProjectService.create_project(tl, payload)
    project_id = proj["project_id"]

    approved, err = ProjectService.approve_project(mgr, project_id, review_notes="Approved for full Q4 rollout.")
    assert err is None
    assert approved["status"] == "ACTIVE"
    assert approved["is_approved"] is True
    assert approved["approved_by"] == mgr["employee_id"]
    assert approved["members"] == [emp1["employee_id"], emp2["employee_id"]]
    assert len(approved["approval_history"]) >= 2
    assert approved["approval_history"][-1]["action"] == "APPROVED"

    # Exactly one group chat created
    chats = list(db.conversations.find({"project_id": project_id}))
    assert len(chats) == 1
    chat = chats[0]
    assert chat["is_group"] is True
    assert chat["name"] == "Quantum ML Pipeline"
    assert tl["employee_id"] in chat["participants"]
    assert mgr["employee_id"] in chat["participants"]
    assert emp1["employee_id"] in chat["participants"]
    assert emp2["employee_id"] in chat["participants"]

    # Idempotency check: repeated chat creation call does not duplicate chat
    ChatService.ensure_project_chat(approved)
    chats_after = list(db.conversations.find({"project_id": project_id}))
    assert len(chats_after) == 1


def test_only_approved_members_gain_access(db, seeded_users, client):
    """
    Requirement 5 & 7:
    Approved project is accessible to approved assigned members.
    Non-assigned employees are strictly forbidden.
    """
    tl = seeded_users["team_lead"]
    mgr = seeded_users["manager"]
    emp1 = seeded_users["emp1"]
    emp2 = seeded_users["emp2"]

    payload = {
        "title": "Internal Security Audit",
        "objectives": "Audit IAM roles",
        "deliverables": "Audit log review",
        "manager_employee_id": mgr["employee_id"],
        "selected_members": [emp1["employee_id"]]  # emp2 is NOT selected
    }
    proj, _ = ProjectService.create_project(tl, payload)
    project_id = proj["project_id"]
    ProjectService.approve_project(mgr, project_id)

    # emp1 (assigned) has access
    t1 = generate_jwt_token(emp1)
    res1 = client.get(f"/api/projects/{project_id}", headers={"Authorization": f"Bearer {t1}"})
    assert res1.status_code == 200

    # emp2 (unassigned) gets 403
    t2 = generate_jwt_token(emp2)
    res2 = client.get(f"/api/projects/{project_id}", headers={"Authorization": f"Bearer {t2}"})
    assert res2.status_code == 403


def test_tasks_cannot_be_assigned_before_approval(db, seeded_users):
    """
    Requirement 5:
    Tasks can ONLY be assigned after approval.
    Attempts to create tasks on unapproved projects are rejected.
    """
    tl = seeded_users["team_lead"]
    mgr = seeded_users["manager"]
    emp1 = seeded_users["emp1"]

    payload = {
        "title": "Database Sharding",
        "objectives": "Shard user table",
        "deliverables": "Sharding cluster setup",
        "manager_employee_id": mgr["employee_id"],
        "selected_members": [emp1["employee_id"]]
    }
    proj, _ = ProjectService.create_project(tl, payload)
    project_id = proj["project_id"]

    # Attempt task creation on PENDING_APPROVAL project
    task, err = ProjectService.create_task(tl, {
        "project_id": project_id,
        "title": "Setup sharded cluster nodes",
        "assigned_to": emp1["employee_id"]
    })
    assert err is not None
    assert "must be approved and active" in err

    # Approve project
    ProjectService.approve_project(mgr, project_id)

    # Task creation now succeeds
    task, err = ProjectService.create_task(tl, {
        "project_id": project_id,
        "title": "Setup sharded cluster nodes",
        "assigned_to": emp1["employee_id"]
    })
    assert err is None
    assert task is not None
    assert task["project_id"] == project_id


def test_membership_change_requests_require_manager_approval(db, seeded_users):
    """
    Requirement 4:
    Post-approval membership changes:
      - TL submits membership change request to Manager.
      - Direct membership change without approval is blocked.
      - Manager approves: project.members updated and chat participants synchronized.
      - Removed members lose chat access, added members gain chat access.
    """
    tl = seeded_users["team_lead"]
    mgr = seeded_users["manager"]
    emp1 = seeded_users["emp1"]
    emp2 = seeded_users["emp2"]

    payload = {
        "title": "Enterprise Gateway V3",
        "objectives": "Fast API gateway",
        "deliverables": "Gateway service",
        "manager_employee_id": mgr["employee_id"],
        "selected_members": [emp1["employee_id"]]
    }
    proj, _ = ProjectService.create_project(tl, payload)
    project_id = proj["project_id"]
    ProjectService.approve_project(mgr, project_id)

    # Verify initial chat has emp1 but not emp2
    conv = db.conversations.find_one({"project_id": project_id})
    assert emp1["employee_id"] in conv["participants"]
    assert emp2["employee_id"] not in conv["participants"]

    # TL submits membership change request: add emp2, remove emp1
    req, err = ProjectService.submit_membership_change_request(
        tl, project_id,
        add_members=[emp2["employee_id"]],
        remove_members=[emp1["employee_id"]],
        reason="Skill specialization shift"
    )
    assert err is None
    assert req["status"] == "PENDING"
    req_id = req["request_id"]

    # Check project.members has NOT changed yet
    p_before = db.projects.find_one({"project_id": project_id})
    assert p_before["members"] == [emp1["employee_id"]]

    # Manager approves membership change
    res, review_err = ProjectService.review_membership_change_request(
        mgr, project_id, req_id, action="approve", review_notes="Approved staff rotation"
    )
    assert review_err is None
    assert res["status"] == "APPROVED"

    # Project members updated
    p_after = db.projects.find_one({"project_id": project_id})
    assert emp2["employee_id"] in p_after["members"]
    assert emp1["employee_id"] not in p_after["members"]

    # Group chat participants synchronized
    conv_after = db.conversations.find_one({"project_id": project_id})
    assert emp2["employee_id"] in conv_after["participants"]
    assert emp1["employee_id"] not in conv_after["participants"]

    # Notifications sent to both
    n_add = db.notifications.find_one({"recipient_id": emp2["employee_id"], "title": {"$regex": "Added to Project"}})
    assert n_add is not None
    n_rem = db.notifications.find_one({"recipient_id": emp1["employee_id"], "title": {"$regex": "Removed from Project"}})
    assert n_rem is not None


def test_project_status_lifecycle_transitions(db, seeded_users):
    """
    Requirement 5:
    Valid lifecycle transitions:
      DRAFT -> PENDING_APPROVAL -> APPROVED/ACTIVE -> IN_PROGRESS -> ON_HOLD -> COMPLETED.
    Invalid transitions are rejected and status history is recorded.
    """
    tl = seeded_users["team_lead"]
    mgr = seeded_users["manager"]

    payload = {
        "title": "Firmware Compiler",
        "objectives": "Custom LLVM compiler",
        "deliverables": "Binary toolchain",
        "manager_employee_id": mgr["employee_id"],
        "is_draft": True
    }
    proj, _ = ProjectService.create_project(tl, payload)
    project_id = proj["project_id"]

    # DRAFT -> PENDING_APPROVAL
    p1, err1 = ProjectService.update_project_status(tl, project_id, "PENDING_APPROVAL", "Ready for review")
    assert err1 is None
    assert p1["status"] == "PENDING_APPROVAL"

    # Approve -> ACTIVE
    p2, err2 = ProjectService.approve_project(mgr, project_id)
    assert err2 is None
    assert p2["status"] == "ACTIVE"

    # ACTIVE -> IN_PROGRESS
    p3, err3 = ProjectService.update_project_status(tl, project_id, "IN_PROGRESS", "Sprint kickoff")
    assert err3 is None
    assert p3["status"] == "IN_PROGRESS"

    # IN_PROGRESS -> ON_HOLD
    p4, err4 = ProjectService.update_project_status(mgr, project_id, "ON_HOLD", "Awaiting hardware specs")
    assert err4 is None
    assert p4["status"] == "ON_HOLD"

    # ON_HOLD -> IN_PROGRESS -> COMPLETED
    ProjectService.update_project_status(mgr, project_id, "IN_PROGRESS")
    p5, err5 = ProjectService.update_project_status(mgr, project_id, "COMPLETED", "Final deliverables validated")
    assert err5 is None
    assert p5["status"] == "COMPLETED"

    # Invalid transition: COMPLETED -> PENDING_APPROVAL
    _, err_inv = ProjectService.update_project_status(tl, project_id, "PENDING_APPROVAL")
    assert err_inv is not None
    assert "Invalid status transition" in err_inv


def test_rbac_hr_strictly_restricted_from_project_creation_and_approval(db, seeded_users, client):
    """
    Requirement 7:
    HR has no project management or approval access.
    Enforced in backend services and API routes.
    """
    hr = seeded_users["hr"]
    mgr = seeded_users["manager"]

    # HR cannot create projects
    _, err_create = ProjectService.create_project(hr, {
        "title": "HR Unauthorized Project",
        "manager_employee_id": mgr["employee_id"]
    })
    assert err_create is not None
    assert "HR personnel are restricted from project operations" in err_create

    # HR cannot approve projects
    tl = seeded_users["team_lead"]
    p, _ = ProjectService.create_project(tl, {
        "title": "Auth Gate Project",
        "manager_employee_id": mgr["employee_id"]
    })
    _, err_app = ProjectService.approve_project(hr, p["project_id"])
    assert err_app is not None
    assert "Unauthorized" in err_app

    # API route GET /api/projects/pending-approvals returns 403 for HR
    token = generate_jwt_token(hr)
    res = client.get("/api/projects/pending-approvals", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 403
    data = res.get_json()
    assert "HR personnel are restricted" in data.get("error", "")
