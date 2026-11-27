"""
Data models package for AI Samrat HRMS.
Provides SQLAlchemy User models and query interfaces.
"""

from backend.models.user import (
    Base,
    User,
    db_session,
    find_user_by_identifier,
    sync_users_from_db
)

__all__ = [
    "Base",
    "User",
    "db_session",
    "find_user_by_identifier",
    "sync_users_from_db"
]

