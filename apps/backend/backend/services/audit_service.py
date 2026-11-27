from datetime import datetime, timezone
from backend.database.connection import get_db
from backend.permissions.rbac import Role, normalize_role


class AuditService:
    @classmethod
    def log_action(
        cls,
        actor: dict,
        action: str,
        target_type: str,
        target_id: str,
        details: dict = None,
        ip_address: str = None
    ) -> dict:
        db = get_db()
        entry = {
            "actor_id": actor.get("employee_id") if actor else "system",
            "actor_name": actor.get("full_name") if actor else "System Automated",
            "actor_role": actor.get("role") if actor else "system",
            "action": action,
            "target_type": target_type,
            "target_id": target_id,
            "details": details or {},
            "ip_address": ip_address,
            "timestamp": datetime.now(timezone.utc),
        }
        db.audit_logs.insert_one(entry)
        return entry

    @classmethod
    def log_profile_change(
        cls,
        target_employee_id: str,
        field_name: str,
        old_value,
        new_value,
        changed_by: dict,
        reason: str = None
    ) -> dict:
        db = get_db()
        entry = {
            "target_employee_id": target_employee_id,
            "field_name": field_name,
            "old_value": old_value,
            "new_value": new_value,
            "changed_by_id": changed_by.get("employee_id"),
            "changed_by_name": changed_by.get("full_name"),
            "changed_by_role": changed_by.get("role"),
            "reason": reason or "Administrative update",
            "timestamp": datetime.now(timezone.utc)
        }
        db.profile_change_logs.insert_one(entry)
        return entry

    @classmethod
    def get_audit_logs(
        cls,
        actor_role: str,
        limit: int = 100,
        skip: int = 0,
        action: str = None,
        filter_role: str = None,
        target_type: str = None,
        date_from: str = None,
        date_to: str = None,
        search: str = None
    ) -> list:
        db = get_db()
        norm_role = normalize_role(actor_role)
        if norm_role not in (Role.HR, Role.ADMIN):
            return []

        query = {}
        allowed_hr_types = ["employee", "attendance", "complaint", "project", "leave", "skill", "user", "offboarding"]

        if action:
            query["action"] = action
        if filter_role:
            query["actor_role"] = filter_role

        # Role scope: Admin sees all; HR sees only operational HR target_types and cannot bypass via target_type param.
        if norm_role == Role.HR:
            if target_type:
                if target_type not in allowed_hr_types:
                    return []
                query["target_type"] = target_type
            else:
                query["target_type"] = {"$in": allowed_hr_types}
        elif target_type:
            query["target_type"] = target_type

        # Date range filtering
        if date_from or date_to:
            ts_query = {}
            if date_from:
                try:
                    df = datetime.fromisoformat(date_from).replace(tzinfo=timezone.utc)
                    ts_query["$gte"] = df
                except Exception:
                    pass
            if date_to:
                try:
                    dt = datetime.fromisoformat(date_to).replace(hour=23, minute=59, second=59, tzinfo=timezone.utc)
                    ts_query["$lte"] = dt
                except Exception:
                    pass
            if ts_query:
                query["timestamp"] = ts_query

        if search:
            query["$or"] = [
                {"actor_name": {"$regex": search, "$options": "i"}},
                {"actor_id": {"$regex": search, "$options": "i"}},
                {"action": {"$regex": search, "$options": "i"}},
                {"target_id": {"$regex": search, "$options": "i"}},
            ]
        
        return list(
            db.audit_logs.find(query)
            .sort("timestamp", -1)
            .skip(skip)
            .limit(limit)
        )
