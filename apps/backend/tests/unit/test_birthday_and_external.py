import pytest
from datetime import datetime
from zoneinfo import ZoneInfo
from services.birthday_service import BirthdayService
from services.external_notification_service import ExternalNotificationService
from permissions.rbac import Role


def test_monthly_birthday_announcement_first_of_month(db, seeded_users):
    """Verifies monthly birthday announcement on 1st of month identifies celebrants without exposing birth year."""
    # Set emp1's DOB in November
    db.users.update_one(
        {"employee_id": seeded_users["emp1"]["employee_id"]},
        {"$set": {"date_of_birth": "1994-11-15", "department": "Core Engineering"}}
    )
    # Set emp2's DOB in November
    db.users.update_one(
        {"employee_id": seeded_users["emp2"]["employee_id"]},
        {"$set": {"date_of_birth": "1998-11-28", "department": "UI/UX Design"}}
    )

    tz = ZoneInfo("Asia/Kolkata")
    nov_first = datetime(2026, 11, 1, 9, 0, 0, tzinfo=tz)

    notif = BirthdayService.check_and_send_monthly_birthday_announcement(target_local_dt=nov_first)
    assert notif is not None
    assert "November" in notif["title"]
    assert "Core Engineering" in notif["message"]
    assert "1994" not in notif["message"]  # Birth year must NOT be exposed
    assert "1998" not in notif["message"]
    assert notif["recipient_group"] == "ALL"

    # Verify idempotency key prevents duplicate announcement
    duplicate = BirthdayService.check_and_send_monthly_birthday_announcement(target_local_dt=nov_first)
    # Count total monthly announcements in db
    count = db.notifications.count_documents({"idempotency_key": "bday_monthly_2026_11"})
    assert count == 1


def test_birthday_sanitized_calendar_api(db, seeded_users):
    """Sanitized calendar API must return name, department, day, and month, never birth year or full DOB."""
    emp_id = seeded_users["emp1"]["employee_id"]
    db.users.update_one(
        {"employee_id": emp_id},
        {"$set": {"date_of_birth": "1990-05-20", "department": "Product Dev"}}
    )

    birthdays = BirthdayService.get_monthly_birthdays(year=2026, month=5)
    assert len(birthdays) >= 1

    entry = [b for b in birthdays if b["employee_id"] == emp_id][0]
    assert entry["day"] == 20
    assert entry["month"] == 5
    assert entry["month_name"] == "May"
    assert entry["department"] == "Product Dev"
    assert "date_of_birth" not in entry
    assert "1990" not in str(entry)


def test_birthday_privacy_setting_honored(db, seeded_users):
    """Employees who opt out ('hide_birthday': True) must not receive public announcements."""
    emp_id = seeded_users["emp1"]["employee_id"]
    db.users.update_one(
        {"employee_id": emp_id},
        {"$set": {"date_of_birth": "1995-10-16", "hide_birthday": True}}
    )

    tz = ZoneInfo("Asia/Kolkata")
    test_dt = datetime(2026, 10, 16, 9, 0, 0, tzinfo=tz)

    notifs = BirthdayService.check_and_send_birthday_notifications(target_local_dt=test_dt)
    # Must not generate public greeting for opted-out employee
    matching = [n for n in notifs if n.get("recipient_id") == emp_id]
    assert len(matching) == 0


def test_inactive_employee_excluded_from_birthdays(db, seeded_users):
    """Deactivated accounts must never trigger birthday celebrations."""
    inactive_id = seeded_users["inactive"]["employee_id"]
    db.users.update_one(
        {"employee_id": inactive_id},
        {"$set": {"date_of_birth": "1992-10-16"}}
    )

    tz = ZoneInfo("Asia/Kolkata")
    test_dt = datetime(2026, 10, 16, 9, 0, 0, tzinfo=tz)

    notifs = BirthdayService.check_and_send_birthday_notifications(target_local_dt=test_dt)
    matching = [n for n in notifs if n.get("recipient_id") == inactive_id]
    assert len(matching) == 0


def test_external_email_simulation_and_audit_logging(db, seeded_users):
    """External email service safely logs delivery status as SIMULATED_NO_CREDENTIALS when unset."""
    emp = seeded_users["emp1"]
    res = ExternalNotificationService.send_email(
        recipient_email=emp["email"],
        subject="Welcome to AI Samrat Workplace",
        body="Your account is fully initialized and operational.",
        recipient_id=emp["employee_id"],
        category="ONBOARDING",
        idempotency_key="welcome_emp1_test"
    )

    assert res["status"] == "SIMULATED_NO_CREDENTIALS"
    assert res["channel"] == "EMAIL"
    assert res["recipient_id"] == emp["employee_id"]

    # Verify audit log in MongoDB
    log = db.external_message_logs.find_one({"idempotency_key": "welcome_emp1_test"})
    assert log is not None
    assert log["status"] == "SIMULATED_NO_CREDENTIALS"

    # Verify deduplication on re-send
    res2 = ExternalNotificationService.send_email(
        recipient_email=emp["email"],
        subject="Welcome to AI Samrat Workplace",
        body="Your account is fully initialized.",
        recipient_id=emp["employee_id"],
        category="ONBOARDING",
        idempotency_key="welcome_emp1_test"
    )
    assert res2["idempotency_key"] == "welcome_emp1_test"
    count = db.external_message_logs.count_documents({"idempotency_key": "welcome_emp1_test"})
    assert count == 1


def test_external_whatsapp_simulation_and_opt_out(db, seeded_users):
    """WhatsApp dispatch honors user opt-out preference."""
    emp = seeded_users["emp1"]
    # User opts out of WhatsApp alerts
    db.users.update_one(
        {"employee_id": emp["employee_id"]},
        {"$set": {"whatsapp_opt_in": False}}
    )

    res = ExternalNotificationService.send_whatsapp(
        recipient_phone="+919876543210",
        message="Your daily shift summary is ready.",
        recipient_id=emp["employee_id"],
        category="ATTENDANCE",
        idempotency_key="wa_shift_emp1"
    )

    assert res["status"] == "SKIPPED_OPT_OUT"
    assert "opted out" in res["failure_reason"].lower()


def test_external_notification_privacy_guard(db, seeded_users):
    """Attempting to dispatch confidential payroll or banking data externally must be blocked."""
    emp = seeded_users["emp1"]
    res = ExternalNotificationService.send_email(
        recipient_email=emp["email"],
        subject="Your Salary Slip and Net Pay Breakdown",
        body="Your salary for this month is credited to bank account 123456.",
        recipient_id=emp["employee_id"],
        category="PAYROLL",
        idempotency_key="forbidden_salary_email"
    )

    assert res["status"] == "BLOCKED_PRIVACY"
    assert "Confidential" in res["failure_reason"]

    # Verify that nothing was delivered
    log = db.external_message_logs.find_one({"idempotency_key": "forbidden_salary_email"})
    assert log["status"] == "BLOCKED_PRIVACY"
