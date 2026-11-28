import pytest
from datetime import datetime, timezone
from permissions.rbac import Role
from services.roster_service import RosterService

def test_login_does_not_clock_in(client, seeded_users, tokens):
    """Verify that authenticating/logging in via HTTP does NOT auto-clock into attendance."""
    emp_user = seeded_users["emp1"]
    token = tokens["emp1"]

    # Verify no open attendance session exists
    today_res = client.get('/api/attendance/today', headers={"Authorization": f"Bearer {token}"})
    assert today_res.status_code == 200
    today_data = today_res.get_json()
    assert today_data.get("has_open_session") is False

def test_shift_rosters_crud_and_assignment(client, seeded_users, tokens, db):
    """Verify HR can fetch, create, assign, and delete shift rosters in org settings."""
    hr_token = tokens["hr"]

    # 1. Fetch shifts (defaults initialized)
    res = client.get('/api/shifts', headers={"Authorization": f"Bearer {hr_token}"})
    assert res.status_code == 200
    shifts = res.get_json().get("shifts", [])
    assert len(shifts) >= 4
    shift_ids = [s["shift_id"] for s in shifts]
    assert "SHIFT-GEN" in shift_ids
    assert "SHIFT-MORN" in shift_ids

    # 2. Create custom shift
    custom_shift = {
        "shift_id": "SHIFT-CUST-01",
        "name": "APAC Custom Support Shift",
        "start_time": "06:00",
        "end_time": "15:00",
        "grace_minutes": 15,
        "cutoff_time": "16:00",
        "color": "warning",
        "description": "Morning coverage for APAC customers"
    }
    create_res = client.post('/api/shifts', json=custom_shift, headers={"Authorization": f"Bearer {hr_token}"})
    assert create_res.status_code == 200
    assert create_res.get_json().get("success") is True

    # 3. Assign staff to the custom shift
    assign_res = client.post('/api/shifts/assign', json={
        "shift_id": "SHIFT-CUST-01",
        "employee_ids": ["EMP-TEST-1", "EMP-TEST-2"]
    }, headers={"Authorization": f"Bearer {hr_token}"})
    assert assign_res.status_code == 200
    assign_data = assign_res.get_json()
    assert assign_data.get("success") is True
    assert assign_data.get("assigned_count") == 2

    # Verify assignment updated in DB
    user_test_1 = db.users.find_one({"employee_id": "EMP-TEST-1"})
    assert user_test_1.get("shift_id") == "SHIFT-CUST-01"

    # 4. Delete the shift (assigned employees transition to SHIFT-GEN)
    del_res = client.delete('/api/shifts/SHIFT-CUST-01', headers={"Authorization": f"Bearer {hr_token}"})
    assert del_res.status_code == 200
    user_test_1_recheck = db.users.find_one({"employee_id": "EMP-TEST-1"})
    assert user_test_1_recheck.get("shift_id") == "SHIFT-GEN"

def test_feedback_integrated_with_support_ticket(client, seeded_users, tokens, db):
    """Verify system feedback creates a support ticket routed to the designated authority."""
    emp_token = tokens["emp1"]

    payload = {
        "category": "Network & VPN Access",
        "severity": "High",
        "assigned_role": "admin",
        "summary": "VPN gateway timeout when accessing staging DB",
        "details": "Connection drops every 10 minutes from remote subnet.",
        "dashboard_source": "/dashboard/employee"
    }

    res = client.post('/api/feedback/submit', json=payload, headers={"Authorization": f"Bearer {emp_token}"})
    assert res.status_code == 201
    data = res.get_json()
    assert data.get("success") is True
    assert "ticket_id" in data
    assert "System" in data.get("assigned_role_name", "")

    # Verify ticket saved in db.support_tickets
    ticket = db.support_tickets.find_one({"ticket_id": data["ticket_id"]})
    assert ticket is not None
    assert ticket.get("assigned_role") == "admin"
    assert ticket.get("priority") == "High"

def test_hr_attendance_correction_review(client, seeded_users, tokens, db):
    """Verify HR can view pending attendance corrections and approve them."""
    emp_token = tokens["emp1"]
    hr_token = tokens["hr"]

    # 1. Employee submits a correction request
    req_res = client.post('/api/attendance/corrections/request', json={
        "target_date": "2026-11-09",
        "correction_type": "MISSED_PUNCH_IN",
        "requested_in_time": "10:00",
        "requested_out_time": "18:00",
        "reason": "Biometric scanner power outage"
    }, headers={"Authorization": f"Bearer {emp_token}"})
    assert req_res.status_code == 200
    req_data = req_res.get_json()
    assert req_data.get("success") is True
    request_id = req_data["correction"]["request_id"]

    # 2. HR logs in and views pending corrections
    pending_res = client.get('/api/attendance/corrections/pending', headers={"Authorization": f"Bearer {hr_token}"})
    assert pending_res.status_code == 200
    pending_list = pending_res.get_json().get("pending_corrections", [])
    req_ids = [p["request_id"] for p in pending_list]
    assert request_id in req_ids

    # 3. HR reviews and approves correction
    rev_res = client.post(f'/api/attendance/corrections/{request_id}/review', json={
        "decision": "APPROVED",
        "remarks": "Approved after biometric audit verification"
    }, headers={"Authorization": f"Bearer {hr_token}"})
    assert rev_res.status_code == 200
    assert rev_res.get_json().get("success") is True

    # Check updated record in DB
    updated = db.attendance_corrections.find_one({"request_id": request_id})
    assert updated["status"] == "APPROVED"
    assert updated["reviewed_by_id"] == "HR-TEST"
