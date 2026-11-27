from datetime import datetime
from zoneinfo import ZoneInfo
from backend.services.birthday_service import BirthdayService
from backend.database.connection import get_db


def test_birthday_notification_generated_on_date(db, seeded_users):
    """Birthday job must identify employees whose DOB matches local date in Asia/Kolkata."""
    # Set emp1's DOB to Oct 16
    db.users.update_one(
        {"employee_id": seeded_users["emp1"]["employee_id"]},
        {"$set": {"date_of_birth": "1995-10-16"}}
    )

    tz = ZoneInfo("Asia/Kolkata")
    test_dt = datetime(2026, 10, 16, 9, 0, 0, tzinfo=tz)

    notifs = BirthdayService.check_and_send_birthday_notifications(target_local_dt=test_dt)
    assert len(notifs) >= 1

    # Check notification in database
    notif = db.notifications.find_one({"idempotency_key": f"bday_{seeded_users['emp1']['employee_id']}_2026"})
    assert notif is not None
    assert notif["recipient_id"] == seeded_users["emp1"]["employee_id"]


def test_birthday_idempotency_prevents_duplicate(db, seeded_users):
    """Running birthday scan repeatedly on the same day must not create duplicate notifications."""
    emp_id = seeded_users["emp1"]["employee_id"]
    db.users.update_one(
        {"employee_id": emp_id},
        {"$set": {"date_of_birth": "1995-10-16"}}
    )

    tz = ZoneInfo("Asia/Kolkata")
    test_dt = datetime(2026, 10, 16, 9, 0, 0, tzinfo=tz)

    # First run
    BirthdayService.check_and_send_birthday_notifications(target_local_dt=test_dt)
    count1 = db.notifications.count_documents({"idempotency_key": f"bday_{emp_id}_2026"})

    # Second run
    BirthdayService.check_and_send_birthday_notifications(target_local_dt=test_dt)
    count2 = db.notifications.count_documents({"idempotency_key": f"bday_{emp_id}_2026"})

    assert count1 == 1
    assert count2 == 1


def test_leap_day_birthday_celebrated_on_feb_28_in_non_leap_year(db, seeded_users):
    """Employee born on Feb 29 celebrated on Feb 28 in non-leap year (e.g. 2026)."""
    emp_id = seeded_users["emp2"]["employee_id"]
    db.users.update_one(
        {"employee_id": emp_id},
        {"$set": {"date_of_birth": "1996-02-29"}}  # Leap baby
    )

    tz = ZoneInfo("Asia/Kolkata")
    # 2026 is a non-leap year
    feb_28 = datetime(2026, 2, 28, 9, 0, 0, tzinfo=tz)

    notifs = BirthdayService.check_and_send_birthday_notifications(target_local_dt=feb_28)
    assert len(notifs) >= 1

    notif = db.notifications.find_one({"idempotency_key": f"bday_{emp_id}_2026"})
    assert notif is not None
