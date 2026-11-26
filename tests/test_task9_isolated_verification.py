import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

# Add HRM-main to sys.path so we can import models, config, and services
PROJECT_ROOT = Path(__file__).resolve().parent.parent
HRM_BACKEND_DIR = PROJECT_ROOT / "HRM-main"
if str(HRM_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(HRM_BACKEND_DIR))

PROD_STORAGE_DIR = HRM_BACKEND_DIR / "data" / "storage" / "office_hrm"

def compute_dir_hashes(directory: Path):
    """Computes SHA-256 hashes of all JSON files in the given directory."""
    hashes = {}
    for f in sorted(directory.glob("*.json")):
        content = f.read_bytes()
        hashes[f.name] = hashlib.sha256(content).hexdigest()
    return hashes

def run_task9_tests():
    print("==========================================================================")
    print("TASK 9: VERIFICATION STATUS CORRECTION & TEST DATA ISOLATION SUITE")
    print("==========================================================================")

    # -------------------------------------------------------------------------
    # 1. RECORD BASELINE CHECKSUMS OF PRODUCTION STORAGE
    # -------------------------------------------------------------------------
    print("\n[Step 1] Recording pre-test SHA-256 checksums of production database storage...")
    pre_hashes = compute_dir_hashes(PROD_STORAGE_DIR)
    print(f"  • Monitored {len(pre_hashes)} persistent production collections:")
    for fname, fhash in pre_hashes.items():
        print(f"    - {fname:25}: {fhash[:16]}...")

    # -------------------------------------------------------------------------
    # 2. VERIFY INITIAL PRODUCTION BASELINE COUNTS
    # -------------------------------------------------------------------------
    print("\n[Step 2] Verifying initial production facility & desk counts...")
    prod_rooms = json.loads((PROD_STORAGE_DIR / "facility_rooms.json").read_text(encoding="utf-8"))
    prod_seats = json.loads((PROD_STORAGE_DIR / "seating_allocations.json").read_text(encoding="utf-8"))

    v_rooms = sum(1 for r in prod_rooms if r.get("is_verified"))
    unv_rooms = sum(1 for r in prod_rooms if not r.get("is_verified"))
    conf_seats = sum(1 for s in prod_seats if s.get("is_verified"))
    prov_seats = sum(1 for s in prod_seats if not s.get("is_verified"))

    print(f"  • Production Rooms: {v_rooms} verified, {unv_rooms} unverified, {len(prod_rooms)} total")
    print(f"  • Production Desks: {conf_seats} confirmed, {prov_seats} provisional, {len(prod_seats)} total")

    assert v_rooms == 0, f"Expected 0 verified rooms, got {v_rooms}"
    assert unv_rooms == 3, f"Expected 3 unverified rooms, got {unv_rooms}"
    assert conf_seats == 0, f"Expected 0 confirmed desks, got {conf_seats}"
    assert prov_seats == 38, f"Expected 38 provisional desks, got {prov_seats}"
    print("  ✓ PASSED: Production database correctly reflects initial baseline (0 verified, 0 confirmed).")

    # -------------------------------------------------------------------------
    # 3. SET UP ISOLATED TEST APPLICATION CONTEXT
    # -------------------------------------------------------------------------
    print("\n[Step 3] Setting up isolated test application context with in-memory database...")
    os.environ["TESTING"] = "true"
    os.environ["USE_MOCK_DB"] = "true"
    os.environ["ALLOW_MOCK_FALLBACK"] = "true"

    from config import Config
    from backend.database.connection import DatabaseManager
    from backend.auth.security import generate_jwt_token
    from backend.permissions.rbac import Role
    from app import create_app

    # Create temporary isolated directory for any test artifacts
    with tempfile.TemporaryDirectory() as test_sandbox_dir:
        test_sandbox = Path(test_sandbox_dir)

        class TestConfig(Config):
            TESTING = True
            DATABASE_NAME = "office_hrm_test_isolated"
            USE_MOCK_DB = True
            USE_FILE_PERSISTENCE = False
            DATA_DIR = test_sandbox
            PERSISTENT_DATA_DIR = test_sandbox
            ENABLE_DEV_TEST_ACCOUNT = True

        app = create_app(config_class=TestConfig, start_scheduler=False)
        test_client = app.test_client()

        # Isolate database and seed synthetic test fixtures ONLY
        test_db = DatabaseManager.get_db(db_name="office_hrm_test_isolated")
        test_db.facility_rooms.delete_many({})
        test_db.seating_allocations.delete_many({})
        test_db.users.delete_many({})

        # Insert synthetic test accounts (never modify real production accounts)
        synthetic_users = [
            {"employee_id": "TEST-EMP-01", "role": Role.EMPLOYEE, "full_name": "Test Employee", "email": "testemp@aisamrat.test"},
            {"employee_id": "TEST-TL-01", "role": Role.TL, "full_name": "Test Team Lead", "email": "testtl@aisamrat.test"},
            {"employee_id": "TEST-MGR-01", "role": Role.MANAGER, "full_name": "Test Manager", "email": "testmgr@aisamrat.test"},
            {"employee_id": "TEST-HR-01", "role": Role.HR, "full_name": "Test HR Officer", "email": "testhr@aisamrat.test"},
            {"employee_id": "TEST-ADMIN-01", "role": Role.ADMIN, "full_name": "Test System Administrator", "email": "testadmin@aisamrat.test"},
        ]
        test_db.users.insert_many(synthetic_users)

        # Insert synthetic facility and seating fixtures
        test_db.facility_rooms.insert_one({
            "room_id": "TEST-ROOM-ISOLATED",
            "name": "Synthetic Lab Draft",
            "floor": "Floor B1",
            "capacity": 5,
            "features": ["Projector"],
            "is_verified": False,
            "status": "Unverified",
            "verification_status": "Unverified Baseline (Pending Campus Audit)"
        })
        test_db.seating_allocations.insert_one({
            "allocation_id": "TEST-ALLOC-ISOLATED",
            "employee_id": "TEST-EMP-01",
            "employee_name": "Test Employee",
            "desk_number": "DRAFT-DESK-01",
            "locker_number": "DRAFT-LCK-01",
            "floor": "Floor B1",
            "bay": "Test Bay",
            "is_verified": False,
            "status": "Provisional",
            "verification_status": "Provisional (Algorithmic Floor 3 Layout)"
        })

        def get_auth_header(user_dict):
            token = generate_jwt_token(user_dict)
            return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        # ---------------------------------------------------------------------
        # 4. RBAC PERMISSION RESTRICTIONS BY ROLE (DIRECT API TEST)
        # ---------------------------------------------------------------------
        print("\n[Step 4] Testing backend RBAC permission restrictions by role on API endpoints...")
        
        non_authorized_roles = [
            ("Employee", synthetic_users[0]),
            ("Team Lead", synthetic_users[1]),
            ("Manager", synthetic_users[2]),
        ]

        for role_name, user_dict in non_authorized_roles:
            hdrs = get_auth_header(user_dict)
            
            # 4.1 Room verification attempt by unauthorized role
            res_room = test_client.post("/api/facilities/rooms/TEST-ROOM-ISOLATED/verify", json={
                "name": "Hacked Room",
                "notes": "Direct API bypass attempt"
            }, headers=hdrs)
            assert res_room.status_code == 403, f"{role_name} bypassed room verification! Code: {res_room.status_code}"
            print(f"  ✓ {role_name} blocked with HTTP 403 on POST /api/facilities/rooms/<id>/verify")

            # 4.2 Seating verification attempt by unauthorized role
            res_seat = test_client.post("/api/assets/seating-lockers/TEST-ALLOC-ISOLATED/verify", json={
                "desk_number": "HACKED-01",
                "notes": "Direct API bypass attempt"
            }, headers=hdrs)
            assert res_seat.status_code == 403, f"{role_name} bypassed seating verification! Code: {res_seat.status_code}"
            print(f"  ✓ {role_name} blocked with HTTP 403 on POST /api/assets/seating-lockers/<id>/verify")

        # ---------------------------------------------------------------------
        # 5. MANDATORY VERIFICATION NOTES & DETAIL VALIDATION
        # ---------------------------------------------------------------------
        print("\n[Step 5] Testing mandatory physical audit notes and input requirements...")
        admin_hdrs = get_auth_header(synthetic_users[4]) # TEST-ADMIN-01

        # 5.1 Admin attempts room verification with empty notes
        res_empty_room_notes = test_client.post("/api/facilities/rooms/TEST-ROOM-ISOLATED/verify", json={
            "name": "Confirmed Space",
            "floor": "Floor 1",
            "capacity": 10,
            "notes": ""
        }, headers=admin_hdrs)
        assert res_empty_room_notes.status_code == 400
        assert "strictly required" in res_empty_room_notes.get_json()["error"]
        print("  ✓ Room verification without notes rejected: 400 Bad Request.")

        # 5.2 Admin attempts room verification with missing room name
        res_missing_room_name = test_client.post("/api/facilities/rooms/TEST-ROOM-ISOLATED/verify", json={
            "name": "",
            "floor": "Floor 1",
            "capacity": 10,
            "notes": "Some notes"
        }, headers=admin_hdrs)
        assert res_missing_room_name.status_code == 400
        print("  ✓ Room verification with missing name rejected: 400 Bad Request.")

        # 5.3 Admin attempts seating verification with empty notes
        res_empty_seat_notes = test_client.post("/api/assets/seating-lockers/TEST-ALLOC-ISOLATED/verify", json={
            "desk_number": "CONF-01",
            "notes": ""
        }, headers=admin_hdrs)
        assert res_empty_seat_notes.status_code == 400
        assert "strictly required" in res_empty_seat_notes.get_json()["error"]
        print("  ✓ Seating verification without notes rejected: 400 Bad Request.")

        # ---------------------------------------------------------------------
        # 6. AUTHORIZED HR / ADMIN VERIFICATION WORKFLOW (ISOLATED EXECUTION)
        # ---------------------------------------------------------------------
        print("\n[Step 6] Executing authorized verification workflow on synthetic fixtures...")

        # 6.1 Admin verifies synthetic room with complete physical evidence
        res_verify_room = test_client.post("/api/facilities/rooms/TEST-ROOM-ISOLATED/verify", json={
            "name": "Audited Innovation Suite",
            "floor": "Floor 1 — North Wing",
            "capacity": 12,
            "features": ["4K Screen", "Polycom Mic"],
            "notes": "Physically inspected and verified during campus facility audit by Administration."
        }, headers=admin_hdrs)
        assert res_verify_room.status_code == 200
        v_room = res_verify_room.get_json()["room"]
        assert v_room["is_verified"] is True
        assert v_room["status"] == "Available"
        assert v_room["verified_by_id"] == "TEST-ADMIN-01"
        assert v_room["name"] == "Audited Innovation Suite"
        print(f"  ✓ Admin verified synthetic room: '{v_room['name']}' (by {v_room['verified_by_id']})")

        # 6.2 HR verifies synthetic seating with complete physical evidence
        hr_hdrs = get_auth_header(synthetic_users[3]) # TEST-HR-01
        res_verify_seat = test_client.post("/api/assets/seating-lockers/TEST-ALLOC-ISOLATED/verify", json={
            "desk_number": "CONF-DESK-101",
            "locker_number": "CONF-LCK-101",
            "floor": "Floor 1",
            "bay": "Bay North",
            "notes": "Physically verified workstation occupancy and handed over RFID keycard."
        }, headers=hr_hdrs)
        assert res_verify_seat.status_code == 200
        v_seat = res_verify_seat.get_json()["allocation"]
        assert v_seat["is_verified"] is True
        assert v_seat["status"] == "Allocated"
        assert v_seat["verified_by_id"] == "TEST-HR-01"
        assert v_seat["desk_number"] == "CONF-DESK-101"
        print(f"  ✓ HR verified synthetic seating: desk '{v_seat['desk_number']}' (by {v_seat['verified_by_id']})")

        # ---------------------------------------------------------------------
        # 7. VERIFY TEST STORAGE VS PRODUCTION STORAGE IMMUTABILITY
        # ---------------------------------------------------------------------
        print("\n[Step 7] Proving production storage remained 100% untouched...")
        post_hashes = compute_dir_hashes(PROD_STORAGE_DIR)

        diff_files = [f for f in pre_hashes if pre_hashes.get(f) != post_hashes.get(f)]
        new_files = [f for f in post_hashes if f not in pre_hashes]
        assert pre_hashes == post_hashes, f"CRITICAL: Production storage modified in {diff_files + new_files}!"

        print("  ✓ Production file checksum verification (Pre-Test == Post-Test):")
        for fname in sorted(pre_hashes.keys()):
            assert pre_hashes[fname] == post_hashes[fname]
            print(f"    - {fname:25}: Pre={pre_hashes[fname][:12]}... == Post={post_hashes[fname][:12]}... (MATCH)")

        # Verify persistent room and seating file contents directly
        post_prod_rooms = json.loads((PROD_STORAGE_DIR / "facility_rooms.json").read_text(encoding="utf-8"))
        post_prod_seats = json.loads((PROD_STORAGE_DIR / "seating_allocations.json").read_text(encoding="utf-8"))

        assert sum(1 for r in post_prod_rooms if r.get("is_verified")) == 0
        assert sum(1 for r in post_prod_rooms if not r.get("is_verified")) == 3
        assert sum(1 for s in post_prod_seats if s.get("is_verified")) == 0
        assert sum(1 for s in post_prod_seats if not s.get("is_verified")) == 38

        print("  ✓ Production persistent records confirmed: 0 verified rooms (3 baseline), 0 confirmed desks (38 provisional).")
        print("\n==========================================================================")
        print("ALL TASK 9 TEST ISOLATION & DATA INTEGRITY TESTS PASSED 100%!")
        print("==========================================================================")

if __name__ == "__main__":
    run_task9_tests()
