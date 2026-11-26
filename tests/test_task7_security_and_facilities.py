import json
import os
import requests

BASE_URL = "http://127.0.0.1:5000"

def run_tests():
    print("=================================================================")
    print("TASK 7: FACILITY VERIFICATION & ONBOARDING SECURITY TEST SUITE")
    print("=================================================================")

    # 1. Login as Admin
    session = requests.Session()
    login_res = session.post(f"{BASE_URL}/api/auth/login", json={
        "email": "admin@aisamrat.com",
        "password": "password123"
    })
    assert login_res.status_code == 200, f"Admin login failed: {login_res.text}"
    token = login_res.json().get("token") or login_res.json().get("access_token")
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    print("✓ Successfully authenticated as Admin.")

    # -----------------------------------------------------------------
    # SECTION 1: MEETING ROOM VERIFICATION
    # -----------------------------------------------------------------
    print("\n--- 1. Meeting Room Verification ---")
    rooms_res = session.get(f"{BASE_URL}/api/facilities/rooms", headers=headers)
    assert rooms_res.status_code == 200, f"Facilities rooms API failed: {rooms_res.text}"
    rooms_data = rooms_res.json()
    rooms = rooms_data.get("rooms", [])
    print(f"Total Rooms returned by API: {len(rooms)}")
    for r in rooms:
        print(f"  • Room ID: {r.get('room_id')}")
        print(f"    Name: {r.get('name')}")
        print(f"    Floor: {r.get('floor')}")
        print(f"    Capacity: {r.get('capacity')} seats")
        print(f"    Features: {r.get('features')}")
        print(f"    Verification Status: {r.get('verification_status')} (is_verified={r.get('is_verified')})")

    # -----------------------------------------------------------------
    # SECTION 2: SEATING ALLOCATION SAFETY & AUDIT
    # -----------------------------------------------------------------
    print("\n--- 2. Seating Allocations Audit (All 38 Records) ---")
    seat_res = session.get(f"{BASE_URL}/api/assets/seating-lockers", headers=headers)
    assert seat_res.status_code == 200, f"Seating API failed: {seat_res.text}"
    seat_data = seat_res.json()
    all_allocs = seat_data.get("all_allocations", [])
    print(f"Total Allocations returned by API: {len(all_allocs)}")
    
    algorithmic_count = 0
    for idx, a in enumerate(all_allocs, start=1):
        alloc_id = a.get("allocation_id")
        emp_id = a.get("employee_id") or a.get("emp_id")
        emp_name = a.get("employee_name")
        desk = a.get("desk_number")
        v_status = a.get("verification_status")
        is_v = a.get("is_verified")
        print(f"  [{idx:02d}] ID: {alloc_id:<14} | Emp: {emp_id:<10} ({emp_name:<26}) | Desk: {desk:<10} | Status: {v_status}")
        if not is_v:
            algorithmic_count += 1
    print(f"\nTotal Algorithmic / Unverified Seating Allocations: {algorithmic_count} / {len(all_allocs)}")

    # -----------------------------------------------------------------
    # SECTION 3: BACKEND ONBOARDING SECURITY GUARDS
    # -----------------------------------------------------------------
    print("\n--- 3. Backend Onboarding Security Tests ---")
    
    # Pick a candidate who is pending verification
    users_res = session.get(f"{BASE_URL}/api/users", headers=headers)
    users_list = users_res.json().get("users", [])
    pending_candidates = [u for u in users_list if u.get("verification_status") == "pending_verification"]
    assert len(pending_candidates) > 0, "No pending verification candidates found to test!"
    test_cand = pending_candidates[0]
    cand_id = test_cand.get("employee_id") or test_cand.get("email") or str(test_cand.get("_id"))
    print(f"Target pending candidate for security probing: {test_cand.get('email')} (Key: {cand_id})")

    # Test 3.1: Direct API attempt to activate pending candidate without employee ID
    print("\n  [Test 3.1] Attempt to activate pending candidate without Employee ID...")
    payload_1 = {
        "updates": {
            "is_active": True,
            "verification_status": "pending_verification"
        }
    }
    res_1 = session.put(f"{BASE_URL}/api/users/{cand_id}", json=payload_1, headers=headers)
    print(f"  Response: HTTP {res_1.status_code} | {res_1.json()}")
    assert res_1.status_code == 400, f"Expected HTTP 400 rejection, got {res_1.status_code}"
    print("  ✓ PASSED: Direct activation without employee ID / verification rejected.")

    # Test 3.2: Direct API attempt to activate candidate without verified profile
    print("\n  [Test 3.2] Attempt to activate candidate without verified profile (with dummy ID)...")
    payload_2 = {
        "updates": {
            "is_active": True,
            "employee_id": "AS-9999",
            "verification_status": "pending_verification"
        }
    }
    res_2 = session.put(f"{BASE_URL}/api/users/{cand_id}", json=payload_2, headers=headers)
    print(f"  Response: HTTP {res_2.status_code} | {res_2.json()}")
    assert res_2.status_code == 400, f"Expected HTTP 400 rejection, got {res_2.status_code}"
    print("  ✓ PASSED: Direct activation without verified profile rejected.")

    # Test 3.3: Submit onboarding with missing department
    print("\n  [Test 3.3] Attempt onboarding verification with missing Department...")
    payload_3 = {
        "updates": {
            "employee_id": "AS-1099",
            "full_name": "Test Candidate",
            "department": "",
            "designation": "Software Engineer",
            "role": "employee",
            "verification_status": "verified"
        }
    }
    res_3 = session.put(f"{BASE_URL}/api/users/{cand_id}", json=payload_3, headers=headers)
    print(f"  Response: HTTP {res_3.status_code} | {res_3.json()}")
    assert res_3.status_code == 400, f"Expected HTTP 400 rejection, got {res_3.status_code}"
    print("  ✓ PASSED: Verification with missing Department rejected.")

    # Test 3.4: Submit onboarding with missing designation
    print("\n  [Test 3.4] Attempt onboarding verification with missing Designation...")
    payload_4 = {
        "updates": {
            "employee_id": "AS-1099",
            "full_name": "Test Candidate",
            "department": "Engineering",
            "designation": "",
            "role": "employee",
            "verification_status": "verified"
        }
    }
    res_4 = session.put(f"{BASE_URL}/api/users/{cand_id}", json=payload_4, headers=headers)
    print(f"  Response: HTTP {res_4.status_code} | {res_4.json()}")
    assert res_4.status_code == 400, f"Expected HTTP 400 rejection, got {res_4.status_code}"
    print("  ✓ PASSED: Verification with missing Designation rejected.")

    # Test 3.5: Submit onboarding with missing system role
    print("\n  [Test 3.5] Attempt onboarding verification with missing/invalid Role...")
    payload_5 = {
        "updates": {
            "employee_id": "AS-1099",
            "full_name": "Test Candidate",
            "department": "Engineering",
            "designation": "Software Engineer",
            "role": "",
            "verification_status": "verified"
        }
    }
    res_5 = session.put(f"{BASE_URL}/api/users/{cand_id}", json=payload_5, headers=headers)
    print(f"  Response: HTTP {res_5.status_code} | {res_5.json()}")
    assert res_5.status_code == 400, f"Expected HTTP 400 rejection, got {res_5.status_code}"
    print("  ✓ PASSED: Verification with missing/invalid Role rejected.")

    # Test 3.6: Direct shortcut toggle status on pending candidate
    print("\n  [Test 3.6] Attempt shortcut toggle status on unverified candidate...")
    res_6 = session.post(f"{BASE_URL}/api/users/{cand_id}/toggle-status", headers=headers)
    print(f"  Response: HTTP {res_6.status_code} | {res_6.json()}")
    assert res_6.status_code == 400, f"Expected HTTP 400 rejection, got {res_6.status_code}"
    print("  ✓ PASSED: Shortcut status toggle on unverified candidate rejected.")

    # Test 3.7: Verify existing verified employee accounts remain untouched and active
    print("\n  [Test 3.7] Verify existing verified employee accounts remain active and intact...")
    admin_user = session.get(f"{BASE_URL}/api/users/ADMIN-1001", headers=headers).json().get("user", {})
    as1001_user = session.get(f"{BASE_URL}/api/users/AS-1001", headers=headers).json().get("user", {})
    assert admin_user.get("is_active") is True, "ADMIN-1001 was modified or deactivated!"
    assert as1001_user.get("is_active") is True, "AS-1001 was modified or deactivated!"
    print(f"  ✓ Confirmed: ADMIN-1001 is active ({admin_user.get('full_name')})")
    print(f"  ✓ Confirmed: AS-1001 is active ({as1001_user.get('full_name')})")

    # Confirm candidate is still unverified and inactive
    all_users = session.get(f"{BASE_URL}/api/users", headers=headers).json().get("users", [])
    refreshed_cand = next((u for u in all_users if u.get("email") == test_cand.get("email")), {})
    assert refreshed_cand.get("is_active") is not True, "Candidate was improperly activated!"
    assert refreshed_cand.get("verification_status") == "pending_verification", "Candidate status changed!"
    print(f"  ✓ Confirmed: Candidate {test_cand.get('email')} remains safely inactive (is_active={refreshed_cand.get('is_active')}, verification_status={refreshed_cand.get('verification_status')})")

    print("\n=================================================================")
    print("ALL TASK 7 SECURITY & RECONCILIATION TESTS PASSED WITH 100% SUCCESS")
    print("=================================================================")

if __name__ == "__main__":
    run_tests()
