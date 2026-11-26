import io
import openpyxl


def test_work_diary_api_full_flow(client, seeded_users, tokens):
    """Test full API lifecycle: create, get daily, update, get monthly, delete, and download Excel."""
    emp1_token = tokens["emp1"]
    headers_emp1 = {"Authorization": f"Bearer {emp1_token}"}

    # 1. Unauthenticated request must fail
    res = client.get("/api/work-diary/daily?date=2026-10-16")
    assert res.status_code == 401

    # 2. Create work diary entry
    payload = {
        "diary_date": "2026-10-16",
        "start_time": "10:00",
        "end_time": "13:00",
        "activity_title": "Database Schema Design",
        "work_description": "Modeled collections, added indexes, and validated schema.",
        "category": "Development",
        "status": "Completed"
    }
    res = client.post("/api/work-diary/entries", json=payload, headers=headers_emp1)
    assert res.status_code == 201
    data = res.get_json()
    assert "entry" in data
    entry = data["entry"]
    diary_id = entry["diary_id"]
    assert entry["duration_hours"] == 3.0
    assert entry["duration_display"] == "3h 0m"

    # 3. Get daily diary
    res = client.get("/api/work-diary/daily?date=2026-10-16", headers=headers_emp1)
    assert res.status_code == 200
    daily_data = res.get_json()
    assert daily_data["summary"]["entry_count"] == 1
    assert daily_data["summary"]["total_hours"] == 3.0
    assert daily_data["entries"][0]["diary_id"] == diary_id

    # 4. Update entry
    update_payload = {
        "start_time": "10:00",
        "end_time": "14:30",
        "activity_title": "Database Schema Design & Index Tuning"
    }
    res = client.put(f"/api/work-diary/entries/{diary_id}", json=update_payload, headers=headers_emp1)
    assert res.status_code == 200
    updated_entry = res.get_json()["entry"]
    assert updated_entry["duration_hours"] == 4.5
    assert updated_entry["duration_display"] == "4h 30m"
    assert updated_entry["activity_title"] == "Database Schema Design & Index Tuning"

    # 5. Get monthly diary
    res = client.get("/api/work-diary/monthly?month=2026-10", headers=headers_emp1)
    assert res.status_code == 200
    monthly_data = res.get_json()
    assert monthly_data["summary"]["entry_count"] == 1
    assert monthly_data["summary"]["total_hours"] == 4.5
    assert len(monthly_data["daily_summaries"]) == 1

    # 6. Export Daily Excel
    res = client.get("/api/work-diary/export/excel?type=daily&date=2026-10-16", headers=headers_emp1)
    assert res.status_code == 200
    assert res.mimetype == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert "attachment; filename=" in res.headers.get("Content-Disposition", "")
    wb_daily = openpyxl.load_workbook(io.BytesIO(res.data))
    assert wb_daily.active["A1"].value == "AI Samrat Pvt Ltd"

    # 7. Export Monthly Excel
    res = client.get("/api/work-diary/export/excel?type=monthly&month=2026-10", headers=headers_emp1)
    assert res.status_code == 200
    assert res.mimetype == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    wb_month = openpyxl.load_workbook(io.BytesIO(res.data))
    assert wb_month.active["A1"].value == "AI Samrat Pvt Ltd"

    # 8. Delete entry
    res = client.delete(f"/api/work-diary/entries/{diary_id}", headers=headers_emp1)
    assert res.status_code == 200

    # 9. Verify daily entries are now 0
    res = client.get("/api/work-diary/daily?date=2026-10-16", headers=headers_emp1)
    assert res.get_json()["summary"]["entry_count"] == 0


def test_work_diary_strict_privacy_across_all_roles(client, seeded_users, tokens):
    """
    CRITICAL REQUIREMENT:
    Work diary entries must be visible ONLY to that particular user.
    Emp2, HR, and HR Manager cannot see or modify Emp1's work diary entries.
    """
    emp1_token = tokens["emp1"]
    emp2_token = tokens["emp2"]
    hr_token = tokens["hr"]
    mgr_token = tokens["hr_manager"]

    h_emp1 = {"Authorization": f"Bearer {emp1_token}"}
    h_emp2 = {"Authorization": f"Bearer {emp2_token}"}
    h_hr = {"Authorization": f"Bearer {hr_token}"}
    h_mgr = {"Authorization": f"Bearer {mgr_token}"}

    # Emp1 logs an entry
    res = client.post("/api/work-diary/entries", json={
        "diary_date": "2026-10-16",
        "start_time": "09:00",
        "end_time": "12:00",
        "activity_title": "Confidential Security Audit",
        "work_description": "Identified security vulnerabilities in auth layer.",
        "category": "Development",
        "status": "Completed"
    }, headers=h_emp1)
    assert res.status_code == 201
    entry_id = res.get_json()["entry"]["diary_id"]

    # 1. Emp2 queries daily work diary for that day -> must NOT see Emp1's entry
    res = client.get("/api/work-diary/daily?date=2026-10-16", headers=h_emp2)
    assert res.status_code == 200
    assert res.get_json()["summary"]["entry_count"] == 0
    assert len(res.get_json()["entries"]) == 0

    # 2. HR queries daily work diary for that day -> must NOT see Emp1's entry
    res = client.get("/api/work-diary/daily?date=2026-10-16", headers=h_hr)
    assert res.status_code == 200
    assert res.get_json()["summary"]["entry_count"] == 0

    # 3. HR Manager queries daily work diary for that day -> must NOT see Emp1's entry
    res = client.get("/api/work-diary/daily?date=2026-10-16", headers=h_mgr)
    assert res.status_code == 200
    assert res.get_json()["summary"]["entry_count"] == 0

    # 4. Emp2 attempts to update Emp1's entry -> 403 Forbidden
    res = client.put(f"/api/work-diary/entries/{entry_id}", json={
        "activity_title": "Attempted breach"
    }, headers=h_emp2)
    assert res.status_code == 403

    # 5. HR attempts to delete Emp1's entry -> 403 Forbidden
    res = client.delete(f"/api/work-diary/entries/{entry_id}", headers=h_hr)
    assert res.status_code == 403

    # 6. HR Manager attempts to delete Emp1's entry -> 403 Forbidden
    res = client.delete(f"/api/work-diary/entries/{entry_id}", headers=h_mgr)
    assert res.status_code == 403

    # 7. Emp2 exports Excel for that day -> only contains Emp2's data (0 entries)
    res = client.get("/api/work-diary/export/excel?type=daily&date=2026-10-16", headers=h_emp2)
    assert res.status_code == 200
    wb_emp2 = openpyxl.load_workbook(io.BytesIO(res.data))
    sheet = wb_emp2.active
    # Row 6 has the empty notice
    assert "No work diary entries found" in sheet["A6"].value
