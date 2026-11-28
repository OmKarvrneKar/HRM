from datetime import datetime, timezone
from bson import ObjectId
from database.connection import get_db
from permissions.rbac import Role


class NotificationService:
    @classmethod
    def resolve_destination_url(
        cls,
        category: str,
        reference_id: str = None,
        recipient_role: str = None,
        fallback_link: str = None
    ) -> str:
        """Explicit mapping from notification category and record ID to authorized destination route."""
        # If caller passed fallback_link as 3rd positional argument (i.e. starts with / or #)
        if recipient_role and (recipient_role.startswith("/") or recipient_role == "#"):
            fallback_link = recipient_role
            recipient_role = None

        if fallback_link and fallback_link != "#" and fallback_link.startswith("/"):
            return fallback_link

        cat = (category or "GENERAL").upper()
        if not reference_id:
            return fallback_link or "/notifications"

        if "LEAVE" in cat:
            if recipient_role in ("hr", "hr_manager"):
                return f"/leaves/approvals?request_id={reference_id}"
            return f"/leaves?request_id={reference_id}"
        elif "PROJECT_CHAT" in cat:
            proj_id = reference_id.replace("PRJ-CHAT-", "")
            return f"/inbox?project_id={proj_id}"
        elif "DIRECT_MESSAGE" in cat or "CHAT" in cat:
            return f"/inbox?conversation_id={reference_id}"
        elif "PROJECT" in cat:
            return f"/projects/{reference_id}"
        elif "COMPLAINT" in cat:
            return f"/complaints/{reference_id}"
        elif "SKILL" in cat:
            return f"/skills"
        elif "ATTENDANCE" in cat:
            return f"/attendance"
        elif "BIRTHDAY" in cat:
            return "/birthdays"

        return fallback_link or "/notifications"

    @classmethod
    def create_notification(
        cls,
        title: str,
        message: str,
        category: str = "GENERAL",
        recipient_id: str = None,
        recipient_group: str = None,
        link: str = None,
        reference_id: str = None,
        idempotency_key: str = None,
        priority: str = "NORMAL",
        user_id: str = None
    ) -> dict | None:
        if not recipient_id and user_id:
            recipient_id = user_id
        db = get_db()
        if idempotency_key:
            existing = db.notifications.find_one({"idempotency_key": idempotency_key})
            if existing:
                return existing

        recipient_role = None
        if recipient_id:
            u = db.users.find_one({"employee_id": recipient_id}, {"role": 1})
            if u:
                recipient_role = u.get("role")
        elif recipient_group in ("HR", "hr", "hr_manager"):
            recipient_role = "hr"

        resolved_link = cls.resolve_destination_url(
            category=category,
            reference_id=reference_id,
            recipient_role=recipient_role,
            fallback_link=link
        )

        notif_doc = {
            "title": title,
            "message": message,
            "category": category,
            "recipient_id": recipient_id,
            "recipient_group": recipient_group,
            "reference_id": reference_id,
            "link": resolved_link,
            "destination_url": resolved_link,
            "priority": priority,
            "is_read": False,
            "read_by": [],
            "created_at": datetime.now(timezone.utc)
        }
        if idempotency_key:
            notif_doc["idempotency_key"] = idempotency_key

        try:
            res = db.notifications.insert_one(notif_doc)
            notif_doc["_id"] = res.inserted_id
            return notif_doc
        except Exception:
            if idempotency_key:
                return db.notifications.find_one({"idempotency_key": idempotency_key})
            return None

    @classmethod
    def get_user_notifications(cls, user: dict, unread_only: bool = False, limit: int = 50) -> list:
        db = get_db()
        emp_id = user["employee_id"]
        role = user.get("role")
        dept = user.get("department")

        target_groups = ["ALL"]
        if role == Role.EMPLOYEE:
            target_groups.extend(["EMPLOYEES", f"DEPT:{dept}"])
        elif role == Role.HR:
            target_groups.extend(["HR", "EMPLOYEES", f"DEPT:{dept}"])
        elif role == Role.HR_MANAGER:
            target_groups.extend(["HR_MANAGERS", "HR", "EMPLOYEES", f"DEPT:{dept}"])
        elif role == Role.TEAM_LEAD:
            target_groups.extend(["TEAM_LEAD", "TEAM_LEADS", "EMPLOYEES", f"DEPT:{dept}"])
        elif role in (Role.MANAGER, Role.ADMIN, Role.ORGANIZATION):
            target_groups.extend(["MANAGER", "MANAGERS", "EMPLOYEES", f"DEPT:{dept}"])

        if unread_only:
            query = {
                "read_by": {"$ne": emp_id},
                "$or": [
                    {"recipient_id": emp_id, "is_read": False},
                    {"recipient_group": {"$in": target_groups}}
                ]
            }
        else:
            query = {
                "$or": [
                    {"recipient_id": emp_id},
                    {"recipient_group": {"$in": target_groups}}
                ]
            }

        docs = list(db.notifications.find(query).sort("created_at", -1).limit(limit))
        results = []
        for n in docs:
            n_copy = dict(n)
            # Personalize is_read per employee for group announcements
            if n_copy.get("recipient_group"):
                n_copy["is_read"] = emp_id in n_copy.get("read_by", [])
            else:
                n_copy["is_read"] = bool(n_copy.get("is_read")) or emp_id in n_copy.get("read_by", [])
            results.append(n_copy)
        return results

    @classmethod
    def mark_as_read(cls, notification_id: str, user: dict) -> bool:
        db = get_db()
        emp_id = user["employee_id"]
        try:
            obj_id = ObjectId(notification_id)
        except Exception:
            return False

        notif = db.notifications.find_one({"_id": obj_id})
        if not notif:
            return False

        update_ops = {"$addToSet": {"read_by": emp_id}}
        # If personal notification, set is_read = True globally
        if notif.get("recipient_id") == emp_id or not notif.get("recipient_group"):
            update_ops["$set"] = {"is_read": True}

        result = db.notifications.update_one({"_id": obj_id}, update_ops)
        return result.matched_count == 1

    @classmethod
    def mark_all_as_read(cls, user: dict) -> int:
        notifs = cls.get_user_notifications(user, unread_only=True)
        count = 0
        for n in notifs:
            cls.mark_as_read(str(n["_id"]), user)
            count += 1
        return count
