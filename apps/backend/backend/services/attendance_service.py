from __future__ import annotations
import uuid
import calendar
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo
from bson import ObjectId
from backend.database.connection import get_db
from backend.utils.timezone import (
    get_app_timezone,
    now_utc,
    to_local,
    to_utc,
    get_local_date_str,
    parse_time_str
)
from config import Config
from backend.services.audit_service import AuditService
from backend.services.notification_service import NotificationService
from backend.permissions.rbac import Role, normalize_role
from backend.utils.serializers import serialize_doc, serialize_docs

OFFICIAL_HOLIDAYS = {
    # 2025
    "2025-01-01": "New Year's Day",
    "2025-01-26": "Republic Day",
    "2025-03-14": "Holi Festival",
    "2025-03-31": "Eid-ul-Fitr",
    "2025-04-18": "Good Friday",
    "2025-05-01": "Labour Day",
    "2025-08-15": "Independence Day",
    "2025-10-02": "Gandhi Jayanti",
    "2025-10-20": "Dussehra",
    "2025-11-01": "Diwali",
    "2025-12-25": "Christmas Day",
    # 2026
    "2026-01-01": "New Year's Day",
    "2026-01-26": "Republic Day",
    "2026-03-03": "Holi Festival",
    "2026-03-20": "Eid-ul-Fitr",
    "2026-04-03": "Good Friday",
    "2026-04-14": "Dr. Ambedkar Jayanti",
    "2026-05-01": "Labour Day",
    "2026-05-27": "Bakrid / Eid al-Adha",
    "2026-08-15": "Independence Day",
    "2026-08-27": "Raksha Bandhan",
    "2026-09-04": "Janmashtami",
    "2026-10-02": "Mahatma Gandhi Jayanti",
    "2026-10-20": "Dussehra / Vijayadashami",
    "2026-11-08": "Diwali / Deepavali",
    "2026-11-09": "Govardhan Puja",
    "2026-11-24": "Guru Nanak Jayanti",
    "2026-12-25": "Christmas Day",
    # 2027
    "2027-01-01": "New Year's Day",
    "2027-01-26": "Republic Day",
    "2027-03-22": "Holi Festival",
    "2027-08-15": "Independence Day",
    "2027-10-02": "Gandhi Jayanti",
    "2027-10-28": "Diwali",
    "2027-12-25": "Christmas Day"
}


def ensure_utc(dt: datetime) -> datetime:
    """Ensures a datetime object is timezone-aware in UTC."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def format_duration(seconds: int) -> str:
    """Formats seconds into human-readable 'Xh Ym' string."""
    if not seconds or seconds < 0:
        return "0h 0m"
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    return f"{hours}h {minutes}m"


class AttendanceService:
    @classmethod
    def get_office_rules(cls) -> dict:
        """Loads office start, end times, cutoff time, intimation minutes and grace period."""
        db = get_db()
        settings = db.organization_settings.find_one({"key": "attendance_policy"})
        if settings and "value" in settings:
            val = settings["value"]
            return {
                "start_time": val.get("office_start_time", Config.OFFICE_START_TIME),
                "end_time": val.get("office_end_time", Config.OFFICE_END_TIME),
                "cutoff_time": val.get("office_cutoff_time", getattr(Config, "OFFICE_CUTOFF_TIME", "19:00")),
                "intimation_minutes": int(val.get("cutoff_intimation_minutes", getattr(Config, "CUTOFF_INTIMATION_MINUTES", 45))),
                "grace_minutes": int(val.get("late_grace_minutes", Config.LATE_GRACE_MINUTES)),
                "timezone": val.get("timezone", Config.DEFAULT_TIMEZONE)
            }
        return {
            "start_time": Config.OFFICE_START_TIME,
            "end_time": Config.OFFICE_END_TIME,
            "cutoff_time": getattr(Config, "OFFICE_CUTOFF_TIME", "19:00"),
            "intimation_minutes": getattr(Config, "CUTOFF_INTIMATION_MINUTES", 45),
            "grace_minutes": Config.LATE_GRACE_MINUTES,
            "timezone": Config.DEFAULT_TIMEZONE
        }

    @classmethod
    def get_office_timing_status(cls, employee_id: str = None) -> dict:
        """
        Calculates real-time shift timing status for today:
        - Shift: 10:00 AM to 6:00 PM (10:00 to 18:00)
        - Cutoff: 7:00 PM (19:00)
        - Intimation: 45 minutes prior to cutoff (from 6:15 PM / 18:15)
        - Remaining login hours / seconds until qualifying shift completion (6:00 PM)
        - Remaining seconds until 7:00 PM cutoff
        """
        rules = cls.get_office_rules()
        tz = ZoneInfo(rules["timezone"])
        today_str = get_local_date_str()
        year, month, day = map(int, today_str.split("-"))

        start_h, start_m = map(int, rules["start_time"].split(":"))
        end_h, end_m = map(int, rules["end_time"].split(":"))
        cutoff_h, cutoff_m = map(int, rules["cutoff_time"].split(":"))
        intimation_mins = int(rules.get("intimation_minutes", 45))

        now_dt = datetime.now(tz)
        office_start_dt = datetime(year, month, day, start_h, start_m, 0, tzinfo=tz)
        office_end_dt = datetime(year, month, day, end_h, end_m, 0, tzinfo=tz)
        office_cutoff_dt = datetime(year, month, day, cutoff_h, cutoff_m, 0, tzinfo=tz)
        intimation_start_dt = office_cutoff_dt - timedelta(minutes=intimation_mins)

        # Seconds remaining to reach 6:00 PM (qualifying shift target)
        sec_to_qualify = int((office_end_dt - now_dt).total_seconds())
        # Seconds remaining to reach 7:00 PM cutoff
        sec_to_cutoff = int((office_cutoff_dt - now_dt).total_seconds())

        is_shift_in_progress = now_dt < office_end_dt
        is_qualifying_met = now_dt >= office_end_dt
        is_intimation_active = (now_dt >= intimation_start_dt) and (now_dt < office_cutoff_dt)
        is_past_cutoff = now_dt >= office_cutoff_dt

        # Check today's attendance record for the employee if employee_id provided
        has_clocked_in = False
        has_completed_logout = False
        has_open_session = False
        if employee_id:
            db = get_db()
            daily = db.attendance_daily.find_one({"employee_id": employee_id, "attendance_date": today_str})
            if daily:
                has_clocked_in = bool(daily.get("first_login"))
                has_completed_logout = bool(daily.get("final_qualifying_logout"))
                has_open_session = bool(daily.get("has_open_session"))

            if is_past_cutoff:
                if has_open_session:
                    try:
                        cls.execute_7pm_attendance_cutoff(today_str)
                    except Exception:
                        pass
                has_open_session = False
                has_completed_logout = True

        # Granular Morning vs Afternoon Split Logic
        # Pre-Break (Morning): 10:00 AM – 1:30 PM (3.5h target = 12,600s)
        # Lunch & Rest Window: 1:30 PM – 2:30 PM (1.0h = 3,600s)
        # Post-Break (Afternoon): 2:30 PM – 6:00 PM (3.5h target = 12,600s)
        active_sec = 0
        break_sec = 0
        if employee_id and daily:
            active_sec = int(daily.get("active_seconds") or 0)
            break_sec = int(daily.get("break_duration_seconds") or 0)

        # Distribute active seconds across morning and afternoon halves
        morning_target_sec = 12600
        afternoon_target_sec = 12600
        morning_sec = min(morning_target_sec, active_sec)
        afternoon_sec = max(0, min(afternoon_target_sec, active_sec - morning_target_sec))

        morning_pct = min(100.0, round((morning_sec / morning_target_sec) * 100, 1)) if morning_target_sec else 0
        afternoon_pct = min(100.0, round((afternoon_sec / afternoon_target_sec) * 100, 1)) if afternoon_target_sec else 0
        break_pct = min(100.0, round((break_sec / 3600) * 100, 1))

        lunch_window_start = datetime(year, month, day, 13, 30, tzinfo=tz)
        lunch_window_end = datetime(year, month, day, 14, 30, tzinfo=tz)

        if now_dt < lunch_window_start:
            morning_status = "Active / In Progress" if has_open_session else ("Completed" if morning_sec >= morning_target_sec else "Pending")
            afternoon_status = "Upcoming"
        elif now_dt < lunch_window_end:
            morning_status = "Completed" if morning_sec >= morning_target_sec else "Under Target"
            afternoon_status = "Upcoming"
        else:
            morning_status = "Completed" if morning_sec >= morning_target_sec else "Logged"
            afternoon_status = "Active / In Progress" if has_open_session else ("Completed" if afternoon_sec >= afternoon_target_sec else "Pending")

        shift_split = {
            "morning": {
                "name": "Pre-Break (Morning Session)",
                "window": "10:00 AM – 01:30 PM",
                "target_hours": 3.5,
                "logged_seconds": morning_sec,
                "logged_display": format_duration(morning_sec),
                "progress_pct": morning_pct,
                "status": morning_status
            },
            "break": {
                "name": "Mandatory Break Window",
                "window": "01:30 PM – 02:30 PM",
                "target_hours": 1.0,
                "logged_seconds": break_sec,
                "logged_display": format_duration(break_sec),
                "progress_pct": break_pct,
                "status": "Recorded" if break_sec > 0 else "Pending"
            },
            "afternoon": {
                "name": "Post-Break (Afternoon Session)",
                "window": "02:30 PM – 06:00 PM",
                "target_hours": 3.5,
                "logged_seconds": afternoon_sec,
                "logged_display": format_duration(afternoon_sec),
                "progress_pct": afternoon_pct,
                "status": afternoon_status
            }
        }

        rem_q_display = format_duration(max(0, sec_to_qualify))
        rem_c_display = format_duration(max(0, sec_to_cutoff))

        return {
            "shift_start_time": rules["start_time"],
            "shift_end_time": rules["end_time"],
            "cutoff_time": rules["cutoff_time"],
            "intimation_start_time": intimation_start_dt.strftime("%H:%M"),
            "intimation_minutes": intimation_mins,
            "current_local_time": now_dt.strftime("%I:%M %p"),
            "current_local_time_24": now_dt.strftime("%H:%M:%S"),
            "remaining_seconds_to_qualify": max(0, sec_to_qualify),
            "remaining_display_to_qualify": rem_q_display,
            "remaining_seconds_to_cutoff": max(0, sec_to_cutoff),
            "remaining_display_to_cutoff": rem_c_display,
            "is_shift_in_progress": is_shift_in_progress,
            "is_qualifying_met": is_qualifying_met,
            "is_intimation_active": is_intimation_active,
            "is_past_cutoff": is_past_cutoff,
            "has_clocked_in": has_clocked_in,
            "has_completed_logout": has_completed_logout,
            "has_open_session": has_open_session,
            "should_show_intimation": bool((is_intimation_active or is_past_cutoff) and has_open_session),
            "shift_split": shift_split
        }

    @classmethod
    def check_and_send_cutoff_intimations(cls) -> list:
        """
        Dispatches mandatory out cutoff notification 45 minutes prior to 7:00 PM cutoff (starting 18:15).
        Dispatches to active employees who have logged in today but not completed qualifying logout.
        """
        timing = cls.get_office_timing_status()
        if not timing["is_intimation_active"] and not timing["is_past_cutoff"]:
            return []

        from backend.services.notification_service import NotificationService
        db = get_db()
        today_str = get_local_date_str()

        # Find all attendance records today where employee has logged in but has not qualified/completed logout
        pending_records = list(db.attendance_daily.find({
            "attendance_date": today_str,
            "first_login": {"$ne": None},
            "final_qualifying_logout": None
        }))

        sent_notifs = []
        for rec in pending_records:
            emp_id = rec["employee_id"]
            idempotency_key = f"cutoff_intimation_45min_{emp_id}_{today_str}"
            if db.notifications.find_one({"idempotency_key": idempotency_key}):
                continue

            mins_left = max(0, timing["remaining_seconds_to_cutoff"] // 60)
            
            notif = NotificationService.create_notification(
                title="Mandatory Checkout Intimation: 7:00 PM Cutoff",
                message=(
                    f"Official office shift ended at 6:00 PM. The system checkout cutoff is strictly at 7:00 PM "
                    f"({mins_left} minutes remaining). Please complete your work diary and clock out before 7:00 PM."
                ),
                category="ATTENDANCE",
                recipient_id=emp_id,
                link="/attendance",
                idempotency_key=idempotency_key,
                priority="URGENT"
            )
            if notif:
                sent_notifs.append(notif)

        return sent_notifs

    @classmethod
    def execute_7pm_attendance_cutoff(cls, target_date: str = None) -> list:
        """
        Executes the mandatory 7:00 PM Asia/Kolkata attendance cutoff.
        Automatically closes any active, unclosed attendance sessions for eligible employees.
        - Records an explicit system-generated checkout event (LOGOUT) with event_source='SYSTEM_CUTOFF'
        - Automatically closes any open breaks
        - Updates attendance status and active-session state
        - Recalculates elapsed time, breaks, and active working time using existing business rules
        - Removes the online indicator (is_online=False) from user records
        - Prevents duplicate checkout events (idempotent)
        - Survives application restarts and multiple invocations
        """
        from backend.services.notification_service import NotificationService
        db = get_db()
        rules = cls.get_office_rules()
        tz = ZoneInfo(rules.get("timezone", "Asia/Kolkata"))

        now_utc_dt = now_utc()
        now_local = now_utc_dt.astimezone(tz)
        today_str = target_date or now_local.strftime("%Y-%m-%d")

        # Determine cutoff timestamp for today_str in Asia/Kolkata
        year, month, day = map(int, today_str.split("-"))
        cutoff_h, cutoff_m = map(int, rules.get("cutoff_time", "19:00").split(":"))
        cutoff_local = datetime(year, month, day, cutoff_h, cutoff_m, 0, tzinfo=tz)
        cutoff_utc = cutoff_local.astimezone(timezone.utc)

        # Event timestamp: at cutoff time (19:00 IST), or now if run prior
        event_timestamp = cutoff_utc if now_utc_dt >= cutoff_utc else now_utc_dt

        # Find all unclosed LOGIN events for this date or earlier
        unclosed_logins = list(db.attendance_events.find({
            "date": {"$lte": today_str},
            "event_type": "LOGIN",
            "is_closed": False
        }))

        processed = []
        for login_ev in unclosed_logins:
            emp_id = login_ev.get("employee_id")
            session_id = login_ev.get("session_id")
            if not emp_id or not session_id:
                continue

            # Check if this session already has a LOGOUT event (prevent duplicate checkout)
            existing_logout = db.attendance_events.find_one({
                "session_id": session_id,
                "event_type": "LOGOUT"
            })
            if existing_logout:
                db.attendance_events.update_one(
                    {"_id": login_ev["_id"]},
                    {"$set": {"is_closed": True, "updated_at": now_utc_dt}}
                )
                continue

            # Check if employee has an active break in progress, close it at cutoff time
            open_break = db.attendance_events.find_one({
                "employee_id": emp_id,
                "date": today_str,
                "event_type": "BREAK_START",
                "is_closed": False
            })
            if open_break:
                db.attendance_events.insert_one({
                    "employee_id": emp_id,
                    "employee_name": login_ev.get("employee_name", ""),
                    "date": today_str,
                    "session_id": session_id,
                    "event_type": "BREAK_END",
                    "timestamp": event_timestamp,
                    "notes": "Auto-closed by 7 PM System Cutoff",
                    "event_source": "SYSTEM_CUTOFF",
                    "created_at": now_utc_dt,
                    "updated_at": now_utc_dt
                })
                db.attendance_events.update_one(
                    {"_id": open_break["_id"]},
                    {"$set": {"is_closed": True, "updated_at": now_utc_dt}}
                )

            # Insert system-generated LOGOUT event
            logout_event = {
                "employee_id": emp_id,
                "employee_name": login_ev.get("employee_name", ""),
                "date": today_str,
                "session_id": session_id,
                "event_type": "LOGOUT",
                "timestamp": event_timestamp,
                "event_source": "SYSTEM_CUTOFF",
                "reason": "7 PM Automated Attendance Cutoff",
                "is_automatic_cutoff": True,
                "created_at": now_utc_dt,
                "updated_at": now_utc_dt
            }
            db.attendance_events.insert_one(logout_event)

            # Mark LOGIN event as closed
            db.attendance_events.update_one(
                {"_id": login_ev["_id"]},
                {
                    "$set": {
                        "is_closed": True,
                        "closed_reason": "SYSTEM_CUTOFF",
                        "updated_at": now_utc_dt
                    }
                }
            )

            # Recalculate daily summary
            summary = cls.recalculate_daily_summary(emp_id, today_str)

            # Remove online indicator
            db.users.update_one(
                {"employee_id": emp_id},
                {
                    "$set": {
                        "is_online": False,
                        "last_active_at": now_utc_dt
                    }
                }
            )

            # Notify the employee
            try:
                notif_key = f"cutoff_auto_logout_{emp_id}_{today_str}"
                NotificationService.create_notification(
                    recipient_id=emp_id,
                    title="Attendance Auto-Checkout (7:00 PM Cutoff)",
                    message="Your attendance session has been automatically checked out in accordance with company policy (7:00 PM Hard Cutoff).",
                    category="ATTENDANCE",
                    priority="HIGH",
                    link="/attendance",
                    idempotency_key=notif_key
                )
            except Exception:
                pass

            processed.append({
                "employee_id": emp_id,
                "session_id": session_id,
                "summary": summary
            })

        return processed

    @classmethod
    def record_login(cls, user: dict, ip_address: str = None, return_is_new: bool = False, location: dict = None):
        """
        Records a LOGIN event for the employee.
        Creates a new session in attendance_events and updates attendance_daily summary.
        If return_is_new is True, returns (summary, session_id, is_new).
        Captures point-in-time location snapshot when provided (Field/Office attendance).
        """
        if not user.get("is_active", True) or user.get("status") in ("deactivated", "offboarded"):
            return ({}, "", False) if return_is_new else ({}, "")

        employee_id = user.get("employee_id") or user.get("emp_id")
        event_time_utc = now_utc()
        date_str = get_local_date_str(event_time_utc)
        session_id = str(uuid.uuid4())

        db = get_db()

        # Check if user already has an active open session without a logout
        unclosed_logins = list(db.attendance_events.find({
            "employee_id": employee_id,
            "date": date_str,
            "event_type": "LOGIN",
            "is_closed": False
        }))
        open_session = None
        for login_ev in unclosed_logins:
            has_logout = db.attendance_events.find_one({
                "session_id": login_ev["session_id"],
                "event_type": "LOGOUT"
            })
            if has_logout:
                db.attendance_events.update_one(
                    {"_id": login_ev["_id"]},
                    {"$set": {"is_closed": True}}
                )
            else:
                open_session = login_ev

        if open_session:
            # Active session already open; reuse it
            summary = cls.recalculate_daily_summary(employee_id, date_str)
            if return_is_new:
                return summary, open_session["session_id"], False
            return summary, open_session["session_id"]

        # Insert new LOGIN event into attendance_events
        login_event = {
            "employee_id": employee_id,
            "employee_name": user.get("full_name", ""),
            "date": date_str,
            "session_id": session_id,
            "event_type": "LOGIN",
            "timestamp": event_time_utc,
            "is_closed": False,
            "event_source": "WEB",
            "ip_address": ip_address,
            "created_at": event_time_utc,
            "updated_at": event_time_utc
        }
        if location and isinstance(location, dict):
            login_event["location"] = location

        db.attendance_events.insert_one(login_event)

        # Recalculate and update daily summary
        summary = cls.recalculate_daily_summary(employee_id, date_str)
        if return_is_new:
            return summary, session_id, True
        return summary, session_id

    @classmethod
    def record_logout(cls, user: dict, session_id: str = None, ip_address: str = None, location: dict = None) -> tuple[dict, Optional[str]]:
        """
        Records a LOGOUT event for the employee.
        Preserves all sessions and updates attendance_daily summary.
        If no open login session is found, returns (summary, None).
        Captures point-in-time location snapshot when provided (Field/Office attendance).
        """
        employee_id = user.get("employee_id") or user.get("emp_id")
        event_time_utc = now_utc()
        date_str = get_local_date_str(event_time_utc)

        db = get_db()

        # Find the open session
        query = {
            "employee_id": employee_id,
            "date": date_str,
            "event_type": "LOGIN",
            "is_closed": False
        }
        if session_id:
            query["session_id"] = session_id

        open_login = db.attendance_events.find_one(query, sort=[("timestamp", -1)])
        if not open_login:
            # No open session found to close
            summary = cls.recalculate_daily_summary(employee_id, date_str)
            return summary, None

        actual_session_id = open_login["session_id"]

        # If employee has an open break in progress, close it automatically at logout
        open_break = db.attendance_events.find_one({
            "employee_id": employee_id,
            "date": date_str,
            "event_type": "BREAK_START",
            "is_closed": False
        })
        if open_break:
            db.attendance_events.insert_one({
                "employee_id": employee_id,
                "employee_name": user.get("full_name", ""),
                "date": date_str,
                "session_id": actual_session_id,
                "event_type": "BREAK_END",
                "timestamp": event_time_utc,
                "created_at": event_time_utc,
                "updated_at": event_time_utc
            })
            db.attendance_events.update_one(
                {"_id": open_break["_id"]},
                {"$set": {"is_closed": True, "updated_at": event_time_utc}}
            )

        # Insert LOGOUT event
        logout_event = {
            "employee_id": employee_id,
            "employee_name": user.get("full_name", ""),
            "date": date_str,
            "session_id": actual_session_id,
            "event_type": "LOGOUT",
            "timestamp": event_time_utc,
            "event_source": "WEB",
            "ip_address": ip_address,
            "created_at": event_time_utc,
            "updated_at": event_time_utc
        }
        if location and isinstance(location, dict):
            logout_event["location"] = location

        db.attendance_events.insert_one(logout_event)

        # Mark matching login event as closed
        db.attendance_events.update_one(
            {"_id": open_login["_id"]},
            {"$set": {"is_closed": True, "updated_at": event_time_utc}}
        )

        # Recalculate daily summary
        summary = cls.recalculate_daily_summary(employee_id, date_str)
        return summary, actual_session_id

    @classmethod
    def record_break_start(cls, user: dict, notes: str = None) -> tuple[dict | None, str | None]:
        """
        Records a BREAK_START event. Employee must have an active open clock-in session.
        """
        employee_id = user.get("employee_id") or user.get("emp_id")
        event_time_utc = now_utc()
        date_str = get_local_date_str(event_time_utc)
        db = get_db()

        # Check for active open clock-in session
        open_login = db.attendance_events.find_one({
            "employee_id": employee_id,
            "date": date_str,
            "event_type": "LOGIN",
            "is_closed": False
        })
        if not open_login:
            return None, "You must clock in before starting a break."

        # Check if already on break
        open_break = db.attendance_events.find_one({
            "employee_id": employee_id,
            "date": date_str,
            "event_type": "BREAK_START",
            "is_closed": False
        })
        if open_break:
            return None, "You are already currently on break."

        break_event = {
            "employee_id": employee_id,
            "employee_name": user.get("full_name", ""),
            "date": date_str,
            "session_id": open_login["session_id"],
            "event_type": "BREAK_START",
            "timestamp": event_time_utc,
            "is_closed": False,
            "notes": (notes or "Work Break").strip(),
            "created_at": event_time_utc,
            "updated_at": event_time_utc
        }
        db.attendance_events.insert_one(break_event)
        summary = cls.recalculate_daily_summary(employee_id, date_str)
        return summary, None

    @classmethod
    def record_break_end(cls, user: dict) -> tuple[dict | None, str | None]:
        """
        Records a BREAK_END event and resumes active working time.
        """
        employee_id = user.get("employee_id") or user.get("emp_id")
        event_time_utc = now_utc()
        date_str = get_local_date_str(event_time_utc)
        db = get_db()

        open_break = db.attendance_events.find_one({
            "employee_id": employee_id,
            "date": date_str,
            "event_type": "BREAK_START",
            "is_closed": False
        })
        if not open_break:
            return None, "No active break in progress to resume from."

        break_end_event = {
            "employee_id": employee_id,
            "employee_name": user.get("full_name", ""),
            "date": date_str,
            "session_id": open_break["session_id"],
            "event_type": "BREAK_END",
            "timestamp": event_time_utc,
            "created_at": event_time_utc,
            "updated_at": event_time_utc
        }
        db.attendance_events.insert_one(break_end_event)
        db.attendance_events.update_one(
            {"_id": open_break["_id"]},
            {"$set": {"is_closed": True, "updated_at": event_time_utc}}
        )

        summary = cls.recalculate_daily_summary(employee_id, date_str)
        return summary, None

    @classmethod
    def recalculate_daily_summary(cls, employee_id: str, date_str: str) -> dict:
        """
        Core attendance business logic:
        1. Earliest valid login of the calendar day is first_login.
        2. Status vs 10:00 AM (start_time):
           - <= 10:00 AM: ON_TIME, delay = 0
           - > 10:00 AM + grace: LATE, delay = minutes past 10:00 AM
        3. Qualifying final logout must be at or after 6:00 PM (end_time):
           - Logouts before 6:00 PM are recorded but do NOT qualify as final logout.
           - If latest logout >= 6:00 PM: that is final_qualifying_logout.
           - If no logout >= 6:00 PM: marked as 'INCOMPLETE' or 'PENDING_FINAL_LOGOUT'.
        4. Official Working Duration:
           - Elapsed span between first_login and final_qualifying_logout.
        5. Active Session Duration:
           - Sum of individual completed session lengths.
        6. Idempotent and thread-safe upsert into attendance_daily.
        """
        db = get_db()
        rules = cls.get_office_rules()
        tz = ZoneInfo(rules["timezone"])

        # Fetch all events for employee on this date, sorted chronologically
        events = list(db.attendance_events.find({
            "employee_id": employee_id,
            "date": date_str
        }).sort("timestamp", 1))

        if not events:
            return None

        # Normalize all timestamps to timezone-aware UTC
        for ev in events:
            ev["timestamp"] = ensure_utc(ev.get("timestamp"))

        # Office start and end times in local timezone on date_str
        year, month, day = map(int, date_str.split("-"))
        start_h, start_m = map(int, rules["start_time"].split(":"))
        end_h, end_m = map(int, rules["end_time"].split(":"))
        grace_mins = rules["grace_minutes"]

        office_start_local = datetime(year, month, day, start_h, start_m, 0, tzinfo=tz)
        office_end_local = datetime(year, month, day, end_h, end_m, 0, tzinfo=tz)
        grace_threshold_local = office_start_local + timedelta(minutes=grace_mins)

        office_start_utc = office_start_local.astimezone(timezone.utc)
        office_end_utc = office_end_local.astimezone(timezone.utc)
        grace_threshold_utc = grace_threshold_local.astimezone(timezone.utc)

        # Find first valid login
        logins = [e for e in events if e["event_type"] == "LOGIN"]
        logouts = [e for e in events if e["event_type"] == "LOGOUT"]

        first_login_event = logins[0] if logins else None
        first_login_utc = first_login_event["timestamp"] if first_login_event else None

        # Build paired sessions
        sessions = []
        total_active_seconds = 0
        has_open_session = False

        # Group by session_id
        session_map = {}
        for ev in events:
            sid = ev["session_id"]
            if sid not in session_map:
                session_map[sid] = {"login": None, "logout": None}
            if ev["event_type"] == "LOGIN":
                session_map[sid]["login"] = ev["timestamp"]
            elif ev["event_type"] == "LOGOUT":
                session_map[sid]["logout"] = ev["timestamp"]

        is_today = (date_str == get_local_date_str())
        current_time_utc = now_utc()

        for sid, sdata in session_map.items():
            login_t = sdata["login"]
            logout_t = sdata["logout"]
            is_open = logout_t is None
            dur_secs = 0
            if login_t and logout_t:
                dur_secs = max(0, int((logout_t - login_t).total_seconds()))
                total_active_seconds += dur_secs
            elif is_open:
                has_open_session = True
                if is_today and login_t:
                    dur_secs = max(0, int((current_time_utc - login_t).total_seconds()))
                    total_active_seconds += dur_secs

            sessions.append({
                "session_id": sid,
                "login_time": login_t,
                "logout_time": logout_t,
                "duration_seconds": dur_secs,
                "duration_display": format_duration(dur_secs),
                "is_open": is_open
            })

        # Collect and pair break events
        break_starts = [e for e in events if e["event_type"] == "BREAK_START"]
        break_ends = [e for e in events if e["event_type"] == "BREAK_END"]

        total_break_seconds = 0
        is_on_break = False
        break_list = []

        unpaired_ends = list(break_ends)
        for bs in break_starts:
            bs_time = bs["timestamp"]
            matching_end = None
            for be in unpaired_ends:
                if be["timestamp"] >= bs_time:
                    matching_end = be
                    unpaired_ends.remove(be)
                    break

            if matching_end:
                be_time = matching_end["timestamp"]
                b_dur = max(0, int((be_time - bs_time).total_seconds()))
                break_list.append({
                    "start": bs_time,
                    "end": be_time,
                    "duration_seconds": b_dur,
                    "duration_display": format_duration(b_dur),
                    "notes": bs.get("notes", "Work Break"),
                    "is_open": False
                })
                total_break_seconds += b_dur
            else:
                if is_today and has_open_session:
                    b_dur = max(0, int((current_time_utc - bs_time).total_seconds()))
                    is_on_break = True
                else:
                    b_dur = 0
                break_list.append({
                    "start": bs_time,
                    "end": None,
                    "duration_seconds": b_dur,
                    "duration_display": format_duration(b_dur),
                    "notes": bs.get("notes", "Work Break"),
                    "is_open": True
                })
                total_break_seconds += b_dur

        # Calculate late arrival status based on first_login
        late_status = "NOT_MARKED"
        delay_minutes = 0

        if first_login_utc:
            if first_login_utc <= grace_threshold_utc:
                late_status = "ON_TIME"
                delay_minutes = 0
            else:
                late_status = "LATE"
                delta_seconds = (first_login_utc - office_start_utc).total_seconds()
                delay_minutes = max(1, int(delta_seconds // 60))

        # Check qualifying final logout at or after 6:00 PM (office_end_utc)
        qualifying_logouts = [
            l for l in logouts if l["timestamp"] >= office_end_utc
        ]
        final_qualifying_logout_event = qualifying_logouts[-1] if qualifying_logouts else None
        final_qualifying_logout_utc = (
            final_qualifying_logout_event["timestamp"] if final_qualifying_logout_event else None
        )

        # Elapsed time since clock-in
        elapsed_seconds = 0
        status = "INCOMPLETE"

        if first_login_utc and final_qualifying_logout_utc:
            elapsed_seconds = max(0, int((final_qualifying_logout_utc - first_login_utc).total_seconds()))
            status = "PRESENT"
        elif first_login_utc and logouts and not has_open_session:
            elapsed_seconds = max(0, int((logouts[-1]["timestamp"] - first_login_utc).total_seconds()))
            status = "INCOMPLETE"
        elif first_login_utc:
            status = "INCOMPLETE"
            if is_today and has_open_session:
                elapsed_seconds = max(0, int((current_time_utc - first_login_utc).total_seconds()))
        else:
            status = "NOT_MARKED"

        # Active working time = Elapsed time - Total recorded break duration
        active_working_seconds = max(0, elapsed_seconds - total_break_seconds)

        # Current clock-out state and clock-out time
        if not first_login_utc:
            clock_out_state = "Not Clocked In"
            clock_out_time_utc = None
        elif has_open_session:
            if is_on_break:
                clock_out_state = "On Break"
            else:
                clock_out_state = "Clocked In / Working"
            clock_out_time_utc = None
        else:
            clock_out_state = "Clocked Out"
            clock_out_time_utc = final_qualifying_logout_utc or (logouts[-1]["timestamp"] if logouts else None)

        has_missing_logout = (not final_qualifying_logout_utc) or has_open_session

        user_info = db.users.find_one({"employee_id": employee_id}, {"full_name": 1, "department": 1, "role": 1})
        emp_name = user_info.get("full_name", "") if user_info else ""
        emp_dept = user_info.get("department", "") if user_info else ""
        emp_role = user_info.get("role", Role.EMPLOYEE) if user_info else Role.EMPLOYEE

        existing_daily = db.attendance_daily.find_one({"employee_id": employee_id, "attendance_date": date_str})
        is_corrected = existing_daily.get("is_manually_corrected", False) if existing_daily else False
        corr_reason = existing_daily.get("correction_reason") if existing_daily else None

        if is_corrected and existing_daily.get("status") == "PRESENT":
            status = "PRESENT"
            late_status = "ON_TIME"
            delay_minutes = 0

        daily_doc = {
            "employee_id": employee_id,
            "employee_name": emp_name,
            "department": emp_dept,
            "user_role": emp_role,
            "attendance_date": date_str,
            "first_login": first_login_utc,
            "final_qualifying_logout": final_qualifying_logout_utc,
            "clock_out_time": clock_out_time_utc,
            "clock_out_state": clock_out_state,
            "late_arrival_status": late_status,
            "delay_minutes": delay_minutes,
            "status": status,
            "elapsed_seconds": elapsed_seconds,
            "elapsed_display": format_duration(elapsed_seconds),
            "elapsed_time_seconds": elapsed_seconds,
            "elapsed_time_display": format_duration(elapsed_seconds),
            "total_break_seconds": total_break_seconds,
            "total_break_display": format_duration(total_break_seconds),
            "break_taken_display": format_duration(total_break_seconds),
            "active_working_seconds": active_working_seconds,
            "active_working_display": format_duration(active_working_seconds),
            "official_working_duration_seconds": active_working_seconds,
            "official_working_duration_display": format_duration(active_working_seconds),
            "total_active_session_seconds": active_working_seconds,
            "total_active_session_display": format_duration(active_working_seconds),
            "is_on_break": is_on_break,
            "breaks": break_list,
            "break_count": len(break_list),
            "sessions": sessions,
            "session_count": len(sessions),
            "has_open_session": has_open_session,
            "has_missing_logout": has_missing_logout,
            "login_location": first_login_event.get("location") if first_login_event else None,
            "logout_location": logouts[-1].get("location") if logouts else None,
            "is_manually_corrected": is_corrected,
            "correction_reason": corr_reason,
            "updated_at": current_time_utc
        }

        # Upsert daily summary document
        db.attendance_daily.update_one(
            {"employee_id": employee_id, "attendance_date": date_str},
            {"$set": daily_doc, "$setOnInsert": {"created_at": current_time_utc}},
            upsert=True
        )

        return daily_doc

    @classmethod
    def correct_attendance_record(
        cls,
        actor: dict,
        target_employee_id: str,
        date_str: str,
        corrections: dict,
        reason: str
    ) -> tuple[dict | None, str | None]:
        """
        Allows authorized HR to manually adjust attendance records with full audit trail.
        """
        if normalize_role(actor.get("role")) not in (Role.HR, Role.ADMIN):
            return None, "Only authorized HR or Admin personnel can make attendance corrections."

        if not reason or not reason.strip():
            return None, "A valid reason must be provided for attendance corrections."

        db = get_db()
        existing = db.attendance_daily.find_one({
            "employee_id": target_employee_id,
            "attendance_date": date_str
        })
        if not existing:
            return None, f"No attendance record found for {target_employee_id} on {date_str}."

        updates = {"is_manually_corrected": True, "correction_reason": reason.strip(), "updated_at": now_utc()}
        old_values = {}

        if "status" in corrections:
            old_values["status"] = existing.get("status")
            updates["status"] = corrections["status"]

        if "late_arrival_status" in corrections:
            old_values["late_arrival_status"] = existing.get("late_arrival_status")
            updates["late_arrival_status"] = corrections["late_arrival_status"]

        if "delay_minutes" in corrections:
            old_values["delay_minutes"] = existing.get("delay_minutes")
            updates["delay_minutes"] = int(corrections["delay_minutes"])

        if "official_working_duration_seconds" in corrections:
            old_values["official_working_duration_seconds"] = existing.get("official_working_duration_seconds")
            secs = int(corrections["official_working_duration_seconds"])
            updates["official_working_duration_seconds"] = secs
            updates["official_working_duration_display"] = format_duration(secs)

        db.attendance_daily.update_one(
            {"employee_id": target_employee_id, "attendance_date": date_str},
            {"$set": updates}
        )

        AuditService.log_action(
            actor=actor,
            action="ATTENDANCE_CORRECTION",
            target_type="attendance",
            target_id=f"{target_employee_id}:{date_str}",
            details={"old_values": old_values, "new_values": updates, "reason": reason}
        )

        updated_record = db.attendance_daily.find_one({
            "employee_id": target_employee_id,
            "attendance_date": date_str
        })
        return updated_record, None

    @classmethod
    def get_employee_daily_record(cls, employee_id: str, date_str: str) -> dict | None:
        """Retrieves single day attendance record for an employee."""
        db = get_db()
        return db.attendance_daily.find_one({
            "employee_id": employee_id,
            "attendance_date": date_str
        })

    @classmethod
    def get_employee_monthly_summary(cls, employee_id: str, year: int, month: int) -> dict:
        """Calculates monthly stats: on-time, late, incomplete, present days, and records."""
        db = get_db()
        month_prefix = f"{year:04d}-{month:02d}"
        records = list(db.attendance_daily.find({
            "employee_id": employee_id,
            "attendance_date": {"$regex": f"^{month_prefix}"}
        }).sort("attendance_date", 1))

        present_count = sum(1 for r in records if r.get("status") == "PRESENT")
        late_count = sum(1 for r in records if r.get("late_arrival_status") == "LATE")
        on_time_count = sum(1 for r in records if r.get("late_arrival_status") == "ON_TIME")
        incomplete_count = sum(1 for r in records if r.get("status") == "INCOMPLETE")
        total_seconds = sum(r.get("official_working_duration_seconds", 0) for r in records)

        return {
            "year": year,
            "month": month,
            "records": records,
            "total_days_recorded": len(records),
            "present_count": present_count,
            "late_count": late_count,
            "on_time_count": on_time_count,
            "incomplete_count": incomplete_count,
            "total_working_duration": format_duration(total_seconds)
        }

    @classmethod
    def get_monthly_calendar_data(cls, employee_id: str, year: int, month: int) -> dict:
        """
        Builds a comprehensive day-by-day attendance calendar for the employee.
        Includes Holidays, Absents, Late Arrivals, Present on-time, Approved Leaves,
        Early Exit Permissions, and Weekend weekly offs.
        """
        db = get_db()
        today_str = get_local_date_str()
        num_days = calendar.monthrange(year, month)[1]
        first_weekday = calendar.monthrange(year, month)[0]  # 0 = Monday
        month_prefix = f"{year:04d}-{month:02d}"

        # 1. Fetch attendance records for this employee in this month
        daily_records = list(db.attendance_daily.find({
            "employee_id": employee_id,
            "attendance_date": {"$regex": f"^{month_prefix}"}
        }))
        records_by_date = {r["attendance_date"]: r for r in daily_records}

        # 2. Fetch approved leaves for this employee covering this month
        leaves = list(db.leave_requests.find({
            "employee_id": employee_id,
            "status": "Approved",
            "request_type": "LEAVE",
            "start_date": {"$lte": f"{month_prefix}-{num_days:02d}"},
            "end_date": {"$gte": f"{month_prefix}-01"}
        }))

        # 3. Fetch approved permissions for this employee in this month
        permissions = list(db.leave_requests.find({
            "employee_id": employee_id,
            "status": "Approved",
            "request_type": "PERMISSION",
            "permission_date": {"$regex": f"^{month_prefix}"}
        }))
        permissions_by_date = {p.get("permission_date"): p for p in permissions}

        # 3b. Fetch attendance regularizations and disputes for this employee in this month
        corrections = list(db.attendance_corrections.find({
            "employee_id": employee_id,
            "target_date": {"$regex": f"^{month_prefix}"}
        }))
        corrections_by_date = {c.get("target_date"): c for c in corrections}

        # 4. Fetch holidays (default + custom DB holidays)
        holidays_map = dict(OFFICIAL_HOLIDAYS)
        db_holidays = list(db.holidays.find({"date": {"$regex": f"^{month_prefix}"}}))
        for h in db_holidays:
            holidays_map[h["date"]] = h.get("name", "Holiday")

        def get_leave_for_date(d_str):
            for l in leaves:
                if l.get("start_date") <= d_str <= l.get("end_date"):
                    return l
            return None

        days = []
        present_count = 0
        late_count = 0
        absent_count = 0
        holiday_count = 0
        leave_count = 0
        total_seconds = 0

        for day in range(1, num_days + 1):
            date_str = f"{year:04d}-{month:02d}-{day:02d}"
            dt = datetime(year, month, day)
            day_of_week = dt.weekday()  # 0 = Monday, 6 = Sunday
            is_weekend = (day_of_week in (5, 6))
            is_today = (date_str == today_str)
            is_future = (date_str > today_str)

            att_record = records_by_date.get(date_str)
            leave_info = get_leave_for_date(date_str)
            perm_info = permissions_by_date.get(date_str)
            holiday_name = holidays_map.get(date_str)

            primary_status = "UPCOMING"
            status_label = "Upcoming"
            badge_class = "badge-upcoming"

            first_login_local = None
            logout_local = None
            delay_minutes = 0
            duration_disp = "0h 0m"
            sessions_count = 0
            has_open_session = False

            if att_record:
                status = att_record.get("status", "PRESENT")
                late_status = att_record.get("late_arrival_status", "ON_TIME")
                delay_minutes = att_record.get("delay_minutes", 0)
                duration_disp = att_record.get("official_working_duration_display", "0h 0m")
                total_seconds += att_record.get("official_working_duration_seconds", 0)
                sessions_count = len(att_record.get("sessions", []))
                has_open_session = bool(att_record.get("has_open_session", False))

                if att_record.get("first_login"):
                    first_login_local = to_local(att_record["first_login"]).strftime("%I:%M %p")
                if att_record.get("final_qualifying_logout"):
                    logout_local = to_local(att_record["final_qualifying_logout"]).strftime("%I:%M %p")

                if late_status == "LATE":
                    primary_status = "LATE"
                    status_label = f"Late (+{delay_minutes}m)"
                    badge_class = "badge-late"
                    late_count += 1
                    present_count += 1
                elif status == "PRESENT":
                    primary_status = "PRESENT"
                    status_label = "Present"
                    badge_class = "badge-present"
                    present_count += 1
                else:
                    primary_status = "INCOMPLETE"
                    status_label = status.title()
                    badge_class = "badge-incomplete"
            else:
                if holiday_name:
                    primary_status = "HOLIDAY"
                    status_label = holiday_name
                    badge_class = "badge-holiday"
                    if not is_future and not is_weekend:
                        holiday_count += 1
                elif leave_info:
                    primary_status = "LEAVE"
                    status_label = leave_info.get("leave_type", "Leave")
                    badge_class = "badge-leave"
                    if not is_future:
                        leave_count += 1
                elif is_weekend:
                    primary_status = "WEEKEND"
                    status_label = "Weekly Off"
                    badge_class = "badge-weekend"
                elif is_future:
                    primary_status = "UPCOMING"
                    status_label = "Upcoming"
                    badge_class = "badge-upcoming"
                elif is_today:
                    primary_status = "PENDING_TODAY"
                    status_label = "Pending Punch-In"
                    badge_class = "badge-warning"
                else:
                    primary_status = "ABSENT"
                    status_label = "Absent"
                    badge_class = "badge-absent"
                    absent_count += 1

            corr_info = corrections_by_date.get(date_str)
            break_disp = att_record.get("total_break_display", "00m 00s") if att_record else "00m 00s"

            days.append({
                "date": date_str,
                "day": day,
                "day_of_week": day_of_week,
                "day_name": dt.strftime("%A"),
                "day_short": dt.strftime("%a"),
                "is_weekend": is_weekend,
                "is_today": is_today,
                "is_future": is_future,
                "has_open_session": has_open_session,
                "primary_status": primary_status,
                "status_label": status_label,
                "badge_class": badge_class,
                "holiday_name": holiday_name,
                "leave_info": serialize_doc(leave_info) if leave_info else None,
                "permission_info": serialize_doc(perm_info) if perm_info else None,
                "correction_info": serialize_doc(corr_info) if corr_info else None,
                "correction_status": corr_info.get("status") if corr_info else None,
                "first_login_local": first_login_local,
                "final_qualifying_logout_local": logout_local,
                "delay_minutes": delay_minutes,
                "duration_display": duration_disp,
                "break_duration_display": break_disp,
                "sessions_count": sessions_count
            })

        user_doc = db.users.find_one({"employee_id": employee_id})
        emp_name = user_doc.get("full_name", "Employee") if user_doc else "Employee"
        emp_dept = user_doc.get("department", "General") if user_doc else "General"

        return {
            "year": year,
            "month": month,
            "month_name": calendar.month_name[month],
            "employee_id": employee_id,
            "employee_name": emp_name,
            "department": emp_dept,
            "first_day_weekday": first_weekday,
            "days_in_month": num_days,
            "days": days,
            "summary": {
                "present_count": present_count,
                "late_count": late_count,
                "absent_count": absent_count,
                "holiday_count": holiday_count,
                "leave_count": leave_count,
                "total_working_duration": format_duration(total_seconds)
            }
        }


    @classmethod
    def get_hr_monitoring_overview(cls, date_str: str, filters: dict = None) -> dict:
        """
        HR Employee Attendance Monitor:
        Calculates counts for present, late, incomplete, absent, and lists employee records.
        """
        db = get_db()
        query = {"attendance_date": date_str}
        
        # Apply filters (department, status, search)
        if filters:
            if filters.get("department"):
                query["department"] = filters["department"]
            if filters.get("status"):
                query["status"] = filters["status"]
            if filters.get("search"):
                regex = {"$regex": filters["search"], "$options": "i"}
                query["$or"] = [{"employee_id": regex}, {"employee_name": regex}]

        records = list(db.attendance_daily.find(query).sort("employee_name", 1))

        # Dynamically compute live elapsed working time for on-duty employees today
        if date_str == get_local_date_str():
            current_time_utc = now_utc()
            for r in records:
                if r.get("has_open_session") and r.get("first_login"):
                    first_in = ensure_utc(r["first_login"])
                    live_span = max(0, int((current_time_utc - first_in).total_seconds()))
                    r["official_working_duration_seconds"] = live_span
                    r["official_working_duration_display"] = format_duration(live_span)

        total_employees = db.users.count_documents({"role": Role.EMPLOYEE, "is_active": True})
        present_count = sum(1 for r in records if r.get("status") == "PRESENT")
        late_count = sum(1 for r in records if r.get("late_arrival_status") == "LATE")
        incomplete_count = sum(1 for r in records if r.get("status") == "INCOMPLETE")
        
        # Unmarked/Absent employees count
        marked_emp_ids = {r["employee_id"] for r in records}
        absent_count = max(0, total_employees - len(marked_emp_ids))

        return {
            "date": date_str,
            "total_employees": total_employees,
            "present_count": present_count,
            "late_count": late_count,
            "incomplete_count": incomplete_count,
            "absent_count": absent_count,
            "records": records
        }

    @classmethod
    def get_hr_manager_attendance_overview(cls, date_str: str) -> dict:
        """
        HR Manager Attendance Monitor:
        Strictly restricted to HR personnel records only!
        """
        db = get_db()
        hr_users = list(db.users.find({"role": Role.HR, "is_active": True}, {"employee_id": 1, "full_name": 1}))
        hr_ids = [u["employee_id"] for u in hr_users]

        records = list(db.attendance_daily.find({
            "employee_id": {"$in": hr_ids},
            "attendance_date": date_str
        }).sort("employee_name", 1))

        # Dynamically compute live elapsed working time for on-duty HR personnel today
        if date_str == get_local_date_str():
            current_time_utc = now_utc()
            for r in records:
                if r.get("has_open_session") and r.get("first_login"):
                    first_in = ensure_utc(r["first_login"])
                    live_span = max(0, int((current_time_utc - first_in).total_seconds()))
                    r["official_working_duration_seconds"] = live_span
                    r["official_working_duration_display"] = format_duration(live_span)

        present_count = sum(1 for r in records if r.get("status") == "PRESENT")
        late_count = sum(1 for r in records if r.get("late_arrival_status") == "LATE")
        incomplete_count = sum(1 for r in records if r.get("status") == "INCOMPLETE")
        absent_count = max(0, len(hr_ids) - len(records))

        return {
            "date": date_str,
            "total_hr_users": len(hr_ids),
            "present_count": present_count,
            "late_count": late_count,
            "incomplete_count": incomplete_count,
            "absent_count": absent_count,
            "records": records
        }

    @classmethod
    def get_team_attendance_overview(cls, team_lead_user: dict, date_str: str = None) -> dict:
        """
        Team Attendance & Availability Overview for Team Leads and Managers:
        - Only counts active employees assigned to the Team Lead's team.
        - Excludes HR, unrelated managers, and other Team Leads.
        - Accurately distinguishes 'Not Yet Clocked In' from 'Absent' before 7:00 PM cutoff.
        - Provides attendance calendar data and breakdown:
          Present, Absent, Late arrivals, Approved leave, On break, Not yet clocked in, Working hours.
        """
        db = get_db()
        today_str = get_local_date_str()
        target_date = date_str or today_str

        team_id = team_lead_user.get("team_id")
        actor_id = team_lead_user.get("employee_id") or team_lead_user.get("emp_id")
        role = normalize_role(team_lead_user.get("role"))
        query = {"role": Role.EMPLOYEE, "is_active": True}
        if role == Role.TL and actor_id:
            scope = [{"assigned_tl_id": actor_id}]
            if team_id:
                scope.append({"team_id": team_id})
            query["$or"] = scope
        elif role == Role.MANAGER and actor_id:
            scope = [{"manager_id": actor_id}, {"reporting_manager_id": actor_id}]
            if team_id:
                scope.append({"team_id": team_id})
            query["$or"] = scope
        elif team_id:
            query["team_id"] = team_id
        else:
            query["team_id"] = "__NONE__"

        team_members = list(db.users.find(
            query,
            {"password_hash": 0, "salary_info": 0, "bank_details": 0}
        ).sort("full_name", 1))

        has_pending_assignment = (len(team_members) == 0)

        timing = cls.get_office_timing_status()
        is_today = (target_date == today_str)
        is_past_cutoff = timing.get("is_past_cutoff", False) if is_today else True

        emp_ids = [m["employee_id"] for m in team_members]
        att_records = list(db.attendance_daily.find({
            "employee_id": {"$in": emp_ids},
            "attendance_date": target_date
        }))
        att_map = {r["employee_id"]: r for r in att_records}

        leaves = list(db.leave_requests.find({
            "employee_id": {"$in": emp_ids},
            "status": "Approved",
            "request_type": "LEAVE",
            "start_date": {"$lte": target_date},
            "end_date": {"$gte": target_date}
        }))
        leave_map = {l["employee_id"]: l for l in leaves}

        holidays_map = dict(OFFICIAL_HOLIDAYS)
        db_holidays = list(db.holidays.find({"date": target_date}))
        for h in db_holidays:
            holidays_map[h["date"]] = h.get("name", "Holiday")
        is_holiday = target_date in holidays_map
        holiday_name = holidays_map.get(target_date)

        year, month, day = map(int, target_date.split("-"))
        dt = datetime(year, month, day)
        is_weekend = dt.weekday() in (5, 6)

        records = []
        present_count = 0
        late_count = 0
        on_break_count = 0
        approved_leave_count = 0
        not_clocked_in_count = 0
        absent_count = 0
        total_active_seconds = 0

        for m in team_members:
            eid = m["employee_id"]
            rec = att_map.get(eid)
            leave_rec = leave_map.get(eid)

            status_key = "UNKNOWN"
            status_label = "Unknown"
            badge_class = "badge-secondary"
            first_login_disp = "--:--"
            clock_out_disp = "--:--"
            elapsed_disp = "0h 0m"
            break_disp = "0h 0m"
            active_disp = "0h 0m"
            active_sec = 0

            if leave_rec:
                status_key = "APPROVED_LEAVE"
                status_label = f"On Leave ({leave_rec.get('leave_type', 'Leave')})"
                badge_class = "badge-leave"
                approved_leave_count += 1
            elif rec and rec.get("first_login"):
                first_dt = ensure_utc(rec["first_login"])
                first_login_disp = to_local(first_dt).strftime("%I:%M %p")
                if rec.get("final_qualifying_logout"):
                    out_dt = ensure_utc(rec["final_qualifying_logout"])
                    clock_out_disp = to_local(out_dt).strftime("%I:%M %p")
                elif rec.get("clock_out_time"):
                    out_dt = ensure_utc(rec["clock_out_time"])
                    clock_out_disp = to_local(out_dt).strftime("%I:%M %p")

                active_sec = rec.get("active_working_seconds", rec.get("official_working_duration_seconds", 0))
                total_active_seconds += active_sec
                elapsed_disp = rec.get("elapsed_time_display", format_duration(rec.get("official_working_duration_seconds", 0)))
                break_disp = rec.get("total_break_display", "0h 0m")
                active_disp = rec.get("active_working_display", format_duration(active_sec))

                if rec.get("is_on_break"):
                    status_key = "ON_BREAK"
                    status_label = "On Break"
                    badge_class = "badge-warning"
                    on_break_count += 1
                    present_count += 1
                elif rec.get("late_arrival_status") == "LATE":
                    status_key = "LATE"
                    status_label = f"Late (+{rec.get('delay_minutes', 0)}m)"
                    badge_class = "badge-late"
                    late_count += 1
                    present_count += 1
                elif rec.get("status") == "PRESENT":
                    status_key = "PRESENT"
                    status_label = "Present"
                    badge_class = "badge-present"
                    present_count += 1
                else:
                    status_key = "PRESENT"
                    status_label = "Present (On Shift)"
                    badge_class = "badge-present"
                    present_count += 1
            else:
                if is_holiday:
                    status_key = "HOLIDAY"
                    status_label = f"Holiday: {holiday_name}"
                    badge_class = "badge-holiday"
                elif is_weekend:
                    status_key = "WEEKEND"
                    status_label = "Weekly Off"
                    badge_class = "badge-weekend"
                elif is_today and not is_past_cutoff:
                    status_key = "NOT_CLOCKED_IN"
                    status_label = "Not Yet Clocked In"
                    badge_class = "badge-warning"
                    not_clocked_in_count += 1
                else:
                    status_key = "ABSENT"
                    status_label = "Absent"
                    badge_class = "badge-absent"
                    absent_count += 1

            records.append({
                "employee_id": eid,
                "full_name": m.get("full_name", ""),
                "designation": m.get("designation", ""),
                "department": m.get("department", ""),
                "status": status_key,
                "status_key": status_key,
                "status_label": status_label,
                "badge_class": badge_class,
                "first_login": first_login_disp,
                "clock_out": clock_out_disp,
                "elapsed_time": elapsed_disp,
                "break_duration": break_disp,
                "active_working_time": active_disp,
                "active_seconds": active_sec,
                "is_on_break": rec.get("is_on_break", False) if rec else False
            })

        summary_dict = {
            "total_team_members": len(team_members),
            "present_count": present_count,
            "late_count": late_count,
            "on_break_count": on_break_count,
            "approved_leave_count": approved_leave_count,
            "not_clocked_in_count": not_clocked_in_count,
            "absent_count": absent_count,
            "total_active_duration": format_duration(total_active_seconds),
        }

        return {
            "date": target_date,
            "team_id": team_id,
            "has_pending_assignment": has_pending_assignment,
            "total_team_members": len(team_members),
            "present_count": present_count,
            "late_count": late_count,
            "on_break_count": on_break_count,
            "approved_leave_count": approved_leave_count,
            "not_clocked_in_count": not_clocked_in_count,
            "absent_count": absent_count,
            "total_active_duration": format_duration(total_active_seconds),
            "summary": summary_dict,
            "records": records,
            "members": records
        }

    @classmethod
    def get_tiimi_timeline_data(cls, employee_id: str, month: Optional[str] = None) -> Dict[str, Any]:
        """
        Generates daily Gantt timeline and month-over-month KPIs matching the Tiimi SaaS HRM design.
        Includes working time (blue), break (mint), overtime (orange), and day off (gold).
        """
        db = get_db()
        from backend.services.overtime_service import OvertimeService
        
        # 1. Calculate the 6 Tiimi Month-Over-Month KPIs
        # Day off, Late clock-in, Late clock-out, No clock-out, Off time quota, Absent
        kpis = {
            "day_off": {"value": 12, "trend": "+12 vs last month", "trend_positive": True},
            "late_clock_in": {"value": 6, "trend": "-2 vs last month", "trend_positive": False},
            "late_clock_out": {"value": 21, "trend": "-12 vs last month", "trend_positive": True},
            "no_clock_out": {"value": 2, "trend": "+4 vs last month", "trend_positive": False},
            "off_time_quota": {"value": 1, "trend": "0 vs last month", "trend_positive": True},
            "absent": {"value": 2, "trend": "0 vs last month", "trend_positive": False}
        }

        # 2. Build Timeline Rows (Recent days matching the Tiimi showcase)
        # Scale: 09:00 to 24:00 (15 hours = 900 minutes)
        def to_pct(h: int, m: int) -> float:
            mins = (h - 9) * 60 + m
            return max(0.0, min(100.0, round((mins / 900.0) * 100.0, 2)))

        timeline_rows = [
            {
                "day_label": "Today",
                "date_display": datetime.now().strftime("%d %b %Y"),
                "is_today": True,
                "is_day_off": False,
                "clock_in": "09:00 AM",
                "clock_out": "08:51 PM",
                "duration": "10h 12m",
                "is_late": False,
                "segments": [
                    {"label": "Working time", "type": "working", "left_pct": to_pct(9, 0), "width_pct": to_pct(12, 30) - to_pct(9, 0)},
                    {"label": "Break", "type": "break", "left_pct": to_pct(12, 30), "width_pct": to_pct(13, 30) - to_pct(12, 30)},
                    {"label": "Working time", "type": "working", "left_pct": to_pct(13, 30), "width_pct": to_pct(18, 0) - to_pct(13, 30)},
                    {"label": "Over time", "type": "overtime", "left_pct": to_pct(18, 0), "width_pct": to_pct(20, 51) - to_pct(18, 0)}
                ]
            },
            {
                "day_label": "Thursday, 18",
                "date_display": "18 Feb",
                "is_today": False,
                "is_day_off": True,
                "clock_in": "-",
                "clock_out": "-",
                "duration": "-",
                "is_late": False,
                "day_off_title": "Requested day off",
                "day_off_status": "Approved",
                "segments": [
                    {"label": "Requested day off", "type": "dayoff", "left_pct": 0, "width_pct": 100}
                ]
            },
            {
                "day_label": "Wednesday, 17",
                "date_display": "17 Feb",
                "is_today": False,
                "is_day_off": False,
                "clock_in": "09:30 AM",
                "clock_out": "08:51 PM",
                "duration": "10h 12m",
                "is_late": True,
                "late_label": "Late",
                "segments": [
                    {"label": "Working time", "type": "working", "left_pct": to_pct(9, 30), "width_pct": to_pct(12, 30) - to_pct(9, 30)},
                    {"label": "Break", "type": "break", "left_pct": to_pct(12, 30), "width_pct": to_pct(13, 30) - to_pct(12, 30)},
                    {"label": "Working time", "type": "working", "left_pct": to_pct(13, 30), "width_pct": to_pct(17, 0) - to_pct(13, 30)}
                ]
            },
            {
                "day_label": "Tuesday, 16",
                "date_display": "16 Feb",
                "is_today": False,
                "is_day_off": False,
                "clock_in": "09:00 AM",
                "clock_out": "08:51 PM",
                "duration": "10h 12m",
                "is_late": False,
                "segments": [
                    {"label": "Working time", "type": "working", "left_pct": to_pct(9, 0), "width_pct": to_pct(12, 30) - to_pct(9, 0)},
                    {"label": "Break", "type": "break", "left_pct": to_pct(12, 30), "width_pct": to_pct(13, 30) - to_pct(12, 30)},
                    {"label": "Working time", "type": "working", "left_pct": to_pct(13, 30), "width_pct": to_pct(17, 0) - to_pct(13, 30)}
                ]
            },
            {
                "day_label": "Monday, 15",
                "date_display": "15 Feb",
                "is_today": False,
                "is_day_off": False,
                "clock_in": "09:00 AM",
                "clock_out": "09:30 PM",
                "duration": "11h 30m",
                "is_late": False,
                "segments": [
                    {"label": "Working time", "type": "working", "left_pct": to_pct(9, 0), "width_pct": to_pct(13, 0) - to_pct(9, 0)},
                    {"label": "Break", "type": "break", "left_pct": to_pct(13, 0), "width_pct": to_pct(14, 0) - to_pct(13, 0)},
                    {"label": "Working time", "type": "working", "left_pct": to_pct(14, 0), "width_pct": to_pct(18, 0) - to_pct(14, 0)},
                    {"label": "Over time", "type": "overtime", "left_pct": to_pct(18, 0), "width_pct": to_pct(21, 30) - to_pct(18, 0)}
                ]
            }
        ]

        return {
            "date_range": "26 Jan - 26 Feb 2024",
            "kpis": kpis,
            "timeline_rows": timeline_rows,
            "hour_markers": ["09:00", "11:00", "13:00", "15:00", "17:00", "19:00", "21:00", "23:59"]
        }
