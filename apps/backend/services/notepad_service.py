import logging
import uuid
from datetime import datetime, timezone
from database.connection import get_db
from utils.serializers import serialize_doc, serialize_docs
from utils.timezone import now_utc

logger = logging.getLogger(__name__)


class NotepadService:
    """
    Multi-Pad Notepad Service for AISamrat HRMS:
    Allows employees across all roles to create, edit, customize colors, pin,
    and persist individual notes and sticky pads backed by MongoDB.
    """

    DEFAULT_PRESET_COLORS = [
        {"name": "Neural Blue", "code": "#0066ff", "bg": "rgba(0, 102, 255, 0.12)", "border": "rgba(0, 102, 255, 0.4)"},
        {"name": "Cyber Cyan", "code": "#00e5ff", "bg": "rgba(0, 229, 255, 0.12)", "border": "rgba(0, 229, 255, 0.4)"},
        {"name": "Emerald Green", "code": "#10b981", "bg": "rgba(16, 185, 129, 0.12)", "border": "rgba(16, 185, 129, 0.4)"},
        {"name": "Amber Gold", "code": "#f59e0b", "bg": "rgba(245, 158, 11, 0.12)", "border": "rgba(245, 158, 11, 0.4)"},
        {"name": "Violet Neon", "code": "#8b5cf6", "bg": "rgba(139, 92, 246, 0.12)", "border": "rgba(139, 92, 246, 0.4)"}
    ]

    @classmethod
    def get_user_notes(cls, employee_id: str) -> list[dict]:
        """
        Retrieves all notes owned by this employee, sorted by is_pinned desc, updated_at desc.
        If user has zero notes, automatically provisions a starter note.
        """
        db = get_db()
        notes = list(db.user_notepads.find(
            {"employee_id": employee_id, "is_deleted": {"$ne": True}}
        ).sort([("is_pinned", -1), ("updated_at", -1)]))

        if not notes:
            starter = cls.create_note(employee_id, {
                "title": "Welcome to AISamrat Multi-Pad",
                "content": "✨ Welcome to your personal Multi-Pad Notepad!\n\n• Organize your daily deliverables and code snippets here.\n• Click '+ New Pad' to open independent working pads.\n• Changes auto-save securely to your profile across all your devices.",
                "color": "#00e5ff",
                "is_pinned": True
            })
            return [starter]

        return serialize_docs(notes)

    @classmethod
    def get_note(cls, employee_id: str, note_id: str) -> dict | None:
        db = get_db()
        doc = db.user_notepads.find_one({
            "employee_id": employee_id,
            "note_id": note_id,
            "is_deleted": {"$ne": True}
        })
        return serialize_doc(doc) if doc else None

    @classmethod
    def create_note(cls, employee_id: str, data: dict) -> dict:
        db = get_db()
        note_id = f"NOTE-{uuid.uuid4().hex[:10].upper()}"
        title = (data.get("title") or "New Notepad").strip()
        content = data.get("content", "")
        color = data.get("color") or "#0066ff"
        is_pinned = bool(data.get("is_pinned", False))

        doc = {
            "note_id": note_id,
            "employee_id": employee_id,
            "title": title,
            "content": content,
            "color": color,
            "is_pinned": is_pinned,
            "is_deleted": False,
            "created_at": now_utc(),
            "updated_at": now_utc()
        }

        db.user_notepads.insert_one(doc)
        logger.info("Created notepad %s for employee %s", note_id, employee_id)
        return serialize_doc(doc)

    @classmethod
    def update_note(cls, employee_id: str, note_id: str, data: dict) -> tuple[dict | None, str | None]:
        db = get_db()
        existing = db.user_notepads.find_one({
            "employee_id": employee_id,
            "note_id": note_id,
            "is_deleted": {"$ne": True}
        })
        if not existing:
            return None, "Notepad not found or permission denied."

        updates = {"updated_at": now_utc()}
        if "title" in data:
            updates["title"] = (data.get("title") or "Untitled Pad").strip()
        if "content" in data:
            updates["content"] = data.get("content", "")
        if "color" in data:
            updates["color"] = data.get("color")
        if "is_pinned" in data:
            updates["is_pinned"] = bool(data.get("is_pinned"))

        db.user_notepads.update_one(
            {"employee_id": employee_id, "note_id": note_id},
            {"$set": updates}
        )

        updated = db.user_notepads.find_one({"employee_id": employee_id, "note_id": note_id})
        return serialize_doc(updated), None

    @classmethod
    def delete_note(cls, employee_id: str, note_id: str) -> tuple[bool, str | None]:
        db = get_db()
        res = db.user_notepads.update_one(
            {"employee_id": employee_id, "note_id": note_id},
            {"$set": {"is_deleted": True, "updated_at": now_utc()}}
        )
        if res.matched_count == 0:
            return False, "Notepad not found or already deleted."
        return True, None

