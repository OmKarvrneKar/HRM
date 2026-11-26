"""
SQLAlchemy User Model & Hybrid Query Interface
AISAMRAT HRMS — Enterprise RBAC & Universal Authentication Model
"""

import re
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

from sqlalchemy import (
    Column,
    String,
    Boolean,
    DateTime,
    Integer,
    Text,
    create_engine,
    or_,
    and_
)
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import declarative_base, sessionmaker, scoped_session
from werkzeug.security import check_password_hash

logger = logging.getLogger(__name__)

Base = declarative_base()

# SQLite in-memory engine supporting SQLAlchemy or_ queries with thread-safe scoped session and StaticPool
DB_PATH = "sqlite:///:memory:"
engine = create_engine(
    DB_PATH,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
    echo=False
)
SessionFactory = sessionmaker(bind=engine, autoflush=True, autocommit=False)
db_session = scoped_session(SessionFactory)


class User(Base):
    """
    SQLAlchemy User Model representing enterprise accounts across all 5 roles:
    - Employee / Intern (AS-1001 to AS-1034)
    - Team Lead (TL-1001)
    - Manager (MGR-1001)
    - HR Officer (HR-1001)
    - System Administrator (ADMIN-1001)
    """
    __tablename__ = "users"
    query = db_session.query_property()

    id = Column(Integer, primary_key=True, autoincrement=True)
    mongo_id = Column(String(50), nullable=True)
    emp_id = Column(String(50), index=True, nullable=True)
    employee_id = Column(String(50), index=True, nullable=True)
    username = Column(String(100), index=True, nullable=True)
    email = Column(String(150), index=True, nullable=True)
    personal_email = Column(String(150), index=True, nullable=True)
    official_email = Column(String(150), index=True, nullable=True)
    full_name = Column(String(150), nullable=True)
    name = Column(String(150), nullable=True)
    role = Column(String(50), nullable=False, default="employee")
    department = Column(String(100), nullable=True)
    designation = Column(String(100), nullable=True)
    team_id = Column(String(50), nullable=True)
    phone_number = Column(String(50), nullable=True)
    password_hash = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True)
    is_email_verified = Column(Boolean, default=True)
    account_status = Column(String(50), default="active")
    status = Column(String(50), default="active")
    needs_password_setup = Column(Boolean, default=False)
    joining_date = Column(String(50), nullable=True)
    date_of_birth = Column(String(50), nullable=True)

    def check_password(self, password: str) -> bool:
        """Verifies password using Werkzeug's secure hash algorithm."""
        if not self.password_hash or not password:
            return False
        return check_password_hash(self.password_hash, password)

    def get(self, key: str, default: Any = None) -> Any:
        if key in ("_id", "id"):
            val = getattr(self, "mongo_id", None) or getattr(self, "emp_id", None) or getattr(self, "employee_id", None)
            return val if val is not None else (str(self.id) if self.id is not None else default)
        val = getattr(self, key, None)
        if val is None and key == "emp_id":
            return getattr(self, "employee_id", default)
        if val is None and key == "employee_id":
            return getattr(self, "emp_id", default)
        if val is None and key == "name":
            return getattr(self, "full_name", default)
        if val is None and key == "full_name":
            return getattr(self, "name", default)
        return val if val is not None else default

    def __getitem__(self, item: str) -> Any:
        val = self.get(item)
        if val is None:
            raise KeyError(item)
        return val

    def __contains__(self, item: str) -> bool:
        return hasattr(self, item) and getattr(self, item) is not None

    def to_dict(self) -> Dict[str, Any]:
        """Serializes user record into standard dictionary."""
        record_id = str(self.mongo_id or self.emp_id or self.employee_id or self.id or "")
        return {
            "_id": record_id,
            "id": record_id,
            "emp_id": self.emp_id or self.employee_id,
            "employee_id": self.employee_id or self.emp_id,
            "username": self.username,
            "email": self.email,
            "personal_email": self.personal_email,
            "official_email": self.official_email,
            "full_name": self.full_name or self.name,
            "name": self.name or self.full_name,
            "role": (self.role or "employee").lower(),
            "department": self.department,
            "designation": self.designation,
            "team_id": self.team_id,
            "phone_number": self.phone_number,
            "password_hash": self.password_hash,
            "is_active": self.is_active,
            "is_email_verified": self.is_email_verified,
            "account_status": self.account_status,
            "status": self.status,
            "needs_password_setup": self.needs_password_setup,
            "joining_date": self.joining_date,
            "date_of_birth": self.date_of_birth
        }


def init_sqla_db():
    """Initializes SQLAlchemy database schema."""
    Base.metadata.create_all(engine)


# Create tables in the engine
init_sqla_db()


def sync_users_from_db(db=None):
    """
    Synchronizes users from the active MongoDB/in-memory database into the SQLAlchemy session.
    Guarantees that User.query.filter(or_(...)) finds all enterprise users.
    """
    try:
        init_sqla_db()
        from backend.database.connection import DatabaseManager
        active_db = db if db is not None else DatabaseManager.get_db()
        mongo_users = list(active_db.users.find({}))

        session = db_session()
        for doc in mongo_users:
            emp_id = doc.get("emp_id") or doc.get("employee_id")
            email = doc.get("email")

            existing = session.query(User).filter(
                or_(
                    User.emp_id == emp_id,
                    User.employee_id == emp_id,
                    User.email == email
                )
            ).first() if (emp_id or email) else None

            if not existing:
                existing = User()
                session.add(existing)

            existing.mongo_id = str(doc.get("_id") or emp_id or "")
            existing.emp_id = emp_id
            existing.employee_id = doc.get("employee_id") or emp_id
            existing.username = doc.get("username") or (emp_id.lower() if emp_id else None)
            existing.email = email
            existing.personal_email = doc.get("personal_email")
            existing.official_email = doc.get("official_email")
            existing.full_name = doc.get("full_name") or doc.get("name")
            existing.name = doc.get("name") or doc.get("full_name")
            existing.role = (doc.get("role") or "employee").lower()
            existing.department = doc.get("department")
            existing.designation = doc.get("designation")
            existing.team_id = doc.get("team_id")
            existing.phone_number = doc.get("phone_number")
            existing.password_hash = doc.get("password_hash")
            existing.is_active = doc.get("is_active", True)
            existing.is_email_verified = doc.get("is_email_verified", True)
            existing.account_status = doc.get("account_status", "active")
            existing.status = doc.get("status", "active")
            existing.needs_password_setup = doc.get("needs_password_setup", False)
            existing.joining_date = str(doc.get("joining_date")) if doc.get("joining_date") else None
            existing.date_of_birth = str(doc.get("date_of_birth")) if doc.get("date_of_birth") else None

        session.commit()
    except Exception as e:
        logger.warning("Could not sync users to SQLAlchemy: %s", e)
        db_session.rollback()


def find_user_by_identifier(identifier: str) -> Optional[User]:
    """
    Platform-wide user lookup using SQLAlchemy or_.
    Matches email, emp_id, employee_id, or username across all enterprise accounts.
    """
    if not identifier:
        return None

    clean_id = str(identifier).strip()
    sync_users_from_db()

    user = User.query.filter(
        or_(
            User.email == clean_id.lower(),
            User.emp_id == clean_id.upper(),
            User.employee_id == clean_id.upper(),
            User.username == clean_id.lower(),
            User.personal_email == clean_id.lower(),
            User.official_email == clean_id.lower()
        )
    ).first()

    return user

