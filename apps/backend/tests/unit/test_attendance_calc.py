import pytest
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from services.attendance_service import AttendanceService
from utils.timezone import get_app_timezone


def make_test_event(emp_id, date_str, hour, minute, event_type, session_id):
    tz = get_app_timezone()
    y, m, d = map(int, date_str.split("-"))
    local_dt = datetime(y, m, d, hour, minute, 0, tzinfo=tz)
    utc_dt = local_dt.astimezone(timezone.utc)
    return {
        "employee_id": emp_id,
        "employee_name": "Test User",
        "date": date_str,
        "session_id": session_id,
        "event_type": event_type,
        "timestamp": utc_dt,
        "is_closed": event_type == "LOGOUT",
        "event_source": "TEST",
        "created_at": utc_dt,
        "updated_at": utc_dt
    }


def test_login_before_10am_is_ontime(db, seeded_users):
    """First login before 10:00 AM must be classified as ON_TIME with 0 delay."""
    emp_id = seeded_users["emp1"]["employee_id"]
    date_str = "2026-10-16"

    # Login at 09:45 AM
    ev = make_test_event(emp_id, date_str, 9, 45, "LOGIN", "s1")
    db.attendance_events.insert_one(ev)

    summary = AttendanceService.recalculate_daily_summary(emp_id, date_str)
    assert summary is not None
    assert summary["late_arrival_status"] == "ON_TIME"
    assert summary["delay_minutes"] == 0


def test_login_exactly_at_10am_is_ontime(db, seeded_users):
    """First login exactly at 10:00 AM must be classified as ON_TIME with 0 delay."""
    emp_id = seeded_users["emp1"]["employee_id"]
    date_str = "2026-10-16"

    # Login at 10:00 AM
    ev = make_test_event(emp_id, date_str, 10, 0, "LOGIN", "s1")
    db.attendance_events.insert_one(ev)

    summary = AttendanceService.recalculate_daily_summary(emp_id, date_str)
    assert summary["late_arrival_status"] == "ON_TIME"
    assert summary["delay_minutes"] == 0


def test_login_after_10am_is_late_with_correct_delay(db, seeded_users):
    """First login after 10:00 AM must be classified as LATE with accurate delay minutes."""
    emp_id = seeded_users["emp1"]["employee_id"]
    date_str = "2026-10-16"

    # Login at 10:25 AM (25 mins late)
    ev = make_test_event(emp_id, date_str, 10, 25, "LOGIN", "s1")
    db.attendance_events.insert_one(ev)

    summary = AttendanceService.recalculate_daily_summary(emp_id, date_str)
    assert summary["late_arrival_status"] == "LATE"
    assert summary["delay_minutes"] == 25


def test_multiple_sessions_preserved(db, seeded_users):
    """Intermediate sessions must be recorded without overwriting previous sessions."""
    emp_id = seeded_users["emp1"]["employee_id"]
    date_str = "2026-10-16"

    # Session 1: 9:45 to 12:30
    db.attendance_events.insert_one(make_test_event(emp_id, date_str, 9, 45, "LOGIN", "sess-1"))
    db.attendance_events.insert_one(make_test_event(emp_id, date_str, 12, 30, "LOGOUT", "sess-1"))

    # Session 2: 13:30 to 18:30
    db.attendance_events.insert_one(make_test_event(emp_id, date_str, 13, 30, "LOGIN", "sess-2"))
    db.attendance_events.insert_one(make_test_event(emp_id, date_str, 18, 30, "LOGOUT", "sess-2"))

    summary = AttendanceService.recalculate_daily_summary(emp_id, date_str)
    assert summary["session_count"] == 2
    assert len(summary["sessions"]) == 2


def test_logout_before_6pm_is_incomplete(db, seeded_users):
    """A logout before 6:00 PM must not qualify as final logout and status must remain INCOMPLETE."""
    emp_id = seeded_users["emp1"]["employee_id"]
    date_str = "2026-10-16"

    # Login at 09:50 AM, early logout at 4:30 PM (16:30)
    db.attendance_events.insert_one(make_test_event(emp_id, date_str, 9, 50, "LOGIN", "s1"))
    db.attendance_events.insert_one(make_test_event(emp_id, date_str, 16, 30, "LOGOUT", "s1"))

    summary = AttendanceService.recalculate_daily_summary(emp_id, date_str)
    assert summary["status"] == "INCOMPLETE"
    assert summary["final_qualifying_logout"] is None


def test_qualifying_logout_after_6pm_calculates_working_span(db, seeded_users):
    """Official working duration must be elapsed span from first login to final qualifying logout."""
    emp_id = seeded_users["emp1"]["employee_id"]
    date_str = "2026-10-16"

    # 09:45 AM to 18:30 PM (8h 45m = 31500 seconds)
    db.attendance_events.insert_one(make_test_event(emp_id, date_str, 9, 45, "LOGIN", "s1"))
    db.attendance_events.insert_one(make_test_event(emp_id, date_str, 12, 0, "LOGOUT", "s1"))
    db.attendance_events.insert_one(make_test_event(emp_id, date_str, 13, 0, "LOGIN", "s2"))
    db.attendance_events.insert_one(make_test_event(emp_id, date_str, 18, 30, "LOGOUT", "s2"))

    summary = AttendanceService.recalculate_daily_summary(emp_id, date_str)
    assert summary["status"] == "PRESENT"
    assert summary["official_working_duration_seconds"] == 31500  # 8h 45m
    assert summary["official_working_duration_display"] == "8h 45m"


def test_manual_attendance_correction_audited(db, seeded_users):
    """Authorized HR can correct attendance with required reason and full audit entry."""
    hr_actor = seeded_users["hr"]
    emp_id = seeded_users["emp1"]["employee_id"]
    date_str = "2026-10-16"

    # Setup initial record
    db.attendance_events.insert_one(make_test_event(emp_id, date_str, 10, 15, "LOGIN", "s1"))
    AttendanceService.recalculate_daily_summary(emp_id, date_str)

    # Correct record
    corrected, err = AttendanceService.correct_attendance_record(
        actor=hr_actor,
        target_employee_id=emp_id,
        date_str=date_str,
        corrections={"status": "PRESENT", "late_arrival_status": "ON_TIME", "delay_minutes": 0},
        reason="Biometric turnstile glitch at main office lobby entrance"
    )

    assert err is None
    assert corrected["status"] == "PRESENT"
    assert corrected["late_arrival_status"] == "ON_TIME"
    assert corrected["is_manually_corrected"] is True

    # Verify audit log was created
    audit = db.audit_logs.find_one({"action": "ATTENDANCE_CORRECTION"})
    assert audit is not None
    assert audit["actor_id"] == hr_actor["employee_id"]


def test_office_rules_returns_cutoff_and_intimation(db):
    """Office rules must contain 7:00 PM cutoff and 45-minute intimation parameters."""
    rules = AttendanceService.get_office_rules()
    assert rules["start_time"] == "10:00"
    assert rules["end_time"] == "18:00"
    assert rules["cutoff_time"] == "19:00"
    assert rules["intimation_minutes"] == 45


def test_get_office_timing_status_structure_and_values(db, seeded_users):
    """Timing status must report remaining time to 18:00 and 19:00 cutoff with employee context."""
    emp_id = seeded_users["emp1"]["employee_id"]
    status = AttendanceService.get_office_timing_status(emp_id)

    assert status["shift_start_time"] == "10:00"
    assert status["shift_end_time"] == "18:00"
    assert status["cutoff_time"] == "19:00"
    assert status["intimation_start_time"] == "18:15"
    assert status["intimation_minutes"] == 45
    assert "remaining_seconds_to_qualify" in status
    assert "remaining_seconds_to_cutoff" in status
    assert "remaining_display_to_qualify" in status
    assert "remaining_display_to_cutoff" in status
    assert isinstance(status["is_shift_in_progress"], bool)
    assert isinstance(status["is_intimation_active"], bool)
    assert isinstance(status["is_past_cutoff"], bool)


def test_cutoff_intimations_service_idempotency(db, seeded_users):
    """Cutoff intimations must create high-priority notifications idempotently for unclosed sessions."""
    from utils.timezone import get_local_date_str
    today_str = get_local_date_str()
    emp_id = seeded_users["emp1"]["employee_id"]

    # Insert an unclosed attendance record today
    ev = make_test_event(emp_id, today_str, 10, 0, "LOGIN", "session-cutoff-test")
    db.attendance_events.insert_one(ev)
    AttendanceService.recalculate_daily_summary(emp_id, today_str)

    # Ensure record exists and is pending
    record = db.attendance_daily.find_one({"employee_id": emp_id, "attendance_date": today_str})
    assert record is not None
    assert record["final_qualifying_logout"] is None

    # Simulate intimation active by patching get_office_timing_status
    original_timing = AttendanceService.get_office_timing_status
    AttendanceService.get_office_timing_status = classmethod(lambda cls, eid=None: {
        "is_intimation_active": True,
        "is_past_cutoff": False,
        "remaining_seconds_to_cutoff": 2700  # 45 minutes
    })

    try:
        sent1 = AttendanceService.check_and_send_cutoff_intimations()
        assert len(sent1) == 1
        assert "7:00 PM Cutoff" in sent1[0]["title"]
        assert sent1[0]["priority"] == "URGENT"

        # Second call on same day should be idempotent (no duplicates)
        sent2 = AttendanceService.check_and_send_cutoff_intimations()
        assert len(sent2) == 0
    finally:
        AttendanceService.get_office_timing_status = original_timing

