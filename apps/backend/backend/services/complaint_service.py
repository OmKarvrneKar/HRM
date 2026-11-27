from datetime import datetime, timezone
from bson import ObjectId
from backend.database.connection import get_db
from backend.services.audit_service import AuditService
from backend.permissions.rbac import Role, can_access_complaint

VALID_STATUSES = [
    "Submitted",
    "Received",
    "Under Review",
    "Action Required",
    "Resolved",
    "Closed"
]

VALID_CATEGORIES = [
    "Workplace Harassment",
    "Policy or Legal Concern",
    "Workplace Environment",
    "Salary or Benefits Query",
    "General HR Query"
]


class ComplaintService:
    @classmethod
    def submit_complaint(cls, complainant: dict, data: dict) -> tuple[dict | None, str | None]:
        db = get_db()
        subject = data.get("subject", "").strip()
        description = data.get("description", "").strip()
        category = data.get("category", "General HR Query")

        if not subject or not description:
            return None, "Subject and description are required."

        count = db.complaints.count_documents({})
        complaint_id = f"CMP-{1001 + count}"

        complaint = {
            "complaint_id": complaint_id,
            "complainant_id": complainant["employee_id"],
            "complainant_name": complainant.get("full_name", ""),
            "complainant_email": complainant.get("email", ""),
            "category": category,
            "subject": subject,
            "description": description,
            "priority": data.get("priority", "Medium"),
            "status": "Submitted",
            "assigned_hr_id": None,
            "responses": [],
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
            "closed_at": None
        }

        db.complaints.insert_one(complaint)
        cls._notify_hr_new_complaint(complaint)

        AuditService.log_action(
            actor=complainant,
            action="SUBMIT_COMPLAINT",
            target_type="complaint",
            target_id=complaint_id,
            details={"category": category, "priority": complaint["priority"]}
        )

        return complaint, None

    @classmethod
    def add_response(
        cls,
        actor: dict,
        complaint_id: str,
        message: str,
        new_status: str = None
    ) -> tuple[dict | None, str | None]:
        if not message or not message.strip():
            return None, "Response message cannot be empty."

        db = get_db()
        complaint = db.complaints.find_one({"complaint_id": complaint_id})
        if not complaint:
            return None, "Complaint not found."

        if not can_access_complaint(actor, complaint):
            return None, "Access Denied: You do not have permission to view or respond to this complaint."

        response_entry = {
            "sender_id": actor["employee_id"],
            "sender_name": actor.get("full_name", ""),
            "sender_role": actor.get("role", ""),
            "message": message.strip(),
            "timestamp": datetime.now(timezone.utc)
        }

        updates = {
            "$push": {"responses": response_entry},
            "$set": {"updated_at": datetime.now(timezone.utc)}
        }

        if actor.get("role") == Role.HR:
            if not complaint.get("assigned_hr_id"):
                updates["$set"]["assigned_hr_id"] = actor["employee_id"]

            if new_status and new_status in VALID_STATUSES:
                updates["$set"]["status"] = new_status
                if new_status == "Closed":
                    updates["$set"]["closed_at"] = datetime.now(timezone.utc)

        db.complaints.update_one({"complaint_id": complaint_id}, updates)

        AuditService.log_action(
            actor=actor,
            action="COMPLAINT_RESPONSE",
            target_type="complaint",
            target_id=complaint_id,
            details={"status": new_status or complaint.get("status")}
        )

        updated_complaint = db.complaints.find_one({"complaint_id": complaint_id})
        return updated_complaint, None

    @classmethod
    def update_status(cls, actor: dict, complaint_id: str, new_status: str) -> tuple[dict | None, str | None]:
        if actor.get("role") != Role.HR:
            return None, "Only HR personnel can update complaint status."

        if new_status not in VALID_STATUSES:
            return None, f"Invalid status '{new_status}'."

        db = get_db()
        complaint = db.complaints.find_one({"complaint_id": complaint_id})
        if not complaint:
            return None, "Complaint not found."

        updates = {
            "status": new_status,
            "updated_at": datetime.now(timezone.utc)
        }
        if new_status == "Closed":
            updates["closed_at"] = datetime.now(timezone.utc)

        db.complaints.update_one({"complaint_id": complaint_id}, {"$set": updates})

        AuditService.log_action(
            actor=actor,
            action="UPDATE_COMPLAINT_STATUS",
            target_type="complaint",
            target_id=complaint_id,
            details={"previous_status": complaint.get("status"), "new_status": new_status}
        )

        updated_complaint = db.complaints.find_one({"complaint_id": complaint_id})
        return updated_complaint, None

    @classmethod
    def get_user_complaints(cls, user: dict) -> list:
        role = user.get("role")
        db = get_db()

        if role == Role.EMPLOYEE:
            return list(db.complaints.find({"complainant_id": user["employee_id"]}).sort("created_at", -1))
        elif role == Role.HR:
            return list(db.complaints.find().sort("created_at", -1))
        else:
            return []

    @classmethod
    def _notify_hr_new_complaint(cls, complaint: dict):
        db = get_db()
        db.notifications.insert_one({
            "recipient_group": "HR",
            "title": "New Workplace Complaint Submitted",
            "message": f"A new complaint '{complaint['subject']}' ({complaint['category']}) has been filed.",
            "category": "COMPLAINT",
            "link": f"/complaints/{complaint['complaint_id']}",
            "is_read": False,
            "created_at": datetime.now(timezone.utc)
        })
