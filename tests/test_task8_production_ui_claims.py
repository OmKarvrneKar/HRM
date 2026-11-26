import json
import os
import requests

BASE_URL = "http://127.0.0.1:5000"

def run_tests():
    print("=================================================================")
    print("TASK 8: UNVERIFIED FACILITY CLAIMS & VERIFICATION CONTROLS SUITE")
    print("=================================================================")

    # 1. Login as Admin
    session_admin = requests.Session()
    login_admin = session_admin.post(f"{BASE_URL}/api/auth/login", json={
        "email": "admin@aisamrat.com",
        "password": "password123"
    })
    assert login_admin.status_code == 200, f"Admin login failed: {login_admin.text}"
    token_admin = login_admin.json().get("token") or login_admin.json().get("access_token")
    headers_admin = {"Authorization": f"Bearer {token_admin}", "Content-Type": "application/json"}
    print("✓ Successfully authenticated as Admin (ADMIN-1001).")

    # 2. Login as regular Employee (AS-1001)
    session_emp = requests.Session()
    login_emp = session_emp.post(f"{BASE_URL}/api/auth/login", json={
        "identifier": "AS-1001",
        "password": "password123"
    })
    assert login_emp.status_code == 200, f"Employee login failed: {login_emp.text}"
    token_emp = login_emp.json().get("token") or login_emp.json().get("access_token")
    headers_emp = {"Authorization": f"Bearer {token_emp}", "Content-Type": "application/json"}
    print("✓ Successfully authenticated as Employee (AS-1001).")

    # -----------------------------------------------------------------
    # SECTION 1: MEETING ROOMS BASELINE AUDIT
    # -----------------------------------------------------------------
    print("\n--- 1. Testing Meeting Rooms Baseline Counts ---")
    res_rooms = session_admin.get(f"{BASE_URL}/api/facilities/rooms", headers=headers_admin)
    assert res_rooms.status_code == 200
    rooms_data = res_rooms.json()
    verified_rooms = rooms_data.get("verified_rooms_count", 0)
    unverified_rooms = rooms_data.get("unverified_rooms_count", 0)
    total_rooms = rooms_data.get("total_rooms", 0)

    print(f"  • Total Rooms in Registry: {total_rooms}")
    print(f"  • Confirmed Verified Rooms: {verified_rooms}")
    print(f"  • Unverified Baseline Rooms: {unverified_rooms}")
    assert verified_rooms == 0, f"Expected 0 verified rooms initially, got {verified_rooms}"
    assert unverified_rooms == 3, f"Expected 3 unverified rooms, got {unverified_rooms}"
    for r in rooms_data.get("rooms", []):
        assert r.get("is_verified") is False, f"Room {r.get('room_id')} should not be verified"
        assert r.get("status") == "Unverified", f"Room {r.get('room_id')} status should be Unverified, got {r.get('status')}"
    print("  ✓ PASSED: Meeting rooms correctly report 0 confirmed, 3 unverified baseline.")

    # -----------------------------------------------------------------
    # SECTION 2: SEATING ALLOCATIONS BASELINE AUDIT
    # -----------------------------------------------------------------
    print("\n--- 2. Testing Seating Allocations Baseline Counts ---")
    res_seat = session_admin.get(f"{BASE_URL}/api/assets/seating-lockers", headers=headers_admin)
    assert res_seat.status_code == 200
    seat_data = res_seat.json()
    confirmed_desks = seat_data.get("confirmed_allocated", 0)
    provisional_desks = seat_data.get("provisional_allocated", 0)
    total_desks = seat_data.get("total_records", 0)

    print(f"  • Total Workstation Records: {total_desks}")
    print(f"  • Confirmed Allocated Desks: {confirmed_desks}")
    print(f"  • Provisional Layout Desks: {provisional_desks}")
    assert confirmed_desks == 0, f"Expected 0 confirmed desks initially, got {confirmed_desks}"
    assert provisional_desks == 38, f"Expected 38 provisional desks, got {provisional_desks}"
    for a in seat_data.get("all_allocations", []):
        assert a.get("is_verified") is False, f"Allocation {a.get('allocation_id')} should not be verified"
        assert a.get("status") == "Provisional", f"Allocation status should be Provisional, got {a.get('status')}"
    print("  ✓ PASSED: Seating allocations correctly report 0 confirmed, 38 provisional.")

    # -----------------------------------------------------------------
    # SECTION 3: ROLE-BASED VERIFICATION PERMISSION CONTROLS
    # -----------------------------------------------------------------
    print("\n--- 3. Testing Role-Based Verification Permissions ---")
    
    # 3.1 Employee attempts to verify a room -> MUST BE FORBIDDEN (HTTP 403)
    print("  [Test 3.1] Regular Employee attempts to verify a meeting room...")
    res_emp_room = session_emp.post(f"{BASE_URL}/api/facilities/rooms/ROOM-MANTHAN/verify", json={
        "notes": "Unauthorized employee attempt"
    }, headers=headers_emp)
    print(f"  Response: HTTP {res_emp_room.status_code} | {res_emp_room.text[:100]}")
    assert res_emp_room.status_code == 403, f"Expected HTTP 403 Forbidden, got {res_emp_room.status_code}"
    print("  ✓ PASSED: Non-admin employee blocked from verifying facilities.")

    # 3.2 Employee attempts to verify a desk allocation -> MUST BE FORBIDDEN (HTTP 403)
    print("\n  [Test 3.2] Regular Employee attempts to verify a seating allocation...")
    res_emp_seat = session_emp.post(f"{BASE_URL}/api/assets/seating-lockers/SL-AS-1001/verify", json={
        "notes": "Unauthorized employee attempt"
    }, headers=headers_emp)
    print(f"  Response: HTTP {res_emp_seat.status_code} | {res_emp_seat.text[:100]}")
    assert res_emp_seat.status_code == 403, f"Expected HTTP 403 Forbidden, got {res_emp_seat.status_code}"
    print("  ✓ PASSED: Non-admin employee blocked from verifying seating.")

    # 3.3 Authorized HR/Admin verifies a meeting room
    print("\n  [Test 3.3] Authorized Admin verifies ROOM-MANTHAN with official facility audit details...")
    res_admin_room = session_admin.post(f"{BASE_URL}/api/facilities/rooms/ROOM-MANTHAN/verify", json={
        "name": "Manthan Executive Boardroom",
        "floor": "4th Floor — Executive Wing",
        "capacity": 20,
        "features": ["4K Video Wall", "Polycom Trio Dual-Mic", "Acoustic Insulation", "Executive Whiteboard"],
        "notes": "Physically verified by Administration facility audit"
    }, headers=headers_admin)
    print(f"  Response: HTTP {res_admin_room.status_code} | {res_admin_room.json().get('message')}")
    assert res_admin_room.status_code == 200
    verified_room_doc = res_admin_room.json().get("room", {})
    assert verified_room_doc.get("is_verified") is True
    assert verified_room_doc.get("status") == "Available"
    assert verified_room_doc.get("verified_by_id") == "ADMIN-1001"
    print(f"  ✓ Verified by: {verified_room_doc.get('verified_by_name')} ({verified_room_doc.get('verified_by_id')}) at {verified_room_doc.get('verified_at')}")

    # 3.4 Authorized HR/Admin verifies a seating allocation
    print("\n  [Test 3.4] Authorized Admin verifies SL-AS-1001 with confirmed desk assignment...")
    res_admin_seat = session_admin.post(f"{BASE_URL}/api/assets/seating-lockers/SL-AS-1001/verify", json={
        "desk_number": "FL3-A-01",
        "locker_number": "LCK-301",
        "floor": "Floor 3 — Bay A",
        "notes": "Physically assigned to Sneha K with RFID keycard issued"
    }, headers=headers_admin)
    print(f"  Response: HTTP {res_admin_seat.status_code} | {res_admin_seat.json().get('message')}")
    assert res_admin_seat.status_code == 200
    verified_seat_doc = res_admin_seat.json().get("allocation", {})
    assert verified_seat_doc.get("is_verified") is True
    assert verified_seat_doc.get("status") == "Allocated"
    assert verified_seat_doc.get("verified_by_id") == "ADMIN-1001"
    print(f"  ✓ Verified by: {verified_seat_doc.get('verified_by_name')} ({verified_seat_doc.get('verified_by_id')}) at {verified_seat_doc.get('verified_at')}")

    # -----------------------------------------------------------------
    # SECTION 4: RE-AUDIT DASHBOARD COUNTS AFTER VERIFICATION
    # -----------------------------------------------------------------
    print("\n--- 4. Re-auditing Dashboard Counts After Verification ---")
    refreshed_rooms = session_admin.get(f"{BASE_URL}/api/facilities/rooms", headers=headers_admin).json()
    refreshed_seats = session_admin.get(f"{BASE_URL}/api/assets/seating-lockers", headers=headers_admin).json()

    print(f"  • Confirmed Verified Rooms: {refreshed_rooms.get('verified_rooms_count')} (Unverified: {refreshed_rooms.get('unverified_rooms_count')})")
    print(f"  • Confirmed Allocated Desks: {refreshed_seats.get('confirmed_allocated')} (Provisional: {refreshed_seats.get('provisional_allocated')})")
    assert refreshed_rooms.get("verified_rooms_count") == 1
    assert refreshed_rooms.get("unverified_rooms_count") == 2
    assert refreshed_seats.get("confirmed_allocated") == 1
    assert refreshed_seats.get("provisional_allocated") == 37
    print("  ✓ PASSED: Dashboard counts dynamically and accurately distinguish verified vs. provisional records!")

    print("\n=================================================================")
    print("ALL TASK 8 PERMISSION & FACILITY VERIFICATION TESTS PASSED 100%!")
    print("=================================================================")

if __name__ == "__main__":
    run_tests()

