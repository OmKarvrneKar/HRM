import json
from pathlib import Path

STORAGE_DIR = Path("HRM-main/data/storage/office_hrm")

def revert_claims():
    print("=== Reverting Task 8 Test Claims on Persistent Storage ===")
    
    # 1. Revert facility_rooms.json
    rooms_file = STORAGE_DIR / "facility_rooms.json"
    rooms = json.loads(rooms_file.read_text(encoding="utf-8"))
    
    reverted_rooms = []
    for r in rooms:
        r["is_verified"] = False
        r["status"] = "Unverified"
        r["verification_status"] = "Unverified Baseline (Pending Campus Audit)"
        # Remove any verification audit fields
        r.pop("verified_by_id", None)
        r.pop("verified_by_name", None)
        r.pop("verified_at", None)
        r.pop("verification_notes", None)
        reverted_rooms.append(r)
        print(f"  • Room {r.get('room_id')}: status={r.get('status')}, is_verified={r.get('is_verified')}")
        
    rooms_file.write_text(json.dumps(reverted_rooms, indent=2), encoding="utf-8")
    print(f"✓ Successfully reverted {len(reverted_rooms)} facility rooms in {rooms_file}")

    # 2. Revert seating_allocations.json
    seating_file = STORAGE_DIR / "seating_allocations.json"
    allocs = json.loads(seating_file.read_text(encoding="utf-8"))
    
    reverted_allocs = []
    reverted_count = 0
    for a in allocs:
        was_verified = a.get("is_verified", False)
        a["is_verified"] = False
        a["status"] = "Provisional"
        a["verification_status"] = "Provisional (Algorithmic Floor 3 Layout)"
        a["allocation_type"] = "Algorithmic Baseline Layout (Pending Physical Confirmation)"
        # Remove any verification audit fields
        a.pop("verified_by_id", None)
        a.pop("verified_by_name", None)
        a.pop("verified_at", None)
        a.pop("verification_notes", None)
        reverted_allocs.append(a)
        if was_verified:
            reverted_count += 1
            print(f"  • Reverted false verification on allocation {a.get('allocation_id')} ({a.get('employee_name')})")

    seating_file.write_text(json.dumps(reverted_allocs, indent=2), encoding="utf-8")
    print(f"✓ Successfully reverted {reverted_count} falsely verified seating allocations ({len(reverted_allocs)} total records) in {seating_file}")

    # 3. Final verification of baseline state
    verified_rooms = sum(1 for r in reverted_rooms if r.get("is_verified"))
    unverified_rooms = sum(1 for r in reverted_rooms if not r.get("is_verified"))
    confirmed_desks = sum(1 for a in reverted_allocs if a.get("is_verified"))
    provisional_desks = sum(1 for a in reverted_allocs if not a.get("is_verified"))

    print("\n--- Final Persistent Storage Verification ---")
    print(f"  • Verified Meeting Rooms: {verified_rooms} (Expected: 0)")
    print(f"  • Unverified Baseline Rooms: {unverified_rooms} (Expected: 3)")
    print(f"  • Confirmed Desk Allocations: {confirmed_desks} (Expected: 0)")
    print(f"  • Provisional Desk Records: {provisional_desks} (Expected: 38)")

    assert verified_rooms == 0
    assert unverified_rooms == 3
    assert confirmed_desks == 0
    assert provisional_desks == 38
    print("✓ PERSISTENT STORAGE INITIAL BASELINE RESTORED 100% SUCCESSFULLY!\n")

if __name__ == "__main__":
    revert_claims()

