import pytest
from backend.services.attendance_service import AttendanceService, OFFICIAL_HOLIDAYS
from backend.services.leave_service import LeaveService
from backend.database.connection import get_db
from backend.utils.timezone import now_utc


def test_attendance_calendar_holidays_and_weekends(db, seeded_users):
    """Test calendar correctly marks official holidays and weekends."""
    emp1 = seeded_users["emp1"]
    cal = AttendanceService.get_monthly_calendar_data(emp1["employee_id"], 2026, 10)

    assert cal["year"] == 2026
    assert cal["month"] == 10
    assert cal["days_in_month"] == 31
    assert len(cal["days"]) == 31

    # Oct 2, 2026 is Mahatma Gandhi Jayanti
    day2 = next(d for d in cal["days"] if d["date"] == "2026-10-02")
    assert day2["primary_status"] == "HOLIDAY"
    assert "Gandhi" in day2["holiday_name"]

    # Oct 4, 2026 is Sunday (day_of_week == 6)
    day4 = next(d for d in cal["days"] if d["date"] == "2026-10-04")
    assert day4["is_weekend"] is True
    assert day4["primary_status"] == "WEEKEND"


def test_attendance_calendar_present_late_absent_and_leave(db, seeded_users):
    """Test calendar identifies Present, Late Arrival, Absent, and Approved Leave days."""
    emp1 = seeded_users["emp1"]
    eid = emp1["employee_id"]

    # 1. Insert a PRESENT (on time) day: 2026-10-05 (Monday)
    db.attendance_daily.insert_one({
        "employee_id": eid,
        "attendance_date": "2026-10-05",
        "status": "PRESENT",
        "late_arrival_status": "ON_TIME",
        "delay_minutes": 0,
        "official_working_duration_seconds": 28800,
        "official_working_duration_display": "8h 0m",
        "first_login": now_utc(),
        "final_qualifying_logout": now_utc(),
        "sessions": [{"session_id": "s1"}]
    })

    # 2. Insert a LATE arrival day: 2026-10-06 (Tuesday)
    db.attendance_daily.insert_one({
        "employee_id": eid,
        "attendance_date": "2026-10-06",
        "status": "PRESENT",
        "late_arrival_status": "LATE",
        "delay_minutes": 25,
        "official_working_duration_seconds": 27000,
        "official_working_duration_display": "7h 30m",
        "first_login": now_utc(),
        "final_qualifying_logout": now_utc(),
        "sessions": [{"session_id": "s2"}]
    })

    # 3. Insert an Approved Leave: 2026-10-07 (Wednesday)
    LeaveService.apply_leave(emp1, {
        "start_date": "2026-10-07",
        "end_date": "2026-10-07",
        "leave_type": "Sick Leave",
        "reason": "Doctor appointment"
    })
    # Update to Approved in DB directly for test
    db.leave_requests.update_one({"start_date": "2026-10-07"}, {"$set": {"status": "Approved"}})

    # Fetch calendar
    cal = AttendanceService.get_monthly_calendar_data(eid, 2026, 10)

    # Verify Present day
    d5 = next(d for d in cal["days"] if d["date"] == "2026-10-05")
    assert d5["primary_status"] == "PRESENT"
    assert d5["duration_display"] == "8h 0m"

    # Verify Late day
    d6 = next(d for d in cal["days"] if d["date"] == "2026-10-06")
    assert d6["primary_status"] == "LATE"
    assert d6["delay_minutes"] == 25

    # Verify Leave day
    d7 = next(d for d in cal["days"] if d["date"] == "2026-10-07")
    assert d7["primary_status"] == "LEAVE"
    assert "Sick Leave" in d7["status_label"]

    # Verify past working day with no punch is ABSENT: 2026-10-08 (Thursday)
    # (assuming test runs on or after 2026-10-08, in 2026-10-16 context)
    d8 = next(d for d in cal["days"] if d["date"] == "2026-10-08")
    assert d8["primary_status"] == "ABSENT"


def test_attendance_calendar_api_endpoint(client, seeded_users, tokens):
    """Test /api/attendance/calendar endpoint with auth and role boundaries."""
    emp_token = tokens["emp1"]
    hr_token = tokens["hr"]

    # 1. Unauthenticated -> 401
    res = client.get("/api/attendance/calendar?year=2026&month=10")
    assert res.status_code == 401

    # 2. Authenticated employee gets own calendar
    res = client.get("/api/attendance/calendar?year=2026&month=10", headers={"Authorization": f"Bearer {emp_token}"})
    assert res.status_code == 200
    data = res.get_json()
    assert data["year"] == 2026
    assert data["month"] == 10
    assert len(data["days"]) == 31
    assert "present_count" in data["summary"]

    # 3. Regular employee cannot access another employee's calendar -> 403
    res = client.get("/api/attendance/calendar?year=2026&month=10&employee_id=EMP-TEST-2", headers={"Authorization": f"Bearer {emp_token}"})
    assert res.status_code == 403

    # 4. HR can access any employee's calendar -> 200
    res = client.get(f"/api/attendance/calendar?year=2026&month=10&employee_id={seeded_users['emp1']['employee_id']}", headers={"Authorization": f"Bearer {hr_token}"})
    assert res.status_code == 200
    hr_view = res.get_json()
    assert hr_view["employee_id"] == seeded_users["emp1"]["employee_id"]
