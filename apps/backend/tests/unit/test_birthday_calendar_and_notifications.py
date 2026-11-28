import pytest
from datetime import datetime, timezone
import pytz
from services.birthday_service import BirthdayService
from services.notification_service import NotificationService
from scheduler.scheduler import DistributedScheduler
from auth.security import generate_jwt_token, hash_password
from permissions.rbac import Role
from config import Config

IST = pytz.timezone("Asia/Kolkata")


@pytest.fixture
def birthday_setup(db):
    """Seed test database with real-scenario employees including November celebrants."""
    users = [
        {
            "employee_id": "EMP-1038",
            "full_name": "Nikil H E",
            "email": "nikil.he@aisamrat.com",
            "role": Role.EMPLOYEE,
            "department": "AIML",
            "designation": "AI Engineer",
            "date_of_birth": "2005-11-04",
            "is_active": True,
            "employment_status": "Active",
            "password_hash": hash_password("Test@123")
        },
        {
            "employee_id": "EMP-1013",
            "full_name": "Salil Vijaykumar Madivala",
            "email": "salil.vm@aisamrat.com",
            "role": Role.EMPLOYEE,
            "department": "Engineering",
            "designation": "Software Engineer",
            "date_of_birth": "2005-11-24",
            "is_active": True,
            "employment_status": "Active",
            "password_hash": hash_password("Test@123")
        },
        {
            "employee_id": "EMP-LEAP",
            "full_name": "Leap Day Employee",
            "email": "leap@aisamrat.com",
            "role": Role.EMPLOYEE,
            "department": "Product",
            "designation": "Product Specialist",
            "date_of_birth": "2000-02-29",
            "is_active": True,
            "employment_status": "Active",
            "password_hash": hash_password("Test@123")
        },
        {
            "employee_id": "EMP-INACTIVE-NOV",
            "full_name": "Inactive November Celebrant",
            "email": "inactive.nov@aisamrat.com",
            "role": Role.EMPLOYEE,
            "department": "Finance",
            "designation": "Accountant",
            "date_of_birth": "2000-11-15",
            "is_active": False,
            "employment_status": "Offboarded",
            "password_hash": hash_password("Test@123")
        },
        {
            "employee_id": "EMP-HIDDEN-NOV",
            "full_name": "Privacy Conscious Celebrant",
            "email": "hidden.nov@aisamrat.com",
            "role": Role.EMPLOYEE,
            "department": "Legal",
            "designation": "Legal Counsel",
            "date_of_birth": "2002-11-18",
            "is_active": True,
            "hide_birthday": True,
            "employment_status": "Active",
            "password_hash": hash_password("Test@123")
        },
        {
            "employee_id": "HR-1001",
            "full_name": "Ramya HR",
            "email": "hr.ramya@aisamrat.com",
            "role": Role.HR,
            "department": "Human Resources",
            "designation": "HR Operations Lead",
            "date_of_birth": "1998-05-15",
            "is_active": True,
            "employment_status": "Active",
            "password_hash": hash_password("Hr@123456")
        }
    ]
    for u in users:
        res = db.users.insert_one(u)
        u["_id"] = res.inserted_id

    return {u["employee_id"]: u for u in users}


def auth_header(user):
    token = generate_jwt_token(user)
    return {"Authorization": f"Bearer {token}"}


# 1. Actual employee birthdays appear in the monthly calendar
def test_actual_employee_birthdays_appear_in_monthly_calendar(birthday_setup):
    birthdays = BirthdayService.get_monthly_birthdays(year=2026, month=11)
    names = [b["full_name"] for b in birthdays]
    assert "Nikil H E" in names
    assert "Salil Vijaykumar Madivala" in names
    assert len(birthdays) == 2


# 2. November birthdays displayed correctly with upcoming countdown
def test_november_birthdays_displayed_correctly(birthday_setup):
    target_dt = IST.localize(datetime(2026, 11, 1, 9, 0, 0))
    upcoming = BirthdayService.get_upcoming_birthdays(target_local_dt=target_dt)
    assert len(upcoming) == 2
    # Nikil is on Nov 4 (day 4 - day 1 = 3 days until)
    nikil = next(b for b in upcoming if b["employee_id"] == "EMP-1038")
    assert nikil["day"] == 4
    assert nikil["days_until"] == 3
    assert nikil["is_today"] is False
    assert nikil["birthday_formatted"] == "November 4"

    # Salil is on Nov 24 (day 24 - day 1 = 23 days until)
    salil = next(b for b in upcoming if b["employee_id"] == "EMP-1013")
    assert salil["day"] == 24
    assert salil["days_until"] == 23


# 3. Birthday notifications are stored in the database
def test_birthday_notifications_stored_in_database(birthday_setup, db):
    target_dt = IST.localize(datetime(2026, 11, 1, 9, 0, 0))
    notif = BirthdayService.check_and_send_monthly_birthday_announcement(target_local_dt=target_dt)
    assert notif is not None

    stored = db.notifications.find_one({"reference_id": "bday_monthly_2026_11"})
    assert stored is not None
    assert stored["category"] == "ANNOUNCEMENT"
    assert "Upcoming Birthdays in November" in stored["title"]
    assert stored["link"] == "/birthdays"


# 4. Notification bell displays birthday notifications
def test_notification_bell_displays_birthday_notifications(birthday_setup, client):
    target_dt = IST.localize(datetime(2026, 11, 1, 9, 0, 0))
    BirthdayService.check_and_send_monthly_birthday_announcement(target_local_dt=target_dt)

    nikil = birthday_setup["EMP-1038"]
    res = client.get("/api/notifications", headers=auth_header(nikil))
    assert res.status_code == 200
    data = res.get_json()
    assert data["unread_count"] >= 1
    found = any(n["category"] == "ANNOUNCEMENT" and n.get("link") == "/birthdays" for n in data["notifications"])
    assert found is True


# 5. Unread count updates properly on mark as read
def test_unread_count_updates_and_preserves_other_users(birthday_setup, client, db):
    target_dt = IST.localize(datetime(2026, 11, 1, 9, 0, 0))
    notif = BirthdayService.check_and_send_monthly_birthday_announcement(target_local_dt=target_dt)

    nikil = birthday_setup["EMP-1038"]
    salil = birthday_setup["EMP-1013"]

    nikil_initial = client.get("/api/notifications", headers=auth_header(nikil)).get_json()
    salil_initial = client.get("/api/notifications", headers=auth_header(salil)).get_json()

    notif_id = str(notif["_id"])
    res = client.post(f"/api/notifications/{notif_id}/read", headers=auth_header(nikil))
    assert res.status_code == 200
    assert db.notifications.find_one({"_id": notif["_id"]})["read_by"] == ["EMP-1038"]

    nikil_after = client.get("/api/notifications", headers=auth_header(nikil)).get_json()
    salil_after = client.get("/api/notifications", headers=auth_header(salil)).get_json()

    assert nikil_after["unread_count"] == nikil_initial["unread_count"] - 1
    # Salil must still be unread
    assert salil_after["unread_count"] == salil_initial["unread_count"]
    salil_notif = next(n for n in salil_after["notifications"] if n["id"] == notif_id)
    assert salil_notif["is_read"] is False


def test_marking_missing_notification_returns_error(seeded_users, client):
    response = client.post(
        "/api/notifications/000000000000000000000000/read",
        headers=auth_header(seeded_users["emp1"])
    )
    assert response.status_code == 404


# 6. Notifications remain persistent in database
def test_notifications_remain_persistent(birthday_setup, db):
    target_dt = IST.localize(datetime(2026, 11, 1, 9, 0, 0))
    BirthdayService.check_and_send_monthly_birthday_announcement(target_local_dt=target_dt)

    count1 = db.notifications.count_documents({"category": "ANNOUNCEMENT"})
    assert count1 >= 1

    # Simulate restart/re-instantiation
    docs = list(db.notifications.find({"category": "ANNOUNCEMENT"}))
    assert len(docs) == count1


# 7. Monthly announcement does not duplicate (idempotency)
def test_monthly_announcement_idempotency_no_duplicate(birthday_setup, db):
    target_dt = IST.localize(datetime(2026, 11, 1, 9, 0, 0))
    res1 = BirthdayService.check_and_send_monthly_birthday_announcement(target_local_dt=target_dt)
    assert res1 is not None

    res2 = BirthdayService.check_and_send_monthly_birthday_announcement(target_local_dt=target_dt)
    assert res2 is None  # Skipped because already generated

    count = db.notifications.count_documents({"reference_id": "bday_monthly_2026_11"})
    assert count == 1


# 8. Birthday-day greeting does not duplicate
def test_birthday_day_greeting_idempotency(birthday_setup, db):
    # Nov 4 is Nikil's birthday
    target_dt = IST.localize(datetime(2026, 11, 4, 9, 0, 0))
    res1 = BirthdayService.check_and_send_birthday_notifications(target_local_dt=target_dt)
    assert len(res1) == 2  # 1 personal + 1 company announcement

    # Re-running same day should be skipped
    res2 = BirthdayService.check_and_send_birthday_notifications(target_local_dt=target_dt)
    assert len(res2) == 0

    personal_count = db.notifications.count_documents({"reference_id": "bday_personal_EMP-1038_2026-11-04"})
    assert personal_count == 1


# 9. Scheduler uses Asia/Kolkata timezone
def test_scheduler_timezone_and_jobs():
    scheduler_instance = DistributedScheduler._scheduler
    # If not running, test start/shutdown safely
    DistributedScheduler.start()
    tz_str = getattr(DistributedScheduler._scheduler.timezone, "zone", None) or getattr(DistributedScheduler._scheduler.timezone, "key", str(DistributedScheduler._scheduler.timezone))
    assert tz_str == "Asia/Kolkata"
    
    daily_job = DistributedScheduler._scheduler.get_job("daily_birthday_job")
    assert daily_job is not None
    daily_fields = {f.name: str(f) for f in daily_job.trigger.fields}
    assert daily_fields["hour"] == "9"
    assert daily_fields["minute"] == "0"

    monthly_job = DistributedScheduler._scheduler.get_job("monthly_birthday_job")
    assert monthly_job is not None
    monthly_fields = {f.name: str(f) for f in monthly_job.trigger.fields}
    assert monthly_fields["day"] == "1"
    assert monthly_fields["hour"] == "9"
    assert monthly_fields["minute"] == "0"
    DistributedScheduler.shutdown()


# 10. In-app notifications work without email or WhatsApp configuration
def test_in_app_notifications_work_without_external_credentials(birthday_setup, db, monkeypatch):
    monkeypatch.setattr(Config, "EMAIL_ENABLED", False)
    monkeypatch.setattr(Config, "SMTP_HOST", "")
    target_dt = IST.localize(datetime(2026, 11, 4, 9, 0, 0))
    notifs = BirthdayService.check_and_send_birthday_notifications(target_local_dt=target_dt)
    assert len(notifs) >= 1
    # Verify in-app notifications exist in database
    assert db.notifications.count_documents({"category": "BIRTHDAY"}) >= 1


# 11. Inactive, offboarded, and privacy-hidden employees are excluded
def test_inactive_and_privacy_excluded(birthday_setup):
    birthdays = BirthdayService.get_monthly_birthdays(year=2026, month=11)
    emp_ids = [b["employee_id"] for b in birthdays]
    assert "EMP-INACTIVE-NOV" not in emp_ids
    assert "EMP-HIDDEN-NOV" not in emp_ids


# 12. Privacy enforcement: Birth year and full DOB are never exposed
def test_privacy_birth_year_and_dob_never_exposed(birthday_setup, client):
    hr_user = birthday_setup["HR-1001"]
    res = client.get("/api/birthdays/monthly?month=11&year=2026", headers=auth_header(hr_user))
    assert res.status_code == 200
    data = res.get_json()
    for b in data["birthdays"]:
        assert "date_of_birth" not in b
        assert "birth_year" not in b
        assert "age" not in b
        assert "2005" not in str(b.values())

    preview = BirthdayService.preview_monthly_announcement(year=2026, month=11)
    assert "2005" not in preview["preview_body"]


# 13. Leap day February 29 policy: observed on Feb 28 in non-leap year
def test_leap_day_february_29_policy(birthday_setup):
    # 2025 is not a leap year
    target_dt_28 = IST.localize(datetime(2025, 2, 28, 9, 0, 0))
    today_celebrants = BirthdayService.get_today_birthdays(target_local_dt=target_dt_28)
    leap_ids = [c["employee_id"] for c in today_celebrants]
    assert "EMP-LEAP" in leap_ids

    # 2028 is a leap year (observed on Feb 29, not Feb 28)
    target_dt_leap_28 = IST.localize(datetime(2028, 2, 28, 9, 0, 0))
    today_28 = BirthdayService.get_today_birthdays(target_local_dt=target_dt_leap_28)
    assert "EMP-LEAP" not in [c["employee_id"] for c in today_28]

    target_dt_leap_29 = IST.localize(datetime(2028, 2, 29, 9, 0, 0))
    today_29 = BirthdayService.get_today_birthdays(target_local_dt=target_dt_leap_29)
    assert "EMP-LEAP" in [c["employee_id"] for c in today_29]


# 14. Startup catchup execution
def test_startup_catchup_execution(birthday_setup, db):
    # Simulate server booting on Nov 1 at 14:00 (past 9:00 AM)
    target_dt = IST.localize(datetime(2026, 11, 1, 14, 0, 0))
    BirthdayService.run_startup_catchup(target_local_dt=target_dt)
    stored = db.notifications.find_one({"reference_id": "bday_monthly_2026_11"})
    assert stored is not None
    assert stored["category"] == "ANNOUNCEMENT"


# 15. HR preview and test trigger endpoints
def test_hr_preview_and_test_trigger_endpoints(birthday_setup, client):
    hr_user = birthday_setup["HR-1001"]
    emp_user = birthday_setup["EMP-1038"]

    # Preview by HR: 200
    res_hr = client.get("/api/birthdays/preview?month=11&year=2026", headers=auth_header(hr_user))
    assert res_hr.status_code == 200
    assert "Nikil H E" in res_hr.get_json()["preview_body"]

    # Preview by Employee: 403 Forbidden
    res_emp = client.get("/api/birthdays/preview?month=11&year=2026", headers=auth_header(emp_user))
    assert res_emp.status_code == 403

    # Test trigger by HR: 200
    res_test = client.post("/api/birthdays/trigger-check", json={"action": "test"}, headers=auth_header(hr_user))
    assert res_test.status_code == 200
    assert res_test.get_json()["success"] is True

    # Test trigger by Employee: 403 Forbidden
    res_emp_trigger = client.post("/api/birthdays/trigger-check", json={"action": "test"}, headers=auth_header(emp_user))
    assert res_emp_trigger.status_code == 403
