import hashlib
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from auth.security import generate_jwt_token, hash_password
from database.connection import DatabaseManager, PersistentDatabaseProxy
from database.seeds import seed_real_and_dummy_users
from permissions.rbac import Role
from services.enterprise_hr_service import FacilityBookingService, SeatingLockerService
from config import Config, TestConfig


PROD_STORAGE_DIR = Path(__file__).resolve().parents[2] / "data" / "storage" / "office_hrm"


def _auth(user: dict) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {generate_jwt_token(user)}",
        "Content-Type": "application/json",
    }


def _prod_hashes() -> dict[str, str]:
    return {
        f.name: hashlib.sha256(f.read_bytes()).hexdigest()
        for f in sorted(PROD_STORAGE_DIR.glob("*.json"))
    }


@pytest.fixture
def isolated_facility_actors(app, db):
    assert app.config.get("TESTING") is True
    assert db.name == TestConfig.DATABASE_NAME
    for col in ("facility_rooms", "facility_bookings", "seating_allocations", "hardware_assets", "software_licenses", "asset_requests"):
        db[col].delete_many({})

    now = datetime.now(timezone.utc)
    actors = {
        "emp": {
            "employee_id": "SYN-FAC-EMP",
            "emp_id": "SYN-FAC-EMP",
            "full_name": "Synthetic Facility Employee",
            "email": "syn.fac.emp@test.local",
            "password_hash": hash_password("TestPass@123"),
            "role": Role.EMPLOYEE,
            "department": "Engineering",
            "is_active": True,
            "status": "active",
            "created_at": now,
        },
        "emp2": {
            "employee_id": "SYN-FAC-EMP2",
            "emp_id": "SYN-FAC-EMP2",
            "full_name": "Synthetic Facility Employee Two",
            "email": "syn.fac.emp2@test.local",
            "password_hash": hash_password("TestPass@123"),
            "role": Role.EMPLOYEE,
            "department": "Engineering",
            "is_active": True,
            "status": "active",
            "created_at": now,
        },
        "tl": {
            "employee_id": "SYN-FAC-TL",
            "emp_id": "SYN-FAC-TL",
            "full_name": "Synthetic Facility Lead",
            "email": "syn.fac.tl@test.local",
            "password_hash": hash_password("TestPass@123"),
            "role": Role.TL,
            "department": "Engineering",
            "is_active": True,
            "status": "active",
            "created_at": now,
        },
        "mgr": {
            "employee_id": "SYN-FAC-MGR",
            "emp_id": "SYN-FAC-MGR",
            "full_name": "Synthetic Facility Manager",
            "email": "syn.fac.mgr@test.local",
            "password_hash": hash_password("TestPass@123"),
            "role": Role.MANAGER,
            "department": "Engineering",
            "is_active": True,
            "status": "active",
            "created_at": now,
        },
        "hr": {
            "employee_id": "SYN-FAC-HR",
            "emp_id": "SYN-FAC-HR",
            "full_name": "Synthetic Facility HR",
            "email": "syn.fac.hr@test.local",
            "password_hash": hash_password("TestPass@123"),
            "role": Role.HR,
            "department": "Human Resources",
            "is_active": True,
            "status": "active",
            "created_at": now,
        },
        "admin": {
            "employee_id": "SYN-FAC-ADM",
            "emp_id": "SYN-FAC-ADM",
            "full_name": "Synthetic Facility Admin",
            "email": "syn.fac.adm@test.local",
            "password_hash": hash_password("TestPass@123"),
            "role": Role.ADMIN,
            "department": "Administration",
            "is_active": True,
            "status": "active",
            "created_at": now,
        },
    }
    for key, u in actors.items():
        res = db.users.insert_one(u)
        u["_id"] = res.inserted_id
    return actors


def test_production_storage_and_seed_have_zero_fabricated_facilities_and_desks(db):
    """Verify production JSONs are empty for facilities/desks and seeder does not fabricate any."""
    rooms = json.loads((PROD_STORAGE_DIR / "facility_rooms.json").read_text(encoding="utf-8"))
    seats = json.loads((PROD_STORAGE_DIR / "seating_allocations.json").read_text(encoding="utf-8"))
    prod_users = json.loads((PROD_STORAGE_DIR / "users.json").read_text(encoding="utf-8"))

    assert rooms == []
    assert seats == []
    assert len(prod_users) >= 38

    assert not hasattr(SeatingLockerService, "seed_seating_allocations_if_empty")
    assert not hasattr(FacilityBookingService, "PREDEFINED_ROOMS")

    db.facility_rooms.delete_many({})
    db.seating_allocations.delete_many({})
    seed_real_and_dummy_users(db)

    assert db.facility_rooms.count_documents({}) == 0
    assert db.seating_allocations.count_documents({}) == 0


def test_empty_state_no_defaults_and_verified_creation_across_admin_and_employee(client, db, isolated_facility_actors):
    """Verify empty initial state, rejection of fabricated defaults, RBAC, and Admin/Employee consistency."""
    pre_hashes = _prod_hashes()

    emp = isolated_facility_actors["emp"]
    emp2 = isolated_facility_actors["emp2"]
    tl = isolated_facility_actors["tl"]
    mgr = isolated_facility_actors["mgr"]
    hr = isolated_facility_actors["hr"]
    admin = isolated_facility_actors["admin"]

    # 1. Empty state for both Admin and Employee
    for caller in (admin, emp):
        r_res = client.get("/api/facilities/rooms", headers=_auth(caller))
        assert r_res.status_code == 200
        r_data = r_res.get_json()
        assert r_data["rooms"] == []
        assert r_data["verified_rooms_count"] == 0
        assert r_data["total_rooms"] == 0

        s_res = client.get("/api/assets/seating-lockers", headers=_auth(caller))
        assert s_res.status_code == 200
        s_data = s_res.get_json()
        assert s_data["my_seating"] is None
        assert s_data["all_allocations"] == []
        assert s_data["total_records"] == 0

    # 2. Unauthorized roles cannot create/verify/delete rooms or allocate/verify seating
    for blocked in (emp, tl, mgr):
        assert client.post("/api/facilities/rooms", headers=_auth(blocked), json={
            "name": "Hack Room", "floor": "Floor 1", "capacity": 5, "notes": "Bypass"
        }).status_code == 403
        assert client.post("/api/assets/seating-lockers/allocate", headers=_auth(blocked), json={
            "employee_id": "SYN-FAC-EMP", "floor": "F1", "bay": "B1", "desk_number": "D1", "notes": "Bypass"
        }).status_code == 403

    # 3. Missing genuine specs or missing physical verification notes must be rejected (no defaults invented)
    assert client.post("/api/facilities/rooms", headers=_auth(admin), json={"name": "Partial Room"}).status_code == 400
    assert client.post("/api/facilities/rooms", headers=_auth(admin), json={
        "name": "Partial Room", "floor": "1st Floor", "capacity": 10
    }).status_code == 400  # Missing verification notes
    assert client.post("/api/assets/seating-lockers/allocate", headers=_auth(admin), json={
        "employee_id": "SYN-FAC-EMP"
    }).status_code == 400
    assert client.post("/api/assets/seating-lockers/allocate", headers=_auth(admin), json={
        "employee_id": "SYN-FAC-EMP", "floor": "2nd Floor", "bay": "West Wing", "desk_number": "WKS-201"
    }).status_code == 400  # Missing verification notes

    # 4. Admin creates a genuine verified meeting room (no invented amenities when omitted)
    room_res = client.post("/api/facilities/rooms", headers=_auth(admin), json={
        "name": "Conference Suite Alpha",
        "floor": "2nd Floor East Wing",
        "capacity": 12,
        "notes": "Verified by campus ops inspection 2026-11-26"
    })
    assert room_res.status_code == 201
    room = room_res.get_json()["room"]
    assert room["is_verified"] is True
    assert room["features"] == []
    assert room["verified_by_id"] == "SYN-FAC-ADM"

    # Admin assigns & verifies genuine workstation for emp (not emp2)
    seat_res = client.post("/api/assets/seating-lockers/allocate", headers=_auth(admin), json={
        "employee_id": "SYN-FAC-EMP",
        "floor": "2nd Floor",
        "bay": "North Pod",
        "desk_number": "WKS-204",
        "locker_number": "LCK-204",
        "notes": "Physical walk-through confirmation 2026-11-26"
    })
    assert seat_res.status_code == 200
    alloc = seat_res.get_json()["allocation"]
    assert alloc["is_verified"] is True
    assert alloc["desk_number"] == "WKS-204"
    assert alloc["locker_number"] == "LCK-204"
    assert alloc["amenities"] == ""  # Never auto-invented

    # 5. Admin & Employee see consistent real data with appropriate scoping
    adm_rooms = client.get("/api/facilities/rooms", headers=_auth(admin)).get_json()["rooms"]
    emp_rooms = client.get("/api/facilities/rooms", headers=_auth(emp)).get_json()["rooms"]
    assert len(adm_rooms) == 1 and len(emp_rooms) == 1
    assert emp_rooms[0]["room_id"] == room["room_id"]

    adm_seat = client.get("/api/assets/seating-lockers", headers=_auth(admin)).get_json()
    assert len(adm_seat["all_allocations"]) == 1
    assert adm_seat["confirmed_allocated"] == 1

    emp1_seat = client.get("/api/assets/seating-lockers", headers=_auth(emp)).get_json()
    assert emp1_seat["all_allocations"] == []
    assert emp1_seat["my_seating"]["desk_number"] == "WKS-204"

    # Second employee without assignment sees empty my_seating and empty all_allocations
    emp2_seat = client.get("/api/assets/seating-lockers", headers=_auth(emp2)).get_json()
    assert emp2_seat["all_allocations"] == []
    assert emp2_seat["my_seating"] is None

    # Unverified rooms cannot be booked; verified rooms can be booked
    db.facility_rooms.insert_one({"room_id": "UNV-R1", "name": "Draft", "is_verified": False})
    assert client.post("/api/facilities/book", headers=_auth(emp), json={
        "room_id": "UNV-R1", "booking_date": "2026-12-01", "start_time": "10:00", "end_time": "11:00", "title": "Sync"
    }).status_code == 400
    assert client.post("/api/facilities/book", headers=_auth(emp), json={
        "room_id": room["room_id"], "booking_date": "2026-12-01", "start_time": "10:00", "end_time": "11:00", "title": "Sync"
    }).status_code == 201

    # Employee cannot delete room; HR/Admin can delete room
    assert client.delete(f"/api/facilities/rooms/{room['room_id']}", headers=_auth(emp)).status_code == 403
    assert client.delete(f"/api/facilities/rooms/{room['room_id']}", headers=_auth(hr)).status_code == 200

    assert _prod_hashes() == pre_hashes


def test_disk_persistence_across_reload_in_sandbox(monkeypatch):
    """Prove room and desk writes persist cleanly across storage reload without seeding baselines."""
    with tempfile.TemporaryDirectory() as tmp:
        data_dir = Path(tmp)
        from app import create_app
        from config import Config

        monkeypatch.setenv("TESTING", "false")
        monkeypatch.setattr(Config, "TESTING", False, raising=False)
        monkeypatch.setattr(Config, "DATABASE_NAME", "office_hrm_persist_check", raising=False)
        monkeypatch.setattr(Config, "USE_MOCK_DB", True, raising=False)
        monkeypatch.setattr(Config, "USE_FILE_PERSISTENCE", True, raising=False)
        monkeypatch.setattr(Config, "DATA_DIR", data_dir, raising=False)
        monkeypatch.setattr(Config, "PERSISTENT_DATA_DIR", data_dir, raising=False)
        monkeypatch.setattr(Config, "ENABLE_DEV_TEST_ACCOUNT", False, raising=False)

        class SandboxPersistConfig(Config):
            TESTING = False
            DATABASE_NAME = "office_hrm_persist_check"
            USE_MOCK_DB = True
            USE_FILE_PERSISTENCE = True
            DATA_DIR = data_dir
            PERSISTENT_DATA_DIR = data_dir
            ENABLE_DEV_TEST_ACCOUNT = False

        orig_db = DatabaseManager._db
        orig_client = DatabaseManager._client
        orig_data_dir = DatabaseManager._data_dir
        try:
            DatabaseManager._db = None
            DatabaseManager._client = None
            DatabaseManager._data_dir = None
            app1 = create_app(config_class=SandboxPersistConfig, start_scheduler=False)
            c1 = app1.test_client()
            db1 = DatabaseManager.get_db("office_hrm_persist_check")
            assert isinstance(db1, PersistentDatabaseProxy)
            assert db1.facility_rooms.count_documents({}) == 0
            assert db1.seating_allocations.count_documents({}) == 0

            adm = db1.users.find_one({"role": Role.ADMIN})
            emp = db1.users.find_one({"role": Role.EMPLOYEE})
            assert adm and emp

            r_res = c1.post("/api/facilities/rooms", headers=_auth(adm), json={
                "name": "Boardroom One",
                "floor": "Floor 1",
                "capacity": 6,
                "notes": "Confirmed floor check"
            })
            assert r_res.status_code == 201

            s_res = c1.post("/api/assets/seating-lockers/allocate", headers=_auth(adm), json={
                "employee_id": emp.get("employee_id") or emp.get("emp_id"),
                "floor": "Floor 1",
                "bay": "Pod A",
                "desk_number": "WKS-10",
                "notes": "Confirmed seat check"
            })
            assert s_res.status_code == 200

            # Simulate server restart by resetting singleton and reloading from disk JSON storage
            DatabaseManager._db = None
            DatabaseManager._client = None
            DatabaseManager._data_dir = None
            app2 = create_app(config_class=SandboxPersistConfig, start_scheduler=False)
            c2 = app2.test_client()
            rooms_after = c2.get("/api/facilities/rooms", headers=_auth(emp)).get_json()["rooms"]
            seat_after = c2.get("/api/assets/seating-lockers", headers=_auth(emp)).get_json()
            assert len(rooms_after) == 1
            assert rooms_after[0]["name"] == "Boardroom One"
            assert seat_after["my_seating"]["desk_number"] == "WKS-10"
        finally:
            DatabaseManager._db = orig_db
            DatabaseManager._client = orig_client
            DatabaseManager._data_dir = orig_data_dir

