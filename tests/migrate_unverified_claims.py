import json
import os

STORAGE_DIR = "HRM-main/data/storage/office_hrm"

def update_seating():
    path = os.path.join(STORAGE_DIR, "seating_allocations.json")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        for d in data:
            d["status"] = "Provisional"
            d["is_verified"] = False
            d["verification_status"] = "Provisional (Algorithmic Floor 3 Layout)"
            d["allocation_type"] = "Algorithmic Baseline Layout (Pending Physical Confirmation)"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        print(f"Updated {len(data)} seating allocations to Provisional / Unverified.")

def update_rooms():
    path = os.path.join(STORAGE_DIR, "facility_rooms.json")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        for d in data:
            d["status"] = "Unverified"
            d["is_verified"] = False
            d["verification_status"] = "Unverified Baseline (Pending Campus Audit)"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        print(f"Updated {len(data)} facility rooms to Unverified Baseline.")

if __name__ == "__main__":
    update_seating()
    update_rooms()

