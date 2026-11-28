import calendar
import logging
import re
from datetime import datetime
from database.connection import get_db
from utils.timezone import now_local, is_leap_year
from services.notification_service import NotificationService
from services.external_notification_service import ExternalNotificationService

logger = logging.getLogger(__name__)


def parse_dob(dob_str: str) -> tuple[int, int, int] | None:
    """
    Safely extracts (year, month, day) from either YYYY-MM-DD or DD-MM-YYYY format,
    handling real intern records (e.g., '13-08-2003') and standard seed records seamlessly.
    """
    if not dob_str:
        return None
    dob_str = str(dob_str).strip()
    parts = re.split(r"[-/.]", dob_str)
    if len(parts) != 3:
        return None
    try:
        p0, p1, p2 = int(parts[0]), int(parts[1]), int(parts[2])
        if p0 > 1900:  # YYYY-MM-DD
            return p0, p1, p2
        elif p2 > 1900:  # DD-MM-YYYY
            return p2, p1, p0
        else:
            return 2000, p1, p0
    except ValueError:
        return None


class BirthdayService:
    """
    Automated employee birthday system managing daily celebrations and monthly announcements.
    
    Privacy and Security Standards:
    - Never exposes birth year or full date of birth in company announcements or logs.
    - Honors user privacy preference ('hide_birthday': True).
    - Excludes inactive and archived employee accounts.
    - Idempotency guarantees zero duplicate notifications on repeated execution.
    - Consistent policy for Feb 29 birthdays: observed on Feb 28 during non-leap years.
    """

    @classmethod
    def get_monthly_birthdays(cls, year: int = None, month: int = None) -> list[dict]:
        """
        Retrieves sanitized list of active employees celebrating birthdays in the specified month.
        Only returns employee name, department, designation, day, and month.
        Never exposes birth year, age, or full date of birth.
        Excludes inactive and offboarded employees.
        """
        current_dt = now_local()
        target_year = year or current_dt.year
        target_month = month or current_dt.month

        db = get_db()
        active_users = list(db.users.find({
            "is_active": True,
            "employment_status": {"$nin": ["Offboarded", "Inactive", "Terminated", "Suspended"]},
            "$or": [
                {"date_of_birth": {"$ne": None, "$exists": True}},
                {"dob": {"$ne": None, "$exists": True}}
            ]
        }))

        monthly_celebrants = []
        for user in active_users:
            if user.get("hide_birthday"):
                continue

            dob_str = user.get("date_of_birth") or user.get("dob")
            parsed = parse_dob(dob_str)
            if not parsed:
                continue
            b_year, b_month, b_day = parsed

            if b_month == target_month:
                emp_id = user.get("employee_id") or user.get("emp_id")
                full_name = user.get("full_name") or user.get("name") or emp_id
                monthly_celebrants.append({
                    "employee_id": emp_id,
                    "emp_id": emp_id,
                    "full_name": full_name,
                    "name": full_name,
                    "department": user.get("department", "Corporate"),
                    "designation": user.get("designation", "Team Member"),
                    "role": user.get("role", "employee"),
                    "day": b_day,
                    "month": b_month,
                    "month_name": calendar.month_name[b_month],
                    "birthday_formatted": f"{calendar.month_name[b_month]} {b_day}"
                })

        monthly_celebrants.sort(key=lambda x: x["day"])
        return monthly_celebrants

    @classmethod
    def get_today_birthdays(cls, target_local_dt: datetime = None) -> list[dict]:
        """
        Retrieves sanitized list of active employees celebrating their birthday today in Asia/Kolkata.
        Includes Feb 29 leap day policy (observed on Feb 28 in non-leap years).
        Never exposes birth year or age.
        """
        current_dt = target_local_dt or now_local()
        current_year = current_dt.year
        current_month = current_dt.month
        current_day = current_dt.day
        leap = is_leap_year(current_year)

        db = get_db()
        active_users = list(db.users.find({
            "is_active": True,
            "employment_status": {"$nin": ["Offboarded", "Inactive", "Terminated", "Suspended"]},
            "$or": [
                {"date_of_birth": {"$ne": None, "$exists": True}},
                {"dob": {"$ne": None, "$exists": True}}
            ]
        }))

        today_celebrants = []
        for user in active_users:
            if user.get("hide_birthday"):
                continue

            dob_str = user.get("date_of_birth") or user.get("dob")
            parsed = parse_dob(dob_str)
            if not parsed:
                continue
            b_year, b_month, b_day = parsed

            is_today = False
            if b_month == current_month and b_day == current_day:
                is_today = True
            elif not leap and b_month == 2 and b_day == 29:
                if current_month == 2 and current_day == 28:
                    is_today = True

            if is_today:
                emp_id = user.get("employee_id") or user.get("emp_id")
                full_name = user.get("full_name") or user.get("name") or emp_id
                today_celebrants.append({
                    "employee_id": emp_id,
                    "emp_id": emp_id,
                    "full_name": full_name,
                    "name": full_name,
                    "department": user.get("department", "Corporate"),
                    "designation": user.get("designation", "Team Member"),
                    "role": user.get("role", "employee"),
                    "day": b_day,
                    "month": b_month,
                    "month_name": calendar.month_name[b_month],
                    "birthday_formatted": f"{calendar.month_name[b_month]} {b_day}"
                })

        today_celebrants.sort(key=lambda x: x["full_name"])
        return today_celebrants

    @classmethod
    def get_user_birthday_status(cls, user: dict, target_local_dt: datetime = None) -> dict:
        """
        Evaluates whether today is the authenticated user's birthday.
        Returns celebration metadata with personalized name, emoji, and celebration payload.
        """
        if not user:
            return {"is_birthday_today": False}

        current_dt = target_local_dt or now_local()
        current_year = current_dt.year
        current_month = current_dt.month
        current_day = current_dt.day
        leap = is_leap_year(current_year)

        dob_str = user.get("date_of_birth") or user.get("dob")
        parsed = parse_dob(dob_str)
        if not parsed:
            return {"is_birthday_today": False}

        b_year, b_month, b_day = parsed
        is_today = False
        if b_month == current_month and b_day == current_day:
            is_today = True
        elif not leap and b_month == 2 and b_day == 29:
            if current_month == 2 and current_day == 28:
                is_today = True

        full_name = user.get("full_name") or user.get("name") or "Colleague"
        emp_id = user.get("employee_id") or user.get("emp_id") or ""
        return {
            "is_birthday_today": is_today,
            "employee_id": emp_id,
            "full_name": full_name,
            "day": b_day,
            "month": b_month,
            "month_name": calendar.month_name[b_month],
            "greeting": f"Happy Birthday, {full_name}!",
            "message": "AI Samrat wishes you a glorious, healthy, and successful celebration!"
        }

    @classmethod
    def get_upcoming_birthdays(cls, target_local_dt: datetime = None, limit: int = 10) -> list[dict]:
        """
        Retrieves upcoming birthdays for active employees in the current month.
        Chronologically sorted with countdown days_until.
        """
        current_dt = target_local_dt or now_local()
        current_year = current_dt.year
        current_month = current_dt.month
        current_day = current_dt.day

        monthly = cls.get_monthly_birthdays(year=current_year, month=current_month)
        upcoming = []

        for c in monthly:
            b_day = c["day"]
            if b_day >= current_day:
                item = dict(c)
                item["days_until"] = b_day - current_day
                item["is_today"] = (b_day == current_day)
                upcoming.append(item)

        upcoming.sort(key=lambda x: x["day"])

        if len(upcoming) < limit:
            next_month = 1 if current_month == 12 else current_month + 1
            next_year = current_year + 1 if current_month == 12 else current_year
            next_monthly = cls.get_monthly_birthdays(year=next_year, month=next_month)
            days_in_current_month = calendar.monthrange(current_year, current_month)[1]
            days_left_in_cur_month = days_in_current_month - current_day
            for c in next_monthly:
                item = dict(c)
                item["days_until"] = days_left_in_cur_month + c["day"]
                item["is_today"] = False
                upcoming.append(item)
                if len(upcoming) >= limit:
                    break

        return upcoming[:limit]

    @classmethod
    def preview_monthly_announcement(cls, year: int = None, month: int = None) -> dict:
        """Generates a safe preview of the monthly announcement without saving or sending notifications."""
        current_dt = now_local()
        target_year = year or current_dt.year
        target_month = month or current_dt.month
        month_name = calendar.month_name[target_month]

        celebrants = cls.get_monthly_birthdays(year=target_year, month=target_month)
        lines = [
            f"• {c['full_name']} ({c['department']}) — {month_name} {c['day']}"
            for c in celebrants
        ]
        summary_text = "\n".join(lines) if lines else "No birthdays scheduled for this month."
        return {
            "month": target_month,
            "year": target_year,
            "month_name": month_name,
            "celebrants_count": len(celebrants),
            "celebrants": celebrants,
            "title": f"🎂 Upcoming Birthdays in {month_name}!",
            "preview_message": (
                f"We are excited to celebrate our colleagues having birthdays in {month_name}:\n\n"
                f"{summary_text}\n\n"
                f"Wishing everyone a wonderful month ahead!"
            ),
            "preview_body": (
                f"We are excited to celebrate our colleagues having birthdays in {month_name}:\n\n"
                f"{summary_text}\n\n"
                f"Wishing everyone a wonderful month ahead!"
            )
        }

    @classmethod
    def check_and_send_monthly_birthday_announcement(cls, target_local_dt: datetime = None, force: bool = False) -> dict | None:
        """
        Dispatches monthly birthday announcement on the first day of every month (or via catch-up).
        Notifies all active employees and summarizes all upcoming birthdays for the month.
        Directs users to /birthdays on click. Guaranteed zero duplicates via idempotency_key.
        """
        current_dt = target_local_dt or now_local()
        current_year = current_dt.year
        current_month = current_dt.month
        month_name = calendar.month_name[current_month]

        celebrants = cls.get_monthly_birthdays(year=current_year, month=current_month)
        if not celebrants:
            logger.info("No birthdays scheduled in %s %d.", month_name, current_year)
            return None

        # Build privacy-preserving summary (names, day, department only - NO birth year)
        lines = [
            f"• {c['full_name']} ({c['department']}) — {month_name} {c['day']}"
            for c in celebrants
        ]
        summary_text = "\n".join(lines)
        idempotency_key = f"bday_monthly_{current_year}_{current_month:02d}"

        db = get_db()
        if not force:
            existing = db.notifications.find_one({
                "$or": [
                    {"idempotency_key": idempotency_key},
                    {"reference_id": idempotency_key}
                ]
            })
            if existing:
                logger.info("Monthly birthday announcement already generated for %s %d.", month_name, current_year)
                return None

        # 1. Company-wide in-app announcement
        notif = NotificationService.create_notification(
            title=f"🎂 Upcoming Birthdays in {month_name}!",
            message=(
                f"We are excited to celebrate our colleagues having birthdays in {month_name}:\n\n"
                f"{summary_text}\n\n"
                f"Wishing everyone a wonderful month ahead!"
            ),
            category="ANNOUNCEMENT",
            recipient_group="ALL",
            link="/birthdays",
            reference_id=idempotency_key,
            idempotency_key=None if force else idempotency_key,
            priority="NORMAL"
        )

        # 2. External email announcement dispatch (fail-safe)
        try:
            db = get_db()
            all_active = list(db.users.find({
                "is_active": True,
                "employment_status": {"$nin": ["Offboarded", "Inactive", "Terminated", "Suspended"]}
            }, {"employee_id": 1, "full_name": 1, "email": 1}))
            ExternalNotificationService.dispatch_monthly_announcement(
                monthly_summary=summary_text,
                all_active_users=all_active,
                year=current_year,
                month=current_month
            )
        except Exception as e:
            logger.warning("External monthly announcement dispatch failed: %s", e)

        logger.info("Monthly birthday announcement dispatched for %s %d (%d celebrants).", month_name, current_year, len(celebrants))
        return notif

    @classmethod
    def check_and_send_birthday_notifications(cls, target_local_dt: datetime = None, force: bool = False) -> list:
        """
        Evaluates daily birthdays at 9:00 AM Asia/Kolkata.
        Dispatches personal greetings and company-wide announcements with idempotency.
        """
        current_dt = target_local_dt or now_local()
        current_year = current_dt.year
        current_month = current_dt.month
        current_day = current_dt.day
        leap = is_leap_year(current_year)

        db = get_db()
        active_users = list(db.users.find({
            "is_active": True,
            "employment_status": {"$nin": ["Offboarded", "Inactive", "Terminated", "Suspended"]},
            "date_of_birth": {"$ne": None, "$exists": True}
        }))

        generated_notifications = []

        for user in active_users:
            if user.get("hide_birthday"):
                continue

            dob_str = user.get("date_of_birth")
            if not dob_str or len(dob_str) != 10:
                continue

            try:
                b_year, b_month, b_day = map(int, dob_str.split("-"))
            except ValueError:
                continue

            is_birthday_today = False

            if b_month == current_month and b_day == current_day:
                is_birthday_today = True
            elif not leap and b_month == 2 and b_day == 29:
                # Documented policy: Leap day babies celebrated on Feb 28 in non-leap years
                if current_month == 2 and current_day == 28:
                    is_birthday_today = True

            if is_birthday_today:
                emp_id = user["employee_id"]
                full_name = user.get("full_name", "Valued Colleague")
                dept = user.get("department", "Team")
                today_str = current_dt.strftime("%Y-%m-%d")
                idempotency_key = f"bday_{emp_id}_{current_year}"
                personal_ref = f"bday_personal_{emp_id}_{today_str}"
                group_idempotency_key = f"bday_announcement_{emp_id}_{current_year}"
                group_ref = f"bday_company_{emp_id}_{today_str}"

                if not force:
                    existing_personal = db.notifications.find_one({
                        "$or": [
                            {"idempotency_key": idempotency_key},
                            {"reference_id": personal_ref}
                        ]
                    })
                    if existing_personal:
                        logger.info("Birthday greeting already dispatched today for %s (%s).", full_name, emp_id)
                        continue

                # 1. Personal Happy Birthday greeting
                personal_notif = NotificationService.create_notification(
                    title="🎉 Happy Birthday!",
                    message=f"Happy Birthday, {full_name}! Wishing you a wonderful year ahead filled with success, good health, and happiness.",
                    category="BIRTHDAY",
                    recipient_id=emp_id,
                    link="/birthdays",
                    reference_id=personal_ref,
                    idempotency_key=None if force else idempotency_key,
                    priority="HIGH"
                )

                # 2. Company-wide birthday announcement
                group_notif = NotificationService.create_notification(
                    title=f"🎂 Celebrating {full_name}'s Birthday Today!",
                    message=f"Please join us in wishing {full_name} ({dept}) a very Happy Birthday today!",
                    category="ANNOUNCEMENT",
                    recipient_group="ALL",
                    link="/birthdays",
                    reference_id=group_ref,
                    idempotency_key=None if force else group_idempotency_key,
                    priority="NORMAL"
                )

                # 3. External Email and WhatsApp dispatch (fail-safe)
                try:
                    ExternalNotificationService.dispatch_birthday_greeting(user, target_year=current_year)
                    ExternalNotificationService.dispatch_birthday_announcement(
                        celebrating_user=user,
                        all_active_users=active_users,
                        target_year=current_year
                    )
                except Exception as ext_err:
                    logger.warning("External birthday dispatch encountered an error: %s", ext_err)

                if personal_notif:
                    generated_notifications.append(personal_notif)
                if group_notif:
                    generated_notifications.append(group_notif)
                logger.info("Generated birthday greeting for %s (%s)", full_name, emp_id)

        return generated_notifications

    @classmethod
    def run_startup_catchup(cls, target_local_dt: datetime = None):
        """
        Runs on server boot to ensure missed announcements or birthday greetings
        are safely dispatched without duplicating.
        """
        try:
            current_dt = target_local_dt or now_local()
            # If current month's monthly announcement hasn't been created yet, create it!
            key = f"bday_monthly_{current_dt.year}_{current_dt.month:02d}"
            db = get_db()
            existing = db.notifications.find_one({
                "$or": [
                    {"idempotency_key": key},
                    {"reference_id": key}
                ]
            })
            if not existing:
                logger.info("Startup Catch-up: Generating monthly birthday announcement for %s %d...",
                            calendar.month_name[current_dt.month], current_dt.year)
                cls.check_and_send_monthly_birthday_announcement(target_local_dt=current_dt)

            # If current local time is past 9:00 AM IST, ensure today's birthday notifications are checked
            if current_dt.hour >= 9:
                cls.check_and_send_birthday_notifications(target_local_dt=current_dt)
        except Exception as e:
            logger.warning("Error running birthday startup catch-up: %s", e)
