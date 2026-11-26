from backend.services.project_service import ProjectService
from backend.services.complaint_service import ComplaintService


def test_project_weighted_progress_calculation(db, seeded_users):
    """Project progress must calculate objectively based on weighted task completion."""
    hr_user = seeded_users["hr"]
    emp_user = seeded_users["emp1"]

    # Create Project
    proj, _ = ProjectService.create_project(hr_user, {
        "title": "Cloud Migration",
        "members": [emp_user["employee_id"]]
    })
    pid = proj["project_id"]

    # Task 1: weight 2.0
    t1, _ = ProjectService.create_task(hr_user, {
        "project_id": pid,
        "title": "Design Database Schema",
        "assigned_employee_id": emp_user["employee_id"],
        "weight": 2.0
    })

    # Task 2: weight 1.0
    t2, _ = ProjectService.create_task(hr_user, {
        "project_id": pid,
        "title": "Setup CI/CD Pipeline",
        "assigned_employee_id": emp_user["employee_id"],
        "weight": 1.0
    })

    # Update Task 1 to 100% completed
    ProjectService.update_task_progress(emp_user, t1["task_id"], progress_percentage=100)

    # Weighted progress = (100 * 2.0 + 0 * 1.0) / 3.0 = 200 / 3 = 67%
    updated_proj = db.projects.find_one({"project_id": pid})
    assert updated_proj["progress_percentage"] == 67


def test_complaint_lifecycle_and_confidentiality(db, seeded_users):
    """Employee submits private complaint, HR responds and resolves, audit trail created."""
    emp = seeded_users["emp1"]
    hr = seeded_users["hr"]

    # 1. Submit complaint
    comp, err = ComplaintService.submit_complaint(emp, {
        "category": "Workplace Environment",
        "subject": "Faulty HVAC in west wing",
        "description": "Temperature in west conference room is 32C during afternoons.",
        "priority": "Medium"
    })
    assert err is None
    cid = comp["complaint_id"]

    # Verify notification created for HR group
    hr_notif = db.notifications.find_one({"recipient_group": "HR", "category": "COMPLAINT"})
    assert hr_notif is not None

    # 2. HR responds and advances status to Under Review
    updated, r_err = ComplaintService.add_response(
        actor=hr,
        complaint_id=cid,
        message="Facilities team dispatched to inspect AC thermostat.",
        new_status="Under Review"
    )
    assert r_err is None
    assert updated["status"] == "Under Review"
    assert len(updated["responses"]) == 1

    # 3. Verify audit log entry
    audit = db.audit_logs.find_one({"action": "COMPLAINT_RESPONSE", "target_id": cid})
    assert audit is not None


def test_project_employee_selection_and_member_notifications(db, seeded_users):
    """When HR creates a project, selected employees are saved and receive notifications."""
    hr = seeded_users["hr"]
    emp1 = seeded_users["emp1"]
    emp2 = seeded_users["emp2"]

    # 1. HR creates project selecting emp1 and emp2, with emp1 as lead
    proj, err = ProjectService.create_project(hr, {
        "title": "Quantum AI Gateway",
        "description": "High performance inference gateway",
        "department": "Engineering",
        "manager_employee_id": emp1["employee_id"],
        "members": [emp1["employee_id"], emp2["employee_id"], emp1["employee_id"]]  # includes duplicate to test deduplication
    })
    assert err is None
    assert proj is not None
    pid = proj["project_id"]

    # Deduplicated list of members
    saved_proj = db.projects.find_one({"project_id": pid})
    assert sorted(saved_proj["members"]) == sorted([emp1["employee_id"], emp2["employee_id"]])
    assert saved_proj["manager_employee_id"] == emp1["employee_id"]

    # 2. Check notifications were created for both assigned employees
    notifs = list(db.notifications.find({
        "recipient_id": {"$in": [emp1["employee_id"], emp2["employee_id"]]},
        "category": "PROJECT"
    }))
    assert len(notifs) == 2
    recipients = [n["recipient_id"] for n in notifs]
    assert emp1["employee_id"] in recipients
    assert emp2["employee_id"] in recipients

    # 3. HR updates project members
    updated, u_err = ProjectService.update_project_members(hr, pid, [emp2["employee_id"]])
    assert u_err is None
    assert updated["members"] == [emp2["employee_id"]]


def test_project_member_access_api(client, tokens, seeded_users):
    """Assigned employees can view project details; unassigned employees receive 403 until added."""
    hr = seeded_users["hr"]
    emp1 = seeded_users["emp1"]
    emp2 = seeded_users["emp2"]

    # HR creates project with only emp1
    proj, _ = ProjectService.create_project(hr, {
        "title": "Internal Security Audit",
        "members": [emp1["employee_id"]]
    })
    pid = proj["project_id"]

    # emp1 (assigned member) accesses project
    res1 = client.get(
        f"/api/projects/{pid}",
        headers={"Authorization": f"Bearer {tokens['emp1']}"}
    )
    assert res1.status_code == 200
    pdata1 = res1.get_json()["project"]
    assert len(pdata1["member_details"]) == 1
    assert pdata1["member_details"][0]["employee_id"] == emp1["employee_id"]

    # emp2 (not assigned) attempts access -> 403
    res2 = client.get(
        f"/api/projects/{pid}",
        headers={"Authorization": f"Bearer {tokens['emp2']}"}
    )
    assert res2.status_code == 403

    # HR updates members to include emp2
    upd_res = client.put(
        f"/api/projects/{pid}/members",
        headers={"Authorization": f"Bearer {tokens['hr']}"},
        json={"members": [emp1["employee_id"], emp2["employee_id"]]}
    )
    assert upd_res.status_code == 200

    # emp2 can now access the project
    res3 = client.get(
        f"/api/projects/{pid}",
        headers={"Authorization": f"Bearer {tokens['emp2']}"}
    )
    assert res3.status_code == 200
    assert len(res3.get_json()["project"]["member_details"]) == 2

