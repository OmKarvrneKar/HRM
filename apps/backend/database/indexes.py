import logging
from pymongo import ASCENDING, DESCENDING
from pymongo.database import Database

logger = logging.getLogger(__name__)


def setup_indexes(db: Database):
    """Sets up all necessary indexes across HRM collections."""
    logger.info("Initializing database indexes on '%s'...", db.name)

    # 1. users
    db.users.create_index([("email", ASCENDING)], unique=True)
    try:
        db.users.create_index([("employee_id", ASCENDING)], unique=True, sparse=True)
    except Exception as e:
        logger.warning("Users employee_id unique index note: %s", e)
    db.users.create_index([("role", ASCENDING)])
    db.users.create_index([("is_active", ASCENDING)])
    db.users.create_index([("department", ASCENDING)])
    db.users.create_index([("team_id", ASCENDING)])

    # 2. attendance_events
    db.attendance_events.create_index([("employee_id", ASCENDING)])
    db.attendance_events.create_index([("date", ASCENDING)])
    db.attendance_events.create_index([("event_type", ASCENDING)])
    db.attendance_events.create_index([("timestamp", ASCENDING)])
    db.attendance_events.create_index(
        [("employee_id", ASCENDING), ("date", ASCENDING), ("timestamp", ASCENDING)]
    )

    # 3. attendance_daily
    db.attendance_daily.create_index(
        [("employee_id", ASCENDING), ("attendance_date", ASCENDING)],
        unique=True
    )
    db.attendance_daily.create_index([("attendance_date", ASCENDING)])
    db.attendance_daily.create_index([("status", ASCENDING)])
    db.attendance_daily.create_index([("late_arrival_status", ASCENDING)])
    db.attendance_daily.create_index([("employee_id", ASCENDING)])

    # 4. projects
    db.projects.create_index([("project_id", ASCENDING)], unique=True)
    db.projects.create_index([("status", ASCENDING)])
    db.projects.create_index([("members", ASCENDING)])
    db.projects.create_index([("team_id", ASCENDING)])

    # 5. teams
    db.teams.create_index([("team_id", ASCENDING)], unique=True)
    db.teams.create_index([("lead_employee_id", ASCENDING)])

    # 6. tasks
    db.tasks.create_index([("task_id", ASCENDING)], unique=True)
    db.tasks.create_index([("project_id", ASCENDING)])
    db.tasks.create_index([("assigned_employee_id", ASCENDING)])
    db.tasks.create_index([("status", ASCENDING)])

    # 7. notifications
    db.notifications.create_index([("recipient_id", ASCENDING)])
    db.notifications.create_index([("recipient_group", ASCENDING)])
    db.notifications.create_index([("is_read", ASCENDING)])
    db.notifications.create_index([("created_at", DESCENDING)])
    db.notifications.create_index([("idempotency_key", ASCENDING)], sparse=True, unique=True)

    # 8. complaints
    db.complaints.create_index([("complaint_id", ASCENDING)], unique=True)
    db.complaints.create_index([("complainant_id", ASCENDING)])
    db.complaints.create_index([("assigned_hr_id", ASCENDING)])
    db.complaints.create_index([("status", ASCENDING)])
    db.complaints.create_index([("created_at", DESCENDING)])

    # 9. profile_change_logs
    db.profile_change_logs.create_index([("target_employee_id", ASCENDING)])
    db.profile_change_logs.create_index([("changed_by_id", ASCENDING)])
    db.profile_change_logs.create_index([("timestamp", DESCENDING)])

    # 10. audit_logs
    db.audit_logs.create_index([("actor_id", ASCENDING)])
    db.audit_logs.create_index([("action", ASCENDING)])
    db.audit_logs.create_index([("target_type", ASCENDING)])
    db.audit_logs.create_index([("target_id", ASCENDING)])
    db.audit_logs.create_index([("timestamp", DESCENDING)])

    # 11. organization_settings
    db.organization_settings.create_index([("key", ASCENDING)], unique=True)

    # 12. scheduler_locks
    db.scheduler_locks.create_index([("lock_key", ASCENDING)], unique=True)
    db.scheduler_locks.create_index([("expires_at", ASCENDING)], expireAfterSeconds=0)

    # 13. login_attempts
    db.login_attempts.create_index([("ip_address", ASCENDING), ("email", ASCENDING)])
    db.login_attempts.create_index([("created_at", ASCENDING)], expireAfterSeconds=600)

    # 14. work_diary
    db.work_diary.create_index([("employee_id", ASCENDING)])
    db.work_diary.create_index([("diary_date", ASCENDING)])
    db.work_diary.create_index([("employee_id", ASCENDING), ("diary_date", ASCENDING)])
    db.work_diary.create_index([("diary_id", ASCENDING)], unique=True)
    db.work_diary.create_index([("created_at", DESCENDING)])

    # 15. leave_requests
    db.leave_requests.create_index([("request_id", ASCENDING)], unique=True)
    db.leave_requests.create_index([("employee_id", ASCENDING)])
    db.leave_requests.create_index([("status", ASCENDING)])
    db.leave_requests.create_index([("request_type", ASCENDING)])
    db.leave_requests.create_index([("created_at", DESCENDING)])
    db.leave_requests.create_index([("employee_id", ASCENDING), ("status", ASCENDING)])

    # 16. otp_tokens: Retain for 24 hours after expiry for rate limiting, security audit, and diagnostic error detection
    db.otp_tokens.create_index([("email", ASCENDING), ("purpose", ASCENDING)])
    db.otp_tokens.create_index([("expires_at", ASCENDING)], expireAfterSeconds=86400)

    # 17. attendance_corrections
    db.attendance_corrections.create_index([("request_id", ASCENDING)], unique=True)
    db.attendance_corrections.create_index([("employee_id", ASCENDING), ("target_date", ASCENDING)])
    db.attendance_corrections.create_index([("status", ASCENDING)])
    db.attendance_corrections.create_index([("assigned_manager_id", ASCENDING), ("status", ASCENDING)])

    # 18. leave_transactions
    db.leave_transactions.create_index([("transaction_id", ASCENDING)], unique=True)
    db.leave_transactions.create_index([("employee_id", ASCENDING), ("financial_year", ASCENDING)])
    db.leave_transactions.create_index([("created_at", DESCENDING)])

    # 19. wfh_requests
    db.wfh_requests.create_index([("request_id", ASCENDING)], unique=True)
    db.wfh_requests.create_index([("employee_id", ASCENDING)])
    db.wfh_requests.create_index([("status", ASCENDING)])

    # 20. team_rosters
    db.team_rosters.create_index([("roster_id", ASCENDING)], unique=True)
    db.team_rosters.create_index([("team_id", ASCENDING), ("month", ASCENDING), ("year", ASCENDING)])

    # 21. pip_records
    db.pip_records.create_index([("pip_id", ASCENDING)], unique=True)
    db.pip_records.create_index([("employee_id", ASCENDING)])
    db.pip_records.create_index([("status", ASCENDING)])

    # 22. documents
    db.documents.create_index([("document_id", ASCENDING)], unique=True)
    db.documents.create_index([("category", ASCENDING)])
    db.documents.create_index([("is_active", ASCENDING)])

    # 23. user_notepads (Personal Scratchpad per user)
    db.user_notepads.create_index([("employee_id", ASCENDING), ("is_deleted", ASCENDING)])
    db.user_notepads.create_index([("note_id", ASCENDING)], unique=True)

    # 24. system_feedback (Smart Bug Deduplication & Triage)
    db.system_feedback.create_index([("feedback_id", ASCENDING)], unique=True)
    db.system_feedback.create_index([("status", ASCENDING)])
    db.system_feedback.create_index([("category", ASCENDING)])
    db.system_feedback.create_index([("department", ASCENDING)])
    db.system_feedback.create_index([("created_at", DESCENDING)])

    logger.info("Indexes successfully initialized.")
