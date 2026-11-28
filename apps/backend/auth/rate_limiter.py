from datetime import datetime, timezone, timedelta
from database.connection import get_db
from config import Config

class LoginRateLimiter:
    """MongoDB-backed rate limiter for login attempts per IP and email."""
    @classmethod
    def is_rate_limited(cls, ip_address: str, email: str) -> tuple[bool, int]:
        db = get_db()
        window_start = datetime.now(timezone.utc) - timedelta(seconds=Config.LOGIN_RATE_LIMIT_WINDOW_SECONDS)

        clean_email = email.strip().lower() if email else ""
        query = {"success": False, "created_at": {"$gte": window_start}}
        if clean_email:
            query["email"] = clean_email
        else:
            query["ip_address"] = ip_address

        failed_count = db.login_attempts.count_documents(query)

        if failed_count >= Config.LOGIN_RATE_LIMIT_ATTEMPTS:
            earliest = db.login_attempts.find_one(query, sort=[("created_at", 1)])
            if earliest and "created_at" in earliest:
                earliest_time = earliest["created_at"]
                if earliest_time.tzinfo is None:
                    earliest_time = earliest_time.replace(tzinfo=timezone.utc)
                elapsed = (datetime.now(timezone.utc) - earliest_time).total_seconds()
                remaining = max(1, int(Config.LOGIN_RATE_LIMIT_WINDOW_SECONDS - elapsed))
                return True, remaining
            return True, Config.LOGIN_RATE_LIMIT_WINDOW_SECONDS

        return False, 0

    @classmethod
    def record_attempt(cls, ip_address: str, email: str, success: bool):
        db = get_db()
        db.login_attempts.insert_one({
            "ip_address": ip_address,
            "email": email.strip().lower() if email else "",
            "success": success,
            "created_at": datetime.now(timezone.utc)
        })

    @classmethod
    def reset_attempts(cls, ip_address: str, email: str):
        db = get_db()
        db.login_attempts.delete_many({
            "$or": [{"ip_address": ip_address}, {"email": email.strip().lower() if email else ""}],
            "success": False
        })
