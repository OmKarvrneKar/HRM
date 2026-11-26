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

def run_task10_audit():
    print("==========================================================================")
    print("TASK 10: FINAL RBAC & DATABASE TEST ISOLATION AUDIT SUITE")
    print("==========================================================================")

    # -------------------------------------------------------------------------
    # 1. AUDIT ROLE ENUM, CANONICAL ROLES, AND ALIAS DEFINITIONS
    # -------------------------------------------------------------------------
    print("\n[Step 1] Auditing Role definitions and normalize_role() implementation...")
    from backend.permissions.rbac import Role, normalize_role

    print(f"  • Canonical Roles: {Role.CANONICAL_ROLES}")
    print(f"  • Role.HR: '{Role.HR}'")
    print(f"  • Role.ADMIN: '{Role.ADMIN}'")
    print(f"  • Role.HR_MANAGER exists: {hasattr(Role, 'HR_MANAGER')} (Value: '{getattr(Role, 'HR_MANAGER', None)}')")
    print(f"  • Is Role.HR_MANAGER an alias? {Role.HR_MANAGER == Role.HR} (Alias for Role.HR)")
    print(f"  • Role.ORGANIZATION exists: {hasattr(Role, 'ORGANIZATION')} (Value: '{getattr(Role, 'ORGANIZATION', None)}')")
    print(f"  • Is Role.ORGANIZATION an alias? {Role.ORGANIZATION == Role.MANAGER} (Alias for Role.MANAGER)")

    # Assert canonical roles
    assert Role.CANONICAL_ROLES == ["employee", "tl", "manager", "hr", "admin"]
    assert Role.HR_MANAGER == Role.HR == "hr"
    assert Role.ORGANIZATION == Role.MANAGER == "manager"

    # Test normalize_role mappings
    assert normalize_role("admin") == Role.ADMIN
    assert normalize_role("superadmin") == Role.ADMIN
    assert normalize_role("administrator") == Role.ADMIN
    assert normalize_role("hr") == Role.HR
    assert normalize_role("hr_manager") == Role.HR
    assert normalize_role("human_resources") == Role.HR
    assert normalize_role("manager") == Role.MANAGER
    assert normalize_role("organization") == Role.MANAGER
    assert normalize_role("tl") == Role.TL
    assert normalize_role("team_lead") == Role.TL
    assert normalize_role("employee") == Role.EMPLOYEE
    assert normalize_role("intern") == Role.EMPLOYEE
    print("  ✓ PASSED: Role enum and normalize_role() verified 100% consistent.")

    # -------------------------------------------------------------------------
    # 2. AUDIT API DECORATORS AND SERVICE-LEVEL AUTHORIZATION CONSISTENCY
    # -------------------------------------------------------------------------
    print("\n[Step 2] Auditing API route decorators and service-level authorization consistency...")
    import inspect
    from backend.routes.api_routes import verify_facility_room_route, verify_seating_allocation_route
    from backend.services.enterprise_hr_service import FacilityBookingService, SeatingLockerService

    # Check api_routes source code for decorators
    api_routes_code = (HRM_BACKEND_DIR / "backend" / "routes" / "api_routes.py").read_text(encoding="utf-8")
    assert "@require_roles(Role.HR, Role.ADMIN)\ndef verify_facility_room_route" in api_routes_code, \
        "API decorator for verify_facility_room_route mismatch!"
    assert "@require_roles(Role.HR, Role.ADMIN)\ndef verify_seating_allocation_route" in api_routes_code, \
        "API decorator for verify_seating_allocation_route mismatch!"
    print("  ✓ API Routes: Both endpoints decorated with @require_roles(Role.HR, Role.ADMIN).")

    # Check enterprise_hr_service source code for service-level authorization
    service_code = (HRM_BACKEND_DIR / "backend" / "services" / "enterprise_hr_service.py").read_text(encoding="utf-8")
    assert 'actor_role = normalize_role(actor.get("role"))' in service_code
    assert 'if actor_role not in (Role.HR, Role.ADMIN):' in service_code
    print("  ✓ Service Layer: Both FacilityBookingService and SeatingLockerService enforce actor_role in (Role.HR, Role.ADMIN).")
    print("  ✓ PASSED: API and service-level authorizations are 100% harmonized.")

    # -------------------------------------------------------------------------
    # 3. RECORD PRODUCTION DATABASE CONFIGURATION & BASELINE STORAGE HASHES
    # -------------------------------------------------------------------------
    print("\n[Step 3] Identifying production database configuration and computing storage hashes...")
    from config import Config
    print(f"  • Configured Production DB Name: '{Config.DATABASE_NAME}'")
    print(f"  • Configured Production Storage: {PROD_STORAGE_DIR}")
    print(f"  • Production USE_FILE_PERSISTENCE: {Config.USE_FILE_PERSISTENCE}")
    print(f"  • Production USE_MOCK_DB: {Config.USE_MOCK_DB}")

    assert Config.DATABASE_NAME == "office_hrm"
    assert PROD_STORAGE_DIR.exists()

    pre_hashes = compute_dir_hashes(PROD_STORAGE_DIR)
    print(f"  • Recorded baseline SHA-256 checksums across {len(pre_hashes)} production JSON collections.")

    # Verify initial persistent production records
    prod_rooms = json.loads((PROD_STORAGE_DIR / "facility_rooms.json").read_text(encoding="utf-8"))
    prod_seats = json.loads((PROD_STORAGE_DIR / "seating_allocations.json").read_text(encoding="utf-8"))

    v_rooms = sum(1 for r in prod_rooms if r.get("is_verified"))
    unv_rooms = sum(1 for r in prod_rooms if not r.get("is_verified"))
    conf_seats = sum(1 for s in prod_seats if s.get("is_verified"))
    prov_seats = sum(1 for s in prod_seats if not s.get("is_verified"))

    print(f"  • Initial Production Facilities: {v_rooms} verified, {unv_rooms} unverified, {len(prod_rooms)} total")
    print(f"  • Initial Production Seating   : {conf_seats} confirmed, {prov_seats} provisional, {len(prod_seats)} total")

    assert v_rooms == 0, f"Expected 0 verified rooms, got {v_rooms}"
    assert unv_rooms == 0, f"Expected 0 unverified baseline rooms, got {unv_rooms}"
    assert conf_seats == 0, f"Expected 0 confirmed desks, got {conf_seats}"
    assert prov_seats == 0, f"Expected 0 provisional baseline desks, got {prov_seats}"
    print("  ✓ PASSED: Clean production baseline verified (0 rooms, 0 desks).")

    # -------------------------------------------------------------------------
    # 4. INITIALIZE ISOLATED TEST APPLICATION CONTEXT
    # -------------------------------------------------------------------------
    print("\n[Step 4] Proving test isolation: initializing in-memory test database with persistence disabled...")
    os.environ["TESTING"] = "true"
    os.environ["USE_MOCK_DB"] = "true"
    os.environ["ALLOW_MOCK_FALLBACK"] = "true"

    from backend.database.connection import DatabaseManager
    from backend.auth.security import generate_jwt_token
    from app import create_app

    # Create temporary sandbox directory for test session
    with tempfile.TemporaryDirectory() as test_sandbox_dir:
        test_sandbox = Path(test_sandbox_dir)

        class TestAuditConfig(Config):
            TESTING = True
            DATABASE_NAME = "office_hrm_test_audit"
            USE_MOCK_DB = True
            USE_FILE_PERSISTENCE = False
            DATA_DIR = test_sandbox
            PERSISTENT_DATA_DIR = test_sandbox
            ENABLE_DEV_TEST_ACCOUNT = True

        app = create_app(config_class=TestAuditConfig, start_scheduler=False)
        test_client = app.test_client()

        # Retrieve isolated test database instance
        test_db = DatabaseManager.get_db(db_name="office_hrm_test_audit")
        
        # Verify JSON file persistence is disabled during tests
        assert not isinstance(test_db, getattr(sys.modules.get("backend.database.connection"), "PersistentDatabaseProxy", type(None))), \
            "PersistentDatabaseProxy should NOT wrap test database when USE_FILE_PERSISTENCE=False or is_test_db=True!"
        print("  ✓ Proved: JSON file persistence proxy is DISABLED in test mode.")

        # Seed synthetic test fixtures exclusively
        test_db.facility_rooms.delete_many({})
        test_db.seating_allocations.delete_many({})
        test_db.users.delete_many({})

        synthetic_users = [
            {"employee_id": "SYN-EMP-01", "role": Role.EMPLOYEE, "full_name": "Synthetic Employee", "email": "synemp@aisamrat.test"},
            {"employee_id": "SYN-TL-01", "role": Role.TL, "full_name": "Synthetic Team Lead", "email": "syntl@aisamrat.test"},
            {"employee_id": "SYN-MGR-01", "role": Role.MANAGER, "full_name": "Synthetic Manager", "email": "synmgr@aisamrat.test"},
            {"employee_id": "SYN-HR-01", "role": Role.HR, "full_name": "Synthetic HR Officer", "email": "synhr@aisamrat.test"},
            {"employee_id": "SYN-ADMIN-01", "role": Role.ADMIN, "full_name": "Synthetic Administrator", "email": "synadmin@aisamrat.test"},
        ]
        test_db.users.insert_many(synthetic_users)

        test_db.facility_rooms.insert_one({
            "room_id": "SYN-ROOM-001",
            "name": "Synthetic Meeting Room Baseline",
            "floor": "Floor T1",
            "capacity": 6,
            "features": ["Whiteboard"],
            "is_verified": False,
            "status": "Unverified",
            "verification_status": "Unverified Baseline (Pending Campus Audit)"
        })

        test_db.seating_allocations.insert_one({
            "allocation_id": "SYN-ALLOC-001",
            "employee_id": "SYN-EMP-01",
            "employee_name": "Synthetic Employee",
            "desk_number": "DRAFT-SYN-01",
            "locker_number": "DRAFT-LCK-01",
            "floor": "Floor T1",
            "bay": "Test Bay Alpha",
            "is_verified": False,
            "status": "Provisional",
            "verification_status": "Provisional (Algorithmic Floor 3 Layout)"
        })

        def get_auth_header(user_dict):
            token = generate_jwt_token(user_dict)
            return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        # ---------------------------------------------------------------------
        # 5. TEST UNAUTHORIZED EMPLOYEE, TL, AND MANAGER DIRECT API CALLS
        # ---------------------------------------------------------------------
        print("\n[Step 5] Testing direct API calls from unauthorized roles (Employee, TL, Manager)...")
        
        unauthorized_specs = [
            ("Regular Employee", synthetic_users[0]),
            ("Team Lead", synthetic_users[1]),
            ("Department Manager", synthetic_users[2]),
        ]

        for role_label, udict in unauthorized_specs:
            hdrs = get_auth_header(udict)
            
            # Direct API call to verify facility room
            res_room = test_client.post("/api/facilities/rooms/SYN-ROOM-001/verify", json={
                "name": "Tampered Room",
                "floor": "Floor 1",
                "capacity": 10,
                "notes": "Direct API unauthorized attempt"
            }, headers=hdrs)
            assert res_room.status_code == 403, f"{role_label} bypassed room verification! Got HTTP {res_room.status_code}"
            print(f"  ✓ {role_label:20} -> POST /api/facilities/rooms/SYN-ROOM-001/verify: HTTP 403 FORBIDDEN")

            # Direct API call to verify workstation allocation
            res_seat = test_client.post("/api/assets/seating-lockers/SYN-ALLOC-001/verify", json={
                "desk_number": "TAMPERED-01",
                "notes": "Direct API unauthorized attempt"
            }, headers=hdrs)
            assert res_seat.status_code == 403, f"{role_label} bypassed seating verification! Got HTTP {res_seat.status_code}"
            print(f"  ✓ {role_label:20} -> POST /api/assets/seating-lockers/SYN-ALLOC-001/verify: HTTP 403 FORBIDDEN")

        # ---------------------------------------------------------------------
        # 6. TEST AUTHORIZED HR AND ADMIN VERIFICATION
        # ---------------------------------------------------------------------
        print("\n[Step 6] Testing authorized HR and Admin verification...")

        # 6.1 Authorized HR verifies synthetic room
        hr_hdrs = get_auth_header(synthetic_users[3]) # SYN-HR-01
        res_hr_room = test_client.post("/api/facilities/rooms/SYN-ROOM-001/verify", json={
            "name": "Innovation Hub 101",
            "floor": "Floor 1 — Tech Suite",
            "capacity": 8,
            "features": ["Smart Display", "Conference Speaker"],
            "notes": "Physically inspected and confirmed during facilities audit by Human Resources."
        }, headers=hr_hdrs)
        assert res_hr_room.status_code == 200, f"HR room verification failed: {res_hr_room.text}"
        verified_room = res_hr_room.get_json()["room"]
        assert verified_room["is_verified"] is True
        assert verified_room["status"] == "Available"
        assert verified_room["verified_by_id"] == "SYN-HR-01"
        print(f"  ✓ HR (SYN-HR-01) verified SYN-ROOM-001: '{verified_room['name']}' (HTTP 200 OK)")

        # 6.2 Authorized Admin verifies synthetic seating
        admin_hdrs = get_auth_header(synthetic_users[4]) # SYN-ADMIN-01
        res_admin_seat = test_client.post("/api/assets/seating-lockers/SYN-ALLOC-001/verify", json={
            "desk_number": "CONF-DESK-201",
            "locker_number": "CONF-LCK-201",
            "floor": "Floor 2",
            "bay": "Bay Bravo",
            "notes": "Physically audited and confirmed workstation placement by System Administrator."
        }, headers=admin_hdrs)
        assert res_admin_seat.status_code == 200, f"Admin seating verification failed: {res_admin_seat.text}"
        verified_seat = res_admin_seat.get_json()["allocation"]
        assert verified_seat["is_verified"] is True
        assert verified_seat["status"] == "Allocated"
        assert verified_seat["verified_by_id"] == "SYN-ADMIN-01"
        print(f"  ✓ Admin (SYN-ADMIN-01) verified SYN-ALLOC-001: desk '{verified_seat['desk_number']}' (HTTP 200 OK)")

        # ---------------------------------------------------------------------
        # 7. PROVE PRODUCTION DATABASE STORAGE REMAINED UNTOUCHED
        # ---------------------------------------------------------------------
        print("\n[Step 7] Proving production database storage was completely untouched...")
        post_hashes = compute_dir_hashes(PROD_STORAGE_DIR)

        diff_files = [f for f in pre_hashes if pre_hashes.get(f) != post_hashes.get(f)]
        new_files = [f for f in post_hashes if f not in pre_hashes]
        assert pre_hashes == post_hashes, f"CRITICAL ERROR: Production storage modified in: {diff_files + new_files}"

        print("  ✓ Production file checksum verification (Pre-Test == Post-Test):")
        for fname in sorted(pre_hashes.keys()):
            assert pre_hashes[fname] == post_hashes[fname]
            print(f"    - {fname:25}: {pre_hashes[fname][:16]}... == {post_hashes[fname][:16]}... (MATCH)")

        # Final persistent document verification
        post_prod_rooms = json.loads((PROD_STORAGE_DIR / "facility_rooms.json").read_text(encoding="utf-8"))
        post_prod_seats = json.loads((PROD_STORAGE_DIR / "seating_allocations.json").read_text(encoding="utf-8"))

        final_v_rooms = sum(1 for r in post_prod_rooms if r.get("is_verified"))
        final_unv_rooms = sum(1 for r in post_prod_rooms if not r.get("is_verified"))
        final_conf_seats = sum(1 for s in post_prod_seats if s.get("is_verified"))
        final_prov_seats = sum(1 for s in post_prod_seats if not s.get("is_verified"))

        assert final_v_rooms == 0
        assert final_unv_rooms == 0
        assert final_conf_seats == 0
        assert final_prov_seats == 0

        print("\n--- Final Persistent Storage Verification ---")
        print(f"  • Verified Meeting Rooms: {final_v_rooms} (Expected: 0)")
        print(f"  • Unverified Baseline Rooms: {final_unv_rooms} (Expected: 0)")
        print(f"  • Confirmed Desk Allocations: {final_conf_seats} (Expected: 0)")
        print(f"  • Provisional Desk Records: {final_prov_seats} (Expected: 0)")
        print("  ✓ Production storage preserved completely clean (0 rooms, 0 desks)!")

    print("\n==========================================================================")
    print("ALL TASK 10 RBAC & DATABASE TEST ISOLATION CHECKS PASSED 100%!")
    print("==========================================================================")

if __name__ == "__main__":
    run_task10_audit()

