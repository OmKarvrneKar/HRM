"""
TestAccountService — Dedicated Temporary Employee Test Account Management.

Provides safe, controlled, isolated test account lifecycle for AISamrat HRMS.
Strictly disabled and deactivated in production environments.
"""

import logging
from datetime import datetime, timezone
from config import Config
from backend.permissions.rbac import Role
from backend.auth.security import hash_password

logger = logging.getLogger(__name__)


class TestAccountService:
    TEST_EMP_ID = "EMP-TEST-999"
    TEST_EMP_EMAIL = "test.employee@aisamrat.com"
    TEST_EMP_NAME = "Test Employee (QA Dev)"
    TEST_EMP_PASSWORD = "Dev@TestEmp2026!"  # Dev-only fallback for manual input
    TEST_PROJECT_ID = "PRJ-TEST-001"
    TEST_TASK_ID = "TSK-TEST-001"
    TEST_NOTIFICATION_ID = "NOTIF-TEST-001"

    @classmethod
    def is_test_employee(cls, user_or_id) -> bool:
        """Checks if a given user object or employee_id belongs to the test employee."""
        if not user_or_id:
            return False
        if isinstance(user_or_id, str):
            return user_or_id.strip().upper() == cls.TEST_EMP_ID
        if isinstance(user_or_id, dict):
            return (
                user_or_id.get("employee_id") == cls.TEST_EMP_ID
                or user_or_id.get("email") == cls.TEST_EMP_EMAIL
                or user_or_id.get("is_test_account") is True
            )
        return False

    @classmethod
    def disable_test_employee(cls, db) -> None:
        """
        Explicitly disables and locks the dedicated test employee account (EMP-TEST-999).
        Prevents any login or authentication with this test account.
        """
        if db is None:
            return
        db.users.update_many(
            {"$or": [{"employee_id": cls.TEST_EMP_ID}, {"email": cls.TEST_EMP_EMAIL}]},
            {
                "$set": {
                    "is_active": False,
                    "account_status": "disabled",
                    "employment_status": "Inactive",
                    "updated_at": datetime.now(timezone.utc)
                }
            }
        )
        logger.info("Test employee account %s has been deactivated and disabled.", cls.TEST_EMP_ID)

    @classmethod
    def ensure_test_employee(cls, db) -> dict | None:
        """
        Provisions or activates the dedicated temporary test employee account.
        In production, automatically deactivates and disables the account.
        """
        if db is None:
            return None

        # 1. Production safety guard: Disable and lock account
        if Config.is_production() or not Config.allows_test_account():
            existing = db.users.find_one({"employee_id": cls.TEST_EMP_ID})
            if existing and existing.get("is_active", True):
                db.users.update_one(
                    {"employee_id": cls.TEST_EMP_ID},
                    {
                        "$set": {
                            "is_active": False,
                            "account_status": "disabled_production",
                            "updated_at": datetime.now(timezone.utc)
                        }
                    }
                )
                logger.warning("Test account %s disabled for production safety.", cls.TEST_EMP_ID)
            return None

        # 2. Development mode: Ensure single dedicated test employee exists
        now = datetime.now(timezone.utc)
        user = db.users.find_one({"employee_id": cls.TEST_EMP_ID})

        test_user_data = {
            "employee_id": cls.TEST_EMP_ID,
            "full_name": cls.TEST_EMP_NAME,
            "email": cls.TEST_EMP_EMAIL,
            "personal_email": cls.TEST_EMP_EMAIL,
            "aliases": [],
            "role": Role.EMPLOYEE,  # Strict: Employee permissions only
            "department": "Engineering (QA & Testing)",
            "designation": "QA Test Analyst (Dev Account)",
            "team_id": "TEAM-DEV-TEST",
            "reporting_manager_id": "LEAD-1001",
            "employment_status": "Active",
            "employment_type": "Full-time",
            "joining_date": "2025-01-01",
            "date_of_birth": "1998-05-15",
            "phone_number": "+91 9999900000",
            "address": "AISamrat Tech Park, Test Lab 404, Whitefield, Bangalore",
            "emergency_contact": {
                "name": "Dev Support",
                "relation": "QA Lead",
                "phone": "+91 9999900001"
            },
            "skills": [
                {"name": "Manual Testing", "level": "Expert"},
                {"name": "API Testing", "level": "Advanced"},
                {"name": "UI Verification", "level": "Expert"},
                {"name": "Bug Reporting", "level": "Advanced"}
            ],
            "salary_info": {
                "basic": 25000,
                "hra": 10000,
                "allowances": 5000,
                "gross": 40000,
                "ctc": 480000
            },
            "is_active": True,
            "is_email_verified": True,
            "account_status": "active",
            "is_test_account": True,
            "notes": "Dedicated temporary QA test account for local employee dashboard testing. Disabled in production.",
            "updated_at": now
        }

        if not user:
            test_user_data["password_hash"] = hash_password(cls.TEST_EMP_PASSWORD)
            test_user_data["created_at"] = now
            db.users.insert_one(test_user_data)
            logger.info("Created temporary dev test employee account: %s", cls.TEST_EMP_ID)
        else:
            # Sync fields to ensure active status and valid password
            db.users.update_one(
                {"employee_id": cls.TEST_EMP_ID},
                {"$set": test_user_data}
            )

        # 3. Ensure isolated test project exists
        existing_proj = db.projects.find_one({"project_id": cls.TEST_PROJECT_ID})
        if not existing_proj:
            db.projects.insert_one({
                "project_id": cls.TEST_PROJECT_ID,
                "title": "AISamrat HRMS QA Sandbox",
                "name": "AISamrat HRMS QA Sandbox",
                "description": "Isolated sandbox project for testing employee tasks, attendance, and work logs.",
                "status": "Active",
                "progress_percentage": 35,
                "members": [cls.TEST_EMP_ID, "LEAD-1001"],
                "manager_employee_id": "ADM-1001",
                "lead_id": "LEAD-1001",
                "start_date": "2025-01-01",
                "due_date": "2026-12-31",
                "is_test_data": True,
                "created_at": now,
                "updated_at": now
            })
            logger.info("Ensured isolated test project: %s", cls.TEST_PROJECT_ID)

        # 4. Ensure isolated test task exists
        existing_task = db.tasks.find_one({"task_id": cls.TEST_TASK_ID})
        if not existing_task:
            db.tasks.insert_one({
                "task_id": cls.TEST_TASK_ID,
                "project_id": cls.TEST_PROJECT_ID,
                "title": "Employee Dashboard Verification & Walkthrough",
                "description": "Perform comprehensive verification of clock-in/out, breaks, leaves, diary logs, and profile self-edits.",
                "assigned_employee_id": cls.TEST_EMP_ID,
                "assigned_to": cls.TEST_EMP_ID,
                "status": "In Progress",
                "progress_percentage": 50,
                "weight": 1.0,
                "due_date": "2026-12-31",
                "notes": "Isolated test task for EMP-TEST-999",
                "is_test_data": True,
                "created_by": "LEAD-1001",
                "created_at": now,
                "updated_at": now
            })
            logger.info("Ensured isolated test task: %s", cls.TEST_TASK_ID)

        # 5. Ensure isolated test notification exists
        existing_notif = db.notifications.find_one({
            "employee_id": cls.TEST_EMP_ID,
            "notification_id": cls.TEST_NOTIFICATION_ID
        })
        if not existing_notif:
            db.notifications.insert_one({
                "notification_id": cls.TEST_NOTIFICATION_ID,
                "employee_id": cls.TEST_EMP_ID,
                "type": "system",
                "title": "Welcome to AISamrat QA Testing",
                "message": "This is your dedicated temporary test account. All attendance, leave requests, and diary entries are isolated to this account.",
                "is_read": False,
                "is_test_data": True,
                "created_at": now
            })
            logger.info("Ensured isolated test notification: %s", cls.TEST_NOTIFICATION_ID)

        return db.users.find_one({"employee_id": cls.TEST_EMP_ID})
