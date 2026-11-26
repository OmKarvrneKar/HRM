import sys
import os

# Ensure backend can be imported
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import app
from backend.auth.security import generate_jwt_token
from backend.database.connection import get_db

def run_task2_verifications():
    print("=== STARTING TASK 2 API ENDPOINT VERIFICATION ===")
    client = app.test_client()

    db = get_db()
    test_user = db.users.find_one({"employee_id": "AS-1019"})
    if not test_user:
        test_user = db.users.find_one({"emp_id": "AS-1019"})
    
    assert test_user is not None, "Test user AS-1019 must exist in genuine roster"
    
    # Generate auth token for AS-1019
    token = generate_jwt_token(test_user)
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    # 1. Overtime APIs
    print("\n--- 1. Testing Overtime APIs ---")
    # GET /api/overtime/list
    res = client.get("/api/overtime/list", headers=headers)
    print(f"GET /api/overtime/list -> status {res.status_code}")
    assert res.status_code == 200, f"Expected 200, got {res.status_code}"
    ot_data = res.get_json()
    assert ot_data.get("success") is True
    assert "overtime_requests" in ot_data
    print(f"  Success: retrieved {len(ot_data['overtime_requests'])} overtime requests")

    # POST /api/overtime/request
    ot_payload = {
        "overtime_date": "2026-11-25",
        "start_time": "07:00 PM",
        "end_time": "09:00 PM",
        "reason": "Task 2 Automated Verification OT Request",
        "overtime_type": "After shift"
    }
    res = client.post("/api/overtime/request", headers=headers, json=ot_payload)
    print(f"POST /api/overtime/request -> status {res.status_code}")
    assert res.status_code in (200, 201), f"Expected 200/201, got {res.status_code}: {res.get_data(as_text=True)}"
    ot_submit_data = res.get_json()
    assert ot_submit_data.get("success") is True
    print(f"  Success: Created OT request ID: {ot_submit_data.get('request', {}).get('request_id')}")

    # Verify OT is in the list
    res = client.get("/api/overtime/list", headers=headers)
    ot_data = res.get_json()
    req_ids = [r.get("request_id") for r in ot_data.get("overtime_requests", [])]
    assert ot_submit_data.get("request", {}).get("request_id") in req_ids
    print(f"  Verified OT request appears in list.")

    # 2. Assets Inventory API
    print("\n--- 2. Testing Hardware & Software Unified Inventory API ---")
    res = client.get("/api/assets/inventory", headers=headers)
    print(f"GET /api/assets/inventory -> status {res.status_code}")
    assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.get_data(as_text=True)}"
    inv_data = res.get_json()
    assert inv_data.get("success") is True
    assert "hardware" in inv_data, "hardware key missing in /api/assets/inventory"
    assert "software" in inv_data, "software key missing in /api/assets/inventory"
    hardware = inv_data["hardware"]
    software = inv_data["software"]
    print(f"  Success: Retrieved {len(hardware)} hardware items and {len(software)} software items")
    if hardware:
        print(f"  Sample hardware: {hardware[0].get('asset_tag')} - {hardware[0].get('model')}")
    if software:
        print(f"  Sample software: {software[0].get('license_id')} - {software[0].get('software_name')}")

    # 3. Seating and Locker APIs
    print("\n--- 3. Testing Seating & Locker API ---")
    res = client.get("/api/assets/seating-lockers", headers=headers)
    print(f"GET /api/assets/seating-lockers -> status {res.status_code}")
    assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.get_data(as_text=True)}"
    seating_data = res.get_json()
    assert seating_data.get("success") is True
    print(f"  Success: My seating: {seating_data.get('my_seating', {}).get('desk_number', 'N/A')}")
    print(f"  Total allocations returned: {seating_data.get('total_allocated', len(seating_data.get('all_allocations', [])))}")

    # 4. Kudos APIs
    print("\n--- 4. Testing Kudos APIs ---")
    # GET /api/engagement/kudos
    res = client.get("/api/engagement/kudos", headers=headers)
    print(f"GET /api/engagement/kudos -> status {res.status_code}")
    assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.get_data(as_text=True)}"
    kudos_data = res.get_json()
    assert kudos_data.get("success") is True
    assert "leaderboard" in kudos_data
    assert "recent_kudos" in kudos_data or "kudos" in kudos_data
    print(f"  Success: Leaderboard has {len(kudos_data.get('leaderboard', []))} entries")
    recent = kudos_data.get("recent_kudos") or kudos_data.get("kudos", [])
    print(f"  Success: Recent kudos feed has {len(recent)} items")

    # POST /api/engagement/kudos/send (to AS-1001 / Sneha K)
    kudos_payload = {
        "recipient_id": "AS-1001",
        "points": 50,
        "category": "Teamwork",
        "message": "Task 2 automated appreciation test"
    }
    res = client.post("/api/engagement/kudos/send", headers=headers, json=kudos_payload)
    print(f"POST /api/engagement/kudos/send (with recipient_id) -> status {res.status_code}")
    assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.get_data(as_text=True)}"
    send_data = res.get_json()
    assert send_data.get("success") is True
    print(f"  Success message: {send_data.get('message')}")

    # Also test POST with recipient_name
    kudos_payload_name = {
        "recipient_name": "Lekhana S N",
        "points": 50,
        "category": "Excellence",
        "message": "Task 2 automated appreciation test with name"
    }
    res = client.post("/api/engagement/kudos/send", headers=headers, json=kudos_payload_name)
    print(f"POST /api/engagement/kudos/send (with recipient_name) -> status {res.status_code}")
    assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.get_data(as_text=True)}"
    print(f"  Success message: {res.get_json().get('message')}")

    print("\n=== ALL TASK 2 API ENDPOINT VERIFICATIONS PASSED SUCCESSFULLY! ===")

if __name__ == "__main__":
    run_task2_verifications()

