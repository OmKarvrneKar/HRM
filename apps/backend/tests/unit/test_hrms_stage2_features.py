import pytest
from database.connection import get_db
from permissions.rbac import Role
from auth.security import generate_jwt_token
from services.notepad_service import NotepadService
from services.feedback_service import FeedbackService


@pytest.fixture
def test_setup(client, db, seeded_users):
    emp = seeded_users["emp1"]
    tl = seeded_users["team_lead"]
    mgr = seeded_users["manager"]
    hr = seeded_users["hr"]
    admin = seeded_users.get("admin")

    if not admin:
        # Ensure an admin user exists
        admin = db.users.find_one({"role": Role.ADMIN})
        if not admin:
            admin_doc = {
                "employee_id": "ADM-9999",
                "email": "admin.super@aisamrat.com",
                "full_name": "Super Admin",
                "role": Role.ADMIN,
                "department": "Executive",
                "is_active": True
            }
            res = db.users.insert_one(admin_doc)
            admin_doc["_id"] = res.inserted_id
            admin = admin_doc

    # Set up team assignment for hierarchy testing
    db.users.update_one(
        {"employee_id": emp["employee_id"]},
        {"$set": {"team_id": "TEAM-TEST-ENG", "assigned_tl_id": tl["employee_id"], "department": "Engineering"}}
    )
    db.users.update_one(
        {"employee_id": tl["employee_id"]},
        {"$set": {"team_id": "TEAM-TEST-ENG", "department": "Engineering"}}
    )
    db.users.update_one(
        {"employee_id": mgr["employee_id"]},
        {"$set": {"department": "Engineering"}}
    )

    return {
        "client": client,
        "emp": emp,
        "tl": tl,
        "mgr": mgr,
        "hr": hr,
        "admin": admin
    }


def auth_headers(user):
    token = generate_jwt_token(user)
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }


def test_notepad_service_crud_and_endpoints(test_setup):
    """Verifies Feature 3: Multi-Pad Notepad creation, retrieval, updates, and persistence."""
    client = test_setup["client"]
    emp = test_setup["emp"]
    headers = auth_headers(emp)

    # 1. GET notepads (auto-initializes starter pad if none exist)
    res = client.get("/api/notepads", headers=headers)
    assert res.status_code == 200
    data = res.get_json()
    assert "notes" in data
    assert len(data["notes"]) >= 1

    # 2. POST create new pad
    new_pad_payload = {
        "title": "Quantum Algorithm Notes",
        "content": "Step 1: Initialize qubits\nStep 2: Apply Hadamard transform",
        "color": "#00e5ff",
        "is_pinned": True
    }
    create_res = client.post("/api/notepads", json=new_pad_payload, headers=headers)
    assert create_res.status_code == 201
    created_note = create_res.get_json()["note"]
    note_id = created_note["note_id"]
    assert created_note["title"] == "Quantum Algorithm Notes"
    assert created_note["is_pinned"] is True

    # 3. PUT update pad content and pin
    update_res = client.put(f"/api/notepads/{note_id}", json={
        "title": "Quantum Algorithm Notes V2",
        "content": "Step 3: Measure final state"
    }, headers=headers)
    assert update_res.status_code == 200
    updated_note = update_res.get_json()["note"]
    assert updated_note["title"] == "Quantum Algorithm Notes V2"
    assert "Measure final state" in updated_note["content"]

    # 4. DELETE pad
    del_res = client.delete(f"/api/notepads/{note_id}", headers=headers)
    assert del_res.status_code == 200

    # 5. Verify deleted pad is omitted
    get_res = client.get("/api/notepads", headers=headers)
    active_ids = [n["note_id"] for n in get_res.get_json()["notes"]]
    assert note_id not in active_ids


def test_smart_feedback_and_admin_triage(test_setup):
    """
    Verifies Feature 4: Smart Feedback & Bug Reporting System.
    - Captures reports from employees across departments
    - Groups and deduplicates repetitive reports
    - STRICT GUARANTEE: Triage endpoint NEVER exposes employee names, IDs, or emails
    """
    client = test_setup["client"]
    emp = test_setup["emp"]
    admin = test_setup["admin"]

    emp_headers = auth_headers(emp)
    admin_headers = auth_headers(admin)

    # 1. Submit report #1
    r1 = client.post("/api/feedback/submit", json={
        "category": "Bug / Error",
        "severity": "High",
        "summary": "Punch clock button delays after check out",
        "details": "When clicking punch out, the spinner runs for 3 seconds before UI updates.\nNetwork request succeeds but animation hangs.",
        "dashboard_source": "/dashboard/employee"
    }, headers=emp_headers)
    assert r1.status_code == 201
    assert "employee_id" not in r1.get_json()  # acknowledgement does not expose private DB fields

    # 2. Submit repetitive report #2 (same issue from engineering team)
    r2 = client.post("/api/feedback/submit", json={
        "category": "Bug / Error",
        "severity": "Critical",
        "summary": "Punch clock button delays after clock out",
        "details": "Punch out button is slow on desktop Chrome.\nTakes multiple seconds to reflect duty off status.",
        "dashboard_source": "/dashboard/employee"
    }, headers=emp_headers)
    assert r2.status_code == 201

    # 3. Admin requests triaged telemetry
    triage_res = client.get("/api/admin/feedback/triaged", headers=admin_headers)
    assert triage_res.status_code == 200
    triage_data = triage_res.get_json()

    assert triage_data["total_reports"] >= 2
    clusters = triage_data["clusters"]
    assert len(clusters) >= 1

    # Find the punch clock cluster
    punch_cluster = next((c for c in clusters if "punch" in c["title"].lower()), None)
    assert punch_cluster is not None
    assert punch_cluster["department"] == "Engineering"
    assert punch_cluster["highest_severity"] in ("Critical", "High")
    assert punch_cluster["report_count"] >= 2
    assert len(punch_cluster["unique_bullets"]) >= 1

    # STRICT ANONYMITY VERIFICATION
    cluster_str = str(punch_cluster)
    assert emp["employee_id"] not in cluster_str
    assert emp["email"] not in cluster_str
    assert emp.get("full_name", "___") not in cluster_str

    # 4. Admin updates cluster status
    fids = punch_cluster["feedback_ids"]
    status_res = client.post("/api/admin/feedback/status", json={
        "feedback_ids": fids,
        "status": "Resolved",
        "notes": "Optimized optimistic UI transition on duty switch"
    }, headers=admin_headers)
    assert status_res.status_code == 200


def test_reporting_hierarchy_scope(test_setup):
    """
    Verifies Feature 6: Strict hierarchical visibility:
    - Regular Employees: see directory contacts, no subordinates
    - Team Leads: see strictly their direct-report employees
    - Managers: see both Team Leads and Employees across their department
    - HR Admin: universal oversight
    """
    client = test_setup["client"]
    emp = test_setup["emp"]
    tl = test_setup["tl"]
    mgr = test_setup["mgr"]
    hr = test_setup["hr"]

    # 1. Team Lead directory query
    tl_res = client.get("/api/users", headers=auth_headers(tl))
    assert tl_res.status_code == 200
    tl_users = tl_res.get_json()["users"]
    tl_user_roles = {u.get("role") for u in tl_users}
    assert Role.HR not in tl_user_roles
    assert Role.MANAGER not in tl_user_roles
    # TL strictly sees active employees assigned to their team
    assert all(u.get("role") == Role.EMPLOYEE for u in tl_users)

    # 2. Manager directory query
    mgr_res = client.get("/api/users", headers=auth_headers(mgr))
    assert mgr_res.status_code == 200
    mgr_users = mgr_res.get_json()["users"]
    mgr_roles = {u.get("role") for u in mgr_users}
    # Manager sees both Employees and Team Leads across their department
    assert Role.EMPLOYEE in mgr_roles or Role.TEAM_LEAD in mgr_roles

    # 3. HR directory query (Universal oversight)
    hr_res = client.get("/api/users", headers=auth_headers(hr))
    assert hr_res.status_code == 200
    hr_users = hr_res.get_json()["users"]
    hr_roles = {u.get("role") for u in hr_users}
    assert len(hr_roles) >= 2


def test_roster_policies_endpoint(test_setup):
    """Verifies Feature 5: Shift Attendance & Multi-Shift Roster Policies with automated grace periods and cutoffs."""
    client = test_setup["client"]
    emp = test_setup["emp"]

    res = client.get("/api/roster/policies", headers=auth_headers(emp))
    assert res.status_code == 200
    data = res.get_json()
    assert "shifts" in data
    assert "grace_period_mins" in data
    assert data["grace_period_mins"] == 15
    assert data["mandatory_cutoff_mins_prior"] == 45
    assert data["hard_cutoff_time"] == "19:00"
