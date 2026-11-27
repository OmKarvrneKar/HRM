import logging
import secrets
from datetime import datetime, date, timezone
from backend.database.connection import get_db
from backend.utils.serializers import serialize_doc
from backend.services.audit_service import AuditService
from backend.permissions.rbac import Role

logger = logging.getLogger(__name__)

STANDARD_HOLIDAYS = [
    ("01-01", "New Year's Day", "Public"),
    ("01-26", "Republic Day", "National"),
    ("05-01", "May Day / International Workers' Day", "Public"),
    ("08-15", "Independence Day", "National"),
    ("10-02", "Mahatma Gandhi Jayanti", "National"),
    ("11-01", "Kannada Rajyotsava", "State"),
    ("12-25", "Christmas", "Public")
]


class HolidayService:
    """Manages organization holidays and public/state calendars."""

    @classmethod
    def seed_default_holidays(cls, db=None, target_year: int = None):
        """Alias to ensure standard holidays are present in the collection."""
        cls.ensure_seeded(target_year)

    @classmethod
    def ensure_seeded(cls, target_year: int = None):
        """Ensures that the standard annual holidays are seeded in MongoDB."""
        db = get_db()
        current_year = target_year or datetime.now().year
        
        # Check if holidays exist for the current year
        year_prefix = f"{current_year}-"
        count = db.holidays.count_documents({"date": {"$regex": f"^{year_prefix}"}})
        if count == 0:
            logger.info("Seeding standard corporate holidays for year %d...", current_year)
            seeded_docs = []
            for md, name, h_type in STANDARD_HOLIDAYS:
                doc = {
                    "holiday_id": f"HOL-{current_year}-{secrets.token_hex(4).upper()}",
                    "date": f"{current_year}-{md}",
                    "name": name,
                    "type": h_type,
                    "added_by": "SYSTEM",
                    "created_at": datetime.now(timezone.utc)
                }
                seeded_docs.append(doc)
            if seeded_docs:
                db.holidays.insert_many(seeded_docs)

    @classmethod
    def get_all_holidays(cls, year: int = None) -> list[dict]:
        """Returns all holidays sorted chronologically from the database."""
        db = get_db()
        query = {}
        if year:
            query["date"] = {"$regex": f"^{year}-"}
        
        holidays = list(db.holidays.find(query, {"_id": 0}).sort("date", 1))
        return holidays

    @classmethod
    def get_upcoming_holidays(cls, limit: int = 6) -> list[dict]:
        """Returns upcoming holidays from today onward from the database."""
        db = get_db()
        today_iso = date.today().isoformat()
        holidays = list(
            db.holidays.find({"date": {"$gte": today_iso}}, {"_id": 0})
            .sort("date", 1)
            .limit(limit)
        )
        return holidays

    @classmethod
    def add_holiday(cls, actor: dict, date_str: str, name: str, holiday_type: str = "Public") -> tuple[dict | None, str | None]:
        """Adds a corporate holiday. Requires HR or HR Manager role."""
        actor_role = actor.get("role")
        if actor_role not in (Role.HR, Role.HR_MANAGER, Role.ORGANIZATION, Role.ADMIN):
            return None, "Access Denied: Only HR or Management may declare holidays."

        clean_name = (name or "").strip()
        clean_date = (date_str or "").strip()
        clean_type = (holiday_type or "Public").strip()

        if not clean_name:
            return None, "Holiday name is required."

        try:
            parsed_date = datetime.strptime(clean_date, "%Y-%m-%d").date()
        except ValueError:
            return None, "Invalid holiday date format. Use YYYY-MM-DD."

        db = get_db()
        existing = db.holidays.find_one({"date": clean_date})
        if existing:
            return None, f"A holiday on {clean_date} already exists: {existing.get('name')}."

        new_doc = {
            "holiday_id": f"HOL-{parsed_date.year}-{secrets.token_hex(4).upper()}",
            "date": clean_date,
            "name": clean_name,
            "type": clean_type,
            "added_by": actor.get("employee_id"),
            "created_at": datetime.now(timezone.utc)
        }

        db.holidays.insert_one(new_doc)
        new_doc.pop("_id", None)

        AuditService.log_action(
            actor=actor,
            action="ADD_HOLIDAY",
            target_type="holiday",
            target_id=new_doc["holiday_id"],
            details={"date": clean_date, "name": clean_name, "type": clean_type}
        )

        return new_doc, None

    @classmethod
    def delete_holiday(cls, actor: dict, holiday_id: str) -> tuple[bool, str | None]:
        """Deletes a corporate holiday. Requires HR or HR Manager role."""
        actor_role = actor.get("role")
        if actor_role not in (Role.HR, Role.HR_MANAGER, Role.ORGANIZATION, Role.ADMIN):
            return False, "Access Denied: Only HR or Management may remove holidays."

        db = get_db()
        existing = db.holidays.find_one({"holiday_id": holiday_id})
        if not existing:
            return False, "Holiday not found."

        db.holidays.delete_one({"holiday_id": holiday_id})

        AuditService.log_action(
            actor=actor,
            action="DELETE_HOLIDAY",
            target_type="holiday",
            target_id=holiday_id,
            details={"name": existing.get("name"), "date": existing.get("date")}
        )

        return True, None

    @classmethod
    def update_holiday(cls, actor: dict, holiday_id: str, date_str: str, name: str, holiday_type: str = "Public") -> tuple[dict | None, str | None]:
        """Updates a corporate holiday. Requires HR or HR Manager role."""
        actor_role = actor.get("role")
        if actor_role not in (Role.HR, Role.HR_MANAGER, Role.ORGANIZATION, Role.ADMIN):
            return None, "Access Denied: Only HR or Management may edit holidays."

        clean_name = (name or "").strip()
        clean_date = (date_str or "").strip()
        clean_type = (holiday_type or "Public").strip()

        if not clean_name or not clean_date:
            return None, "Holiday name and date are required."

        try:
            valid_date = datetime.strptime(clean_date, "%Y-%m-%d").date()
        except ValueError:
            return None, "Invalid date format. Expected YYYY-MM-DD."

        db = get_db()
        existing = db.holidays.find_one({"holiday_id": holiday_id})
        if not existing:
            return None, "Holiday not found."

        update_fields = {
            "name": clean_name,
            "date": clean_date,
            "type": clean_type,
            "year": valid_date.year,
            "updated_by": actor["employee_id"],
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        db.holidays.update_one({"holiday_id": holiday_id}, {"$set": update_fields})

        AuditService.log_action(
            actor=actor,
            action="UPDATE_HOLIDAY",
            target_type="holiday",
            target_id=holiday_id,
            details={"name": clean_name, "date": clean_date, "type": clean_type}
        )
        updated = db.holidays.find_one({"holiday_id": holiday_id})
        return serialize_doc(updated), None
