import logging
import uuid
from datetime import datetime, timezone, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from backend.database.connection import get_db
from backend.utils.timezone import now_local, get_local_date_str
from backend.services.attendance_service import AttendanceService
from backend.services.birthday_service import BirthdayService
from backend.permissions.rbac import Role

logger = logging.getLogger(__name__)

class DistributedScheduler:
    _scheduler: BackgroundScheduler | None = None
    _instance_id: str = str(uuid.uuid4())

    @classmethod
    def acquire_lock(cls, lock_name: str, lease_seconds: int = 120) -> bool:
        db = get_db()
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=lease_seconds)

        try:
            result = db.scheduler_locks.find_one_and_update(
                {
                    "lock_key": lock_name,
                    "$or": [
                        {"expires_at": {"$lte": now}},
                        {"owner_id": cls._instance_id}
                    ]
                },
                {
                    "$set": {
                        "owner_id": cls._instance_id,
                        "acquired_at": now,
                        "expires_at": expires_at
                    }
                },
                upsert=True,
                return_document=True
            )
            return result is not None and result.get("owner_id") == cls._instance_id
        except Exception:
            return False

    @classmethod
    def release_lock(cls, lock_name: str):
        db = get_db()
        try:
            db.scheduler_locks.delete_one({
                "lock_key": lock_name,
                "owner_id": cls._instance_id
            })
        except Exception:
            pass

    @classmethod
    def run_morning_cutoff_job(cls):
        if not cls.acquire_lock("job_morning_cutoff", lease_seconds=180):
            return

        try:
            logger.info("Executing morning attendance cutoff job...")
            db = get_db()
            today_str = get_local_date_str()
            active_employees = list(db.users.find({"role": Role.EMPLOYEE, "is_active": True}))

            for emp in active_employees:
                emp_id = emp["employee_id"]
                existing = db.attendance_daily.find_one({"employee_id": emp_id, "attendance_date": today_str})
                if not existing:
                    events_count = db.attendance_events.count_documents({"employee_id": emp_id, "date": today_str})
                    if events_count == 0:
                        db.attendance_daily.update_one(
                            {"employee_id": emp_id, "attendance_date": today_str},
                            {
                                "$setOnInsert": {
                                    "employee_id": emp_id,
                                    "employee_name": emp.get("full_name", ""),
                                    "department": emp.get("department", ""),
                                    "user_role": Role.EMPLOYEE,
                                    "attendance_date": today_str,
                                    "status": "NOT_MARKED",
                                    "late_arrival_status": "NOT_MARKED",
                                    "delay_minutes": 0,
                                    "official_working_duration_seconds": 0,
                                    "total_active_session_seconds": 0,
                                    "sessions": [],
                                    "session_count": 0,
                                    "has_missing_logout": True,
                                    "created_at": datetime.now(timezone.utc),
                                    "updated_at": datetime.now(timezone.utc)
                                }
                            },
                            upsert=True
                        )
            logger.info("Morning cutoff job completed.")
        finally:
            cls.release_lock("job_morning_cutoff")

    @classmethod
    def run_evening_reconciliation_job(cls):
        if not cls.acquire_lock("job_evening_reconcile", lease_seconds=180):
            return

        try:
            logger.info("Executing evening attendance reconciliation job...")
            db = get_db()
            today_str = get_local_date_str()
            records = list(db.attendance_daily.find({"attendance_date": today_str}))
            for rec in records:
                AttendanceService.recalculate_daily_summary(rec["employee_id"], today_str)
            logger.info("Evening reconciliation job completed.")
        finally:
            cls.release_lock("job_evening_reconcile")

    @classmethod
    def run_birthday_job(cls):
        if not cls.acquire_lock("job_birthday_scan", lease_seconds=180):
            return

        try:
            logger.info("Running automated birthday check...")
            BirthdayService.check_and_send_birthday_notifications()
        finally:
            cls.release_lock("job_birthday_scan")

    @classmethod
    def run_monthly_birthday_job(cls):
        if not cls.acquire_lock("job_monthly_birthday_scan", lease_seconds=180):
            return

        try:
            logger.info("Running automated monthly birthday announcement job...")
            BirthdayService.check_and_send_monthly_birthday_announcement()
        finally:
            cls.release_lock("job_monthly_birthday_scan")

    @classmethod
    def run_cutoff_intimation_job(cls):
        if not cls.acquire_lock("job_cutoff_intimation", lease_seconds=180):
            return

        try:
            logger.info("Executing 45-minute prior out cutoff intimation job (18:15)...")
            sent = AttendanceService.check_and_send_cutoff_intimations()
            logger.info("Cutoff intimation job completed. Notifications dispatched: %d", len(sent))
        finally:
            cls.release_lock("job_cutoff_intimation")

    @classmethod
    def run_evening_cutoff_job(cls):
        if not cls.acquire_lock("job_evening_cutoff_7pm", lease_seconds=180):
            return

        try:
            logger.info("Executing 7:00 PM automated attendance cutoff job...")
            closed = AttendanceService.execute_7pm_attendance_cutoff()
            logger.info("7:00 PM cutoff job completed. Automatically closed %d active sessions.", len(closed))
            # Run evening summary reconciliation for all employees today
            db = get_db()
            today_str = get_local_date_str()
            records = list(db.attendance_daily.find({"attendance_date": today_str}))
            for rec in records:
                AttendanceService.recalculate_daily_summary(rec["employee_id"], today_str)
        finally:
            cls.release_lock("job_evening_cutoff_7pm")

    @classmethod
    def start(cls):
        if cls._scheduler is None:
            cls._scheduler = BackgroundScheduler(timezone="Asia/Kolkata")
            
            cls._scheduler.add_job(
                cls.run_birthday_job,
                "cron",
                hour=9,
                minute=0,
                id="daily_birthday_job",
                replace_existing=True
            )

            cls._scheduler.add_job(
                cls.run_monthly_birthday_job,
                "cron",
                day=1,
                hour=9,
                minute=0,
                id="monthly_birthday_job",
                replace_existing=True
            )

            cls._scheduler.add_job(
                cls.run_morning_cutoff_job,
                "cron",
                hour=10,
                minute=15,
                id="morning_cutoff_job",
                replace_existing=True
            )

            cls._scheduler.add_job(
                cls.run_evening_reconciliation_job,
                "cron",
                hour=18,
                minute=5,
                id="evening_reconcile_job",
                replace_existing=True
            )

            # Mandatory 45-minute notification before 7:00 PM cutoff (triggered at 18:15 IST)
            cls._scheduler.add_job(
                cls.run_cutoff_intimation_job,
                "cron",
                hour=18,
                minute=15,
                id="cutoff_intimation_job",
                replace_existing=True
            )

            # Additional intimation checks at 18:30 and 18:45
            cls._scheduler.add_job(
                cls.run_cutoff_intimation_job,
                "cron",
                hour=18,
                minute=30,
                id="cutoff_intimation_recheck_30",
                replace_existing=True
            )

            cls._scheduler.add_job(
                cls.run_cutoff_intimation_job,
                "cron",
                hour=18,
                minute=45,
                id="cutoff_intimation_recheck_45",
                replace_existing=True
            )

            # 7:00 PM Hard Cutoff automatic session closure & reconciliation
            cls._scheduler.add_job(
                cls.run_evening_cutoff_job,
                "cron",
                hour=19,
                minute=0,
                id="evening_reconcile_cutoff_7pm",
                replace_existing=True
            )

            cls._scheduler.start()
            logger.info("Distributed APScheduler successfully started with cutoff intimation and 7 PM checkout jobs.")
            try:
                BirthdayService.run_startup_catchup()
            except Exception as e:
                logger.warning("Error during birthday startup catchup: %s", e)

            # Check if server started/restarted at or after 19:00 IST today; if so, execute cutoff catchup immediately
            try:
                local_dt = now_local()
                if local_dt.hour >= 19:
                    logger.info("Scheduler started at or after 19:00 IST (%s); executing 7 PM attendance cutoff catchup...", local_dt.strftime("%H:%M:%S"))
                    AttendanceService.execute_7pm_attendance_cutoff()
            except Exception as e:
                logger.warning("Error during cutoff startup catchup: %s", e)

    @classmethod
    def shutdown(cls):
        if cls._scheduler and cls._scheduler.running:
            cls._scheduler.shutdown(wait=False)
            cls._scheduler = None
            logger.info("APScheduler stopped.")
