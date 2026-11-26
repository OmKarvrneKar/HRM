import json
import os

STORAGE_DIR = "HRM-main/data/storage/office_hrm"

def update_meeting_rooms():
    path = os.path.join(STORAGE_DIR, "facility_rooms.json")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            rooms = json.load(f)
        for r in rooms:
            r["is_verified"] = False
            r["verification_status"] = "Unverified (Baseline Facility Space)"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(rooms, f, indent=2)
        print(f"Updated {len(rooms)} facility rooms with unverified status.")

def update_seating_allocations():
    path = os.path.join(STORAGE_DIR, "seating_allocations.json")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            allocs = json.load(f)
        for a in allocs:
            a["is_verified"] = False
            a["verification_status"] = "Unverified (Algorithmic Floor 3 Layout)"
            a["allocation_type"] = "Algorithmic Baseline (Pending Physical Office Confirmation)"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(allocs, f, indent=2)
        print(f"Updated {len(allocs)} seating allocations with unverified status.")

if __name__ == "__main__":
    update_meeting_rooms()
    update_seating_allocations()

