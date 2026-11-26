import json
import os
import requests

def inspect_collections():
    base_dir = "HRM-main/data/storage/office_hrm"
    collections = ["kudos_ledger", "facility_rooms", "seating_allocations", "overtime_requests"]
    
    print("=== PERSISTENT STORAGE INSPECTION ===")
    for col in collections:
        path = os.path.join(base_dir, f"{col}.json")
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            print(f"\nCollection: {col}")
            print(f"Total Records in File: {len(data)}")
            for item in data:
                cid = item.get("allocation_id") or item.get("room_id") or item.get("kudos_id") or item.get("request_id") or item.get("_id")
                desc = item.get("room_name") or item.get("employee_name") or item.get("message") or item.get("reason")
                print(f"  - Record ID: {cid} | Details: {desc}")
        else:
            print(f"\nCollection: {col} -> File does not exist (0 records).")

def inspect_apis():
    print("\n=== FLASK API ENDPOINT INSPECTION ===")
    # Login as admin to get token
    session = requests.Session()
    login_res = session.post("http://127.0.0.1:5000/api/auth/login", json={"email": "admin@aisamrat.com", "password": "password123"})
    if login_res.status_code != 200:
        print("Failed to login as admin:", login_res.text)
        return
    token = login_res.json().get("access_token")
    headers = {"Authorization": f"Bearer {token}"}
    
    endpoints = {
        "Kudos (/api/engagement/kudos)": "http://127.0.0.1:5000/api/engagement/kudos",
        "Seating (/api/assets/seating-lockers)": "http://127.0.0.1:5000/api/assets/seating-lockers",
        "Rooms (/api/facilities/rooms)": "http://127.0.0.1:5000/api/facilities/rooms",
        "Inventory Hardware & Software (/api/assets/inventory)": "http://127.0.0.1:5000/api/assets/inventory",
        "Overtime (/api/overtime/list)": "http://127.0.0.1:5000/api/overtime/list"
    }
    
    for name, url in endpoints.items():
        res = session.get(url, headers=headers)
        if res.status_code == 200:
            data = res.json()
            if "kudos_feed" in data:
                print(f"{name}: Success (200) | kudos_feed count: {len(data['kudos_feed'])}")
            elif "all_allocations" in data:
                print(f"{name}: Success (200) | all_allocations count: {len(data['all_allocations'])}, total_allocated: {data.get('total_allocated')}")
            elif "rooms" in data:
                print(f"{name}: Success (200) | rooms count: {len(data['rooms'])}")
            elif "hardware" in data:
                print(f"{name}: Success (200) | hardware count: {len(data['hardware'])}, software count: {len(data.get('software', []))}, rooms count: {len(data.get('rooms', []))}")
            elif "requests" in data:
                print(f"{name}: Success (200) | requests count: {len(data['requests'])}")
            else:
                print(f"{name}: Success (200) | response keys: {list(data.keys())}")
        else:
            print(f"{name}: Failed ({res.status_code}) | {res.text[:100]}")

if __name__ == "__main__":
    inspect_collections()
    inspect_apis()

