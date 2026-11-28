import pytest
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from datetime import datetime, timezone
from bson import ObjectId
from app import create_app
from config import TestConfig
from database.connection import DatabaseManager
from database.indexes import setup_indexes
from auth.security import hash_password, generate_jwt_token
from permissions.rbac import Role


@pytest.fixture(scope="session")
def app():
    # Use separate test database
    app_instance = create_app(config_class=TestConfig, start_scheduler=False)
    yield app_instance
    # Clean up test DB
    db = DatabaseManager.get_db(db_name=TestConfig.DATABASE_NAME)
    db.client.drop_database(TestConfig.DATABASE_NAME)


@pytest.fixture(scope="session")
def client(app):
    return app.test_client()


@pytest.fixture(scope="function")
def db(app):
    database = DatabaseManager.get_db(db_name=TestConfig.DATABASE_NAME)
    # Clear collections before each test function
    for col in [
        "users", "attendance_events", "attendance_daily", "projects",
        "teams", "tasks", "notifications", "complaints", "profile_change_logs",
        "audit_logs", "organization_settings", "login_attempts", "work_diary",
        "leave_requests", "holidays", "skills", "skill_recommendations",
        "conversations", "messages", "offboardings", "chat_attachments",
        "external_message_logs", "otp_tokens"
    ]:
        database[col].delete_many({})
    setup_indexes(database)
    DatabaseManager.set_db(database)
    return database


@pytest.fixture
def seeded_users(db):
    """Creates a standard set of test users across the four canonical application roles."""
    users = {
        "manager": {
            "employee_id": "MGR-TEST",
            "full_name": "Test Operations Manager",
            "email": "manager.test@hrm.local",
            "password_hash": hash_password("Manager@123"),
            "role": Role.MANAGER,
            "department": "Operations",
            "is_active": True,
            "created_at": datetime.now(timezone.utc)
        },
        "hr_manager": {
            "employee_id": "HRM-TEST",
            "full_name": "Test Senior HR Lead",
            "email": "hrlead.test@hrm.local",
            "password_hash": hash_password("Manager@123"),
            "role": Role.HR,
            "department": "Human Resources",
            "is_active": True,
            "created_at": datetime.now(timezone.utc)
        },
        "hr": {
            "employee_id": "HR-TEST",
            "full_name": "Test HR Officer",
            "email": "hr.test@hrm.local",
            "password_hash": hash_password("Hr@Pass123"),
            "role": Role.HR,
            "department": "Human Resources",
            "is_active": True,
            "created_at": datetime.now(timezone.utc)
        },
        "emp1": {
            "employee_id": "EMP-TEST-1",
            "full_name": "Employee One",
            "email": "emp1.test@hrm.local",
            "password_hash": hash_password("Emp1@Pass123"),
            "role": Role.EMPLOYEE,
            "department": "Engineering",
            "is_active": True,
            "created_at": datetime.now(timezone.utc)
        },
        "emp2": {
            "employee_id": "EMP-TEST-2",
            "full_name": "Employee Two",
            "email": "emp2.test@hrm.local",
            "password_hash": hash_password("Emp2@Pass123"),
            "role": Role.EMPLOYEE,
            "department": "Design",
            "is_active": True,
            "created_at": datetime.now(timezone.utc)
        },
        "inactive": {
            "employee_id": "EMP-INACTIVE",
            "full_name": "Deactivated Employee",
            "email": "inactive.test@hrm.local",
            "password_hash": hash_password("Inactive@123"),
            "role": Role.EMPLOYEE,
            "department": "Engineering",
            "is_active": False,
            "created_at": datetime.now(timezone.utc)
        },
        "trainer": {
            "employee_id": "TRN-TEST",
            "full_name": "Test Corporate Training Lead",
            "email": "trainer.test@hrm.local",
            "password_hash": hash_password("Trainer@123"),
            "role": Role.TEAM_LEAD,
            "department": "Training",
            "is_active": True,
            "created_at": datetime.now(timezone.utc)
        },
        "team_lead": {
            "employee_id": "LEAD-TEST",
            "full_name": "Test Team Lead",
            "email": "lead.test@hrm.local",
            "password_hash": hash_password("Lead@123"),
            "role": Role.TEAM_LEAD,
            "department": "Engineering",
            "team_id": "TEAM-TEST-ENG",
            "is_active": True,
            "created_at": datetime.now(timezone.utc)
        }
    }

    inserted = {}
    for key, doc in users.items():
        res = db.users.insert_one(doc)
        doc["_id"] = res.inserted_id
        inserted[key] = doc

    return inserted


@pytest.fixture
def tokens(seeded_users):
    """Generates valid JWT tokens for each seeded test user."""
    return {
        key: generate_jwt_token(user)
        for key, user in seeded_users.items()
    }
