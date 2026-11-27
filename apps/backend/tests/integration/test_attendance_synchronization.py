import pytest
from datetime import datetime, timezone
from backend.services.attendance_service import AttendanceService
from backend.utils.timezone import get_local_date_str, now_utc


def test_clock_in_and_synchronization_across_dashboard_and_attendance(client, seeded_users, tokens, db):
    """
    Scenario 1 & 4:
    Employee clocks in -> both /api/attendance/today (Dashboard) and
    /api/attendance/calendar (Attendance page) immediately reflect Clocked In status and matching time.
    """
    emp1 = seeded_users["emp1"]
    emp_token = tokens["emp1"]
    headers = {"Authorization": f"Bearer {emp_token}"}
    today_str = get_local_date_str()

    # Clear any previous events today for clean test
    db.attendance_events.delete_many({"employee_id": emp1["employee_id"], "date": today_str})
    db.attendance_daily.delete_many({"employee_id": emp1["employee_id"], "attendance_date": today_str})

    # 1. Initially verify not clocked in
    res_init = client.get("/api/attendance/today", headers=headers)
    assert res_init.status_code == 200
    init_data = res_init.get_json()
    assert init_data["has_open_session"] is False
    assert init_data["is_clocked_in"] is False

    # 2. Clock in via check-in API
    res_in = client.post("/api/attendance/check-in", headers=headers, json={})
    assert res_in.status_code == 200
    in_data = res_in.get_json()
    assert in_data["success"] is True
    session_id = in_data["session_id"]
    assert session_id is not None

    # 3. Verify Dashboard endpoint (/api/attendance/today)
    res_dash = client.get("/api/attendance/today", headers=headers)
    assert res_dash.status_code == 200
    dash_data = res_dash.get_json()
    assert dash_data["has_open_session"] is True
    assert dash_data["is_clocked_in"] is True
    assert dash_data["attendance"] is not None
    assert dash_data["attendance"]["first_login"] is not None
    first_login_iso = dash_data["attendance"]["first_login"]

    # 4. Verify Attendance Page endpoint (/api/attendance/calendar)
    now = now_utc()
    res_cal = client.get(f"/api/attendance/calendar?year={now.year}&month={now.month}", headers=headers)
    assert res_cal.status_code == 200
    cal_data = res_cal.get_json()
    today_cell = next((d for d in cal_data["days"] if d["date"] == today_str), None)
    assert today_cell is not None
    assert today_cell["has_open_session"] is True
    assert today_cell["first_login_local"] is not None

    # 5. Verify Attendance Page History endpoint (/api/attendance/my-history)
    res_hist = client.get(f"/api/attendance/my-history?year={now.year}&month={now.month}", headers=headers)
    assert res_hist.status_code == 200
    hist_data = res_hist.get_json()
    today_rec = next((r for r in hist_data["records"] if r["attendance_date"] == today_str), None)
    assert today_rec is not None
    assert today_rec["has_open_session"] is True
    assert today_rec["first_login"][:19] == first_login_iso[:19]


def test_clock_out_and_synchronization(client, seeded_users, tokens, db):
    """
    Scenario 2 & 3:
    Employee clocks out -> both Dashboard and Attendance page endpoints
    immediately reflect Clocked Out status and matching final duration calculations.
    """
    emp1 = seeded_users["emp1"]
    emp_token = tokens["emp1"]
    headers = {"Authorization": f"Bearer {emp_token}"}
    today_str = get_local_date_str()

    # 1. Clock in first
    res_in = client.post("/api/attendance/check-in", headers=headers, json={})
    # If already clocked in or newly clocked in, verify active session
    res_dash = client.get("/api/attendance/today", headers=headers)
    assert res_dash.get_json()["has_open_session"] is True

    # 2. Clock out
    res_out = client.post("/api/attendance/check-out", headers=headers, json={})
    assert res_out.status_code == 200
    out_data = res_out.get_json()
    assert out_data["success"] is True

    # 3. Verify Dashboard endpoint shows clocked out
    res_dash_after = client.get("/api/attendance/today", headers=headers)
    dash_after = res_dash_after.get_json()
    assert dash_after["has_open_session"] is False
    assert dash_after["is_clocked_in"] is False
    assert dash_after["attendance"]["has_open_session"] is False

    # 4. Verify Attendance Page calendar endpoint shows clocked out
    now = now_utc()
    res_cal = client.get(f"/api/attendance/calendar?year={now.year}&month={now.month}", headers=headers)
    cal_data = res_cal.get_json()
    today_cell = next((d for d in cal_data["days"] if d["date"] == today_str), None)
    assert today_cell is not None
    assert today_cell["has_open_session"] is False


def test_prevent_duplicate_clock_in(client, seeded_users, tokens, db):
    """
    Scenario 7:
    Repeated or concurrent clock-in requests must be rejected with HTTP 400.
    No duplicate active sessions or corrupt attendance records may be created.
    """
    emp1 = seeded_users["emp1"]
    emp_token = tokens["emp1"]
    headers = {"Authorization": f"Bearer {emp_token}"}
    today_str = get_local_date_str()

    # Reset
    db.attendance_events.delete_many({"employee_id": emp1["employee_id"], "date": today_str})
    db.attendance_daily.delete_many({"employee_id": emp1["employee_id"], "attendance_date": today_str})

    # First clock-in succeeds
    res1 = client.post("/api/attendance/check-in", headers=headers, json={})
    assert res1.status_code == 200
    assert res1.get_json()["success"] is True

    # Immediate second clock-in must fail with 400
    res2 = client.post("/api/attendance/check-in", headers=headers, json={})
    assert res2.status_code == 400
    assert res2.get_json()["success"] is False
    assert "already have an active attendance session" in res2.get_json()["error"]

    # Verify database has exactly 1 open session event
    open_events = list(db.attendance_events.find({
        "employee_id": emp1["employee_id"],
        "date": today_str,
        "event_type": "LOGIN",
        "is_closed": False
    }))
    assert len(open_events) == 1


def test_prevent_duplicate_clock_out_and_orphan_logouts(client, seeded_users, tokens, db):
    """
    Scenario 7 & 8:
    Clock-out when not clocked in must be rejected with HTTP 400 without creating orphan LOGOUT events.
    """
    emp1 = seeded_users["emp1"]
    emp_token = tokens["emp1"]
    headers = {"Authorization": f"Bearer {emp_token}"}
    today_str = get_local_date_str()

    # Reset
    db.attendance_events.delete_many({"employee_id": emp1["employee_id"], "date": today_str})
    db.attendance_daily.delete_many({"employee_id": emp1["employee_id"], "attendance_date": today_str})

    # Clock-out without prior clock-in
    res = client.post("/api/attendance/check-out", headers=headers, json={})
    assert res.status_code == 400
    assert res.get_json()["success"] is False
    assert "No active clock-in session found" in res.get_json()["error"]

    # Verify no orphan events were created
    logout_events = list(db.attendance_events.find({
        "employee_id": emp1["employee_id"],
        "date": today_str,
        "event_type": "LOGOUT"
    }))
    assert len(logout_events) == 0


def test_prevent_clocking_for_another_employee(client, seeded_users, tokens):
    """
    Scenario 9:
    Employees cannot clock in or out for another employee.
    Mismatched employee_id in payload must return HTTP 403 Forbidden.
    """
    emp1 = seeded_users["emp1"]
    emp2 = seeded_users["emp2"]
    emp1_headers = {"Authorization": f"Bearer {tokens['emp1']}"}

    # Emp1 tries to clock in for Emp2
    res_in = client.post("/api/attendance/check-in", headers=emp1_headers, json={
        "employee_id": emp2["employee_id"]
    })
    assert res_in.status_code == 403
    assert "Forbidden" in res_in.get_json()["error"]

    # Emp1 tries to clock out for Emp2
    res_out = client.post("/api/attendance/check-out", headers=emp1_headers, json={
        "employee_id": emp2["employee_id"]
    })
    assert res_out.status_code == 403
    assert "Forbidden" in res_out.get_json()["error"]
