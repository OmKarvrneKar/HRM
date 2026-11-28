import json
from datetime import datetime, timezone
from pathlib import Path

from auth.security import generate_jwt_token, hash_password
from permissions.rbac import Role
from config import Config, TestConfig


PROD_STORAGE_DIR = Path(__file__).resolve().parents[2] / "data" / "storage" / "office_hrm"
ASSETS_JSX_PATH = Path(__file__).resolve().parents[3] / "frontend" / "src" / "features" / "enterprise" / "AssetsInventory.jsx"


def _auth(user: dict) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {generate_jwt_token(user)}",
        "Content-Type": "application/json",
    }


def test_default_data_dir_points_to_workspace_and_storages_are_clean():
    """Config default storage points into workspace data/storage and production JSONs stay clean."""
    expected_default = (Path(Config.BASE_DIR) / "data" / "storage").resolve()
    assert Path(Config.DEFAULT_DATA_DIR).resolve() == expected_default

    for col_file in ("facility_rooms.json", "seating_allocations.json", "hardware_assets.json", "software_licenses.json", "asset_requests.json"):
        assert json.loads((PROD_STORAGE_DIR / col_file).read_text(encoding="utf-8")) == []

    prod_users = json.loads((PROD_STORAGE_DIR / "users.json").read_text(encoding="utf-8"))
    assert len(prod_users) == 50


def test_api_filters_out_unverified_baseline_rooms_and_38_provisional_desks(client, db):
    """Even if legacy unverified baseline drafts exist in DB, API returns only verified records."""
    assert db.name == TestConfig.DATABASE_NAME
    for col in ("users", "facility_rooms", "seating_allocations", "hardware_assets", "software_licenses"):
        db[col].delete_many({})

    now = datetime.now(timezone.utc)
    admin = {
        "employee_id": "SYN-T13-ADM",
        "emp_id": "SYN-T13-ADM",
        "full_name": "Task13 Admin",
        "email": "t13.adm@test.local",
        "password_hash": hash_password("TestPass@123"),
        "role": Role.ADMIN,
        "is_active": True,
        "status": "active",
        "created_at": now,
    }
    emp = {
        "employee_id": "SYN-T13-EMP",
        "emp_id": "SYN-T13-EMP",
        "full_name": "Task13 Employee",
        "email": "t13.emp@test.local",
        "password_hash": hash_password("TestPass@123"),
        "role": Role.EMPLOYEE,
        "is_active": True,
        "status": "active",
        "created_at": now,
    }
    db.users.insert_many([admin, emp])

    # Insert 3 unverified baseline room templates + 38 provisional seating layouts + unverified assets
    db.facility_rooms.insert_many([
        {"room_id": "ROOM-MANTHAN", "name": "Manthan Executive Boardroom", "floor": "Floor 1", "capacity": 14, "is_verified": False},
        {"room_id": "ROOM-GURUKOOL", "name": "Gurukool Technical Lab", "floor": "Floor 2", "capacity": 20, "is_verified": False},
        {"room_id": "ROOM-SAMVAAD", "name": "Samvaad Agile Huddle Room", "floor": "Floor 3", "capacity": 8, "is_verified": False},
    ])
    db.seating_allocations.insert_many([
        {
            "allocation_id": f"SL-SYN-{i}",
            "employee_id": "SYN-T13-EMP" if i == 0 else f"SYN-T13-E{i}",
            "employee_name": "Synthetic Layout",
            "desk_number": f"FL3-A-{i:02d}",
            "locker_number": f"LCK-{300 + i}",
            "floor": "Floor 3 — AI & Engineering Hub",
            "bay": "Bay A",
            "is_verified": False,
            "status": "Provisional",
            "allocation_type": "Algorithmic Baseline",
        }
        for i in range(38)
    ])
    db.hardware_assets.insert_one({"asset_tag": "DUMMY-HW-1", "model": "Legacy", "is_verified": False})
    db.software_licenses.insert_one({"license_id": "DUMMY-SW-1", "software_name": "Legacy", "is_verified": False})

    # Both Admin and Employee receive 0 rooms, 0 desks, 0 hardware, 0 software
    for caller in (admin, emp):
        r_data = client.get("/api/facilities/rooms", headers=_auth(caller)).get_json()
        assert r_data["rooms"] == []
        assert r_data["verified_rooms_count"] == 0
        assert r_data["unverified_rooms_count"] == 0
        assert r_data["total_rooms"] == 0

        s_data = client.get("/api/assets/seating-lockers", headers=_auth(caller)).get_json()
        assert s_data["all_allocations"] == []
        assert s_data["my_seating"] is None
        assert s_data["confirmed_allocated"] == 0
        assert s_data["provisional_allocated"] == 0

        inv_data = client.get("/api/assets/inventory", headers=_auth(caller)).get_json()
        assert inv_data["hardware"] == []
        assert inv_data["software"] == []
        assert inv_data["seating_allocations"] == []

    # When Admin creates a genuine verified room & workstation, both appear cleanly without leaking drafts
    room_res = client.post("/api/facilities/rooms", headers=_auth(admin), json={
        "name": "Verified Review Room",
        "floor": "Floor 1",
        "capacity": 6,
        "notes": "Physical walkthrough 2026-11-26",
    })
    assert room_res.status_code == 201

    seat_res = client.post("/api/assets/seating-lockers/allocate", headers=_auth(admin), json={
        "employee_id": "SYN-T13-EMP",
        "floor": "Floor 1",
        "bay": "North Wing",
        "desk_number": "DESK-01",
        "notes": "Physical assignment confirmation 2026-11-26",
    })
    assert seat_res.status_code == 200

    adm_rooms = client.get("/api/facilities/rooms", headers=_auth(admin)).get_json()["rooms"]
    assert len(adm_rooms) == 1 and adm_rooms[0]["name"] == "Verified Review Room"

    adm_seat = client.get("/api/assets/seating-lockers", headers=_auth(admin)).get_json()
    assert len(adm_seat["all_allocations"]) == 1 and adm_seat["all_allocations"][0]["desk_number"] == "DESK-01"

    emp_seat = client.get("/api/assets/seating-lockers", headers=_auth(emp)).get_json()
    assert emp_seat["all_allocations"] == []
    assert emp_seat["my_seating"]["desk_number"] == "DESK-01"


def test_react_ui_removes_unverified_draft_sections_and_placeholders():
    """Production React AssetsInventory UI contains no unverified draft rendering or fake placeholders."""
    src = ASSETS_JSX_PATH.read_text(encoding="utf-8")
    for forbidden in (
        "Unverified Facility Drafts",
        "provisionalSeating",
        "unverifiedRooms",
        "Pending Physical Audit",
        "Unverified Baseline",
        "e.g. LCK-101",
        "e.g. WKS-101",
        "e.g. Bay North",
        "e.g. 2nd Floor",
    ):
        assert forbidden not in src

