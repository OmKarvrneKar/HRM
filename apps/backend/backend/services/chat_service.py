import os
import uuid
import logging
from pathlib import Path
from datetime import datetime, timezone
from bson import ObjectId
from werkzeug.utils import secure_filename
from backend.database.connection import get_db
from backend.permissions.rbac import Role
from backend.services.audit_service import AuditService
from backend.services.notification_service import NotificationService
from backend.utils.serializers import serialize_doc, serialize_docs

logger = logging.getLogger(__name__)

# Security configurations for file attachments
ALLOWED_EXTENSIONS = {
    ".pdf", ".docx", ".doc", ".xlsx", ".xls", ".csv",
    ".txt", ".png", ".jpg", ".jpeg", ".webp", ".gif"
}

DANGEROUS_EXTENSIONS = {
    ".exe", ".bat", ".cmd", ".sh", ".vbs", ".js", ".py", ".dll",
    ".msi", ".php", ".phtml", ".scr", ".jar", ".com", ".reg",
    ".ps1", ".hta", ".bin", ".iso", ".apk", ".deb", ".rpm"
}

MAX_ATTACHMENT_SIZE_BYTES = 15 * 1024 * 1024  # 15 MB


def get_chat_attachments_base_dir() -> Path:
    """Returns the dedicated private directory for chat attachments outside static public web paths."""
    import tempfile

    env_dir = os.getenv("CHAT_ATTACHMENTS_DIR")
    if env_dir:
        p = Path(env_dir)
        try:
            p.mkdir(parents=True, exist_ok=True)
            return p
        except Exception:
            pass

    candidates = [
        Path.home() / ".ai_samrat_hrms" / "data" / "chat_attachments",
        Path(__file__).resolve().parent.parent.parent / "data" / "storage" / "chat_attachments",
        Path(tempfile.gettempdir()) / "ai_samrat_chat_attachments",
    ]
    for c in candidates:
        try:
            c.mkdir(parents=True, exist_ok=True)
            test_f = c / f".test_{uuid.uuid4().hex[:6]}"
            test_f.write_text("ok", encoding="utf-8")
            if test_f.exists():
                test_f.unlink()
            return c
        except Exception:
            continue

    fallback = Path(tempfile.gettempdir()) / "ai_samrat_chat_attachments"
    try:
        fallback.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    return fallback


class ChatService:
    """
    Unified chat service managing automatic project group conversations,
    private direct messages, message unsending, and secure file attachments with strict RBAC.
    """

    @classmethod
    def is_project_chat(cls, conv: dict) -> tuple[bool, dict | None]:
        """
        Determines whether a conversation is an approved project chat
        using actual database relationships and project IDs, NOT display names.
        """
        if not conv:
            return False, None

        project_id = conv.get("project_id")
        conv_id = conv.get("conversation_id", "")

        if not project_id and conv_id.startswith("PRJ-CHAT-"):
            project_id = conv_id.replace("PRJ-CHAT-", "").strip()

        db = get_db()
        if project_id:
            project = db.projects.find_one({"project_id": project_id})
            if project:
                return True, project

        if conv.get("type") == "project":
            return True, None

        return False, None

    @classmethod
    def ensure_project_chat(cls, project: dict, creator: dict = None) -> dict:
        """
        Idempotently creates or updates the default private group conversation for a project.
        Uses a stable conversation ID based on the project ID.
        Synchronizes participant access with project membership.
        """
        db = get_db()
        project_id = project["project_id"]
        conv_id = f"PRJ-CHAT-{project_id}"

        # Group chat is strictly created ONLY after Manager approval
        proj_status = str(project.get("status", "")).strip().upper()
        if proj_status in ("DRAFT", "PENDING_APPROVAL", "CHANGES_REQUESTED", "REJECTED") and not project.get("is_approved"):
            return None

        # Collect authorized participant employee IDs
        raw_members = project.get("members", [])
        if isinstance(raw_members, str):
            raw_members = [m.strip().upper() for m in raw_members.split(",") if m.strip()]
        
        participants = set(str(m).strip().upper() for m in raw_members if str(m).strip())

        if project.get("manager_employee_id"):
            participants.add(str(project["manager_employee_id"]).strip().upper())
        if project.get("assigned_manager"):
            participants.add(str(project["assigned_manager"]).strip().upper())
        if project.get("project_lead"):
            participants.add(str(project["project_lead"]).strip().upper())
        if project.get("trainer_employee_id"):
            participants.add(str(project["trainer_employee_id"]).strip().upper())
        if project.get("assigned_trainer_id"):
            participants.add(str(project["assigned_trainer_id"]).strip().upper())
        if creator and creator.get("employee_id"):
            participants.add(str(creator["employee_id"]).strip().upper())
        if project.get("created_by"):
            participants.add(str(project["created_by"]).strip().upper())

        participant_ids = sorted(list(participants))

        # Build participant names mapping
        user_docs = list(db.users.find({"employee_id": {"$in": participant_ids}}, {"employee_id": 1, "full_name": 1, "role": 1}))
        participant_names = {u["employee_id"]: u.get("full_name", u["employee_id"]) for u in user_docs}

        title = project.get("title") or project.get("name") or project_id
        status = "archived" if project.get("status") == "Archived" else "active"

        existing = db.conversations.find_one({"conversation_id": conv_id})

        if existing:
            db.conversations.update_one(
                {"conversation_id": conv_id},
                {
                    "$set": {
                        "name": title,
                        "title": title,
                        "is_group": True,
                        "project_title": project.get("title", ""),
                        "participant_ids": participant_ids,
                        "participants": participant_ids,
                        "participant_names": participant_names,
                        "status": status,
                        "updated_at": datetime.now(timezone.utc)
                    }
                }
            )
            return db.conversations.find_one({"conversation_id": conv_id})

        # Create new project chat
        now = datetime.now(timezone.utc)
        conv_doc = {
            "conversation_id": conv_id,
            "type": "project",
            "is_group": True,
            "name": title,
            "project_id": project_id,
            "title": title,
            "project_title": project.get("title", ""),
            "participant_ids": participant_ids,
            "participants": participant_ids,
            "participant_names": participant_names,
            "created_by": creator.get("employee_id") if creator else (project.get("created_by") or "SYSTEM"),
            "status": status,
            "created_at": now,
            "updated_at": now,
            "last_message": {
                "content": f"Project group chat opened for '{project.get('title', project_id)}'. Collaboration is restricted to assigned members.",
                "sender_id": "SYSTEM",
                "sender_name": "AI Samrat System",
                "timestamp": now
            }
        }

        db.conversations.insert_one(conv_doc)

        # Insert initial system announcement message
        init_message = {
            "conversation_id": conv_id,
            "sender_id": "SYSTEM",
            "sender_name": "AI Samrat HRMS",
            "sender_role": "system",
            "content": f"Official project chat initialized for '{project.get('title', project_id)}' ({project_id}). Only authorized team members and leads may participate.",
            "timestamp": now,
            "read_by": participant_ids,
            "is_unsent": False
        }
        db.messages.insert_one(init_message)

        return conv_doc

    @classmethod
    def get_or_create_direct_chat(cls, user1: dict, user2: dict) -> dict:
        """Creates or retrieves a 1-on-1 private direct conversation between two authorized users."""
        db = get_db()
        id1 = str(user1["employee_id"]).strip().upper()
        id2 = str(user2["employee_id"]).strip().upper()

        if id1 == id2:
            raise ValueError("Cannot create a direct conversation with yourself.")

        sorted_ids = sorted([id1, id2])
        conv_id = f"DM-{sorted_ids[0]}-{sorted_ids[1]}"

        existing = db.conversations.find_one({"conversation_id": conv_id})
        if existing:
            # If the conversation was previously deleted/hidden by id1 from their view, restore id1's view
            if id1 in existing.get("deleted_for", []) or id1 in existing.get("hidden_for", []):
                db.conversations.update_one(
                    {"conversation_id": conv_id},
                    {
                        "$pull": {"deleted_for": id1, "hidden_for": id1},
                        "$set": {"status": "active", "updated_at": datetime.now(timezone.utc)}
                    }
                )
                existing = db.conversations.find_one({"conversation_id": conv_id})
            return existing

        now = datetime.now(timezone.utc)
        conv_doc = {
            "conversation_id": conv_id,
            "type": "direct",
            "title": f"{user1.get('full_name')} & {user2.get('full_name')}",
            "participant_ids": sorted_ids,
            "participant_names": {
                id1: user1.get("full_name", id1),
                id2: user2.get("full_name", id2)
            },
            "created_by": id1,
            "status": "active",
            "created_at": now,
            "updated_at": now,
            "last_message": {
                "content": "Conversation started.",
                "sender_id": id1,
                "sender_name": user1.get("full_name"),
                "timestamp": now
            }
        }
        db.conversations.insert_one(conv_doc)
        return conv_doc

    @classmethod
    def get_user_conversations(cls, user: dict, filter_type: str = None, search: str = None) -> list:
        """Lists all conversations accessible to the user with unread counts and formatted titles."""
        db = get_db()
        emp_id = user["employee_id"]

        query = {
            "participant_ids": emp_id,
            "status": {"$ne": "deleted"},
            "deleted_for": {"$ne": emp_id}
        }

        if filter_type == "hidden":
            query["hidden_for"] = emp_id
        else:
            query["hidden_for"] = {"$ne": emp_id}
            if filter_type in ("project", "direct", "team"):
                query["type"] = filter_type

        convs = list(db.conversations.find(query).sort("updated_at", -1))
        enriched = []

        for c in convs:
            cid = c["conversation_id"]

            # Compute unread count for this user
            unread_count = db.messages.count_documents({
                "conversation_id": cid,
                "sender_id": {"$ne": emp_id},
                "read_by": {"$ne": emp_id}
            })

            # Format title for direct messages
            display_title = c.get("title", "")
            if c.get("type") == "direct":
                other_ids = [pid for pid in c.get("participant_ids", []) if pid != emp_id]
                if other_ids:
                    other_id = other_ids[0]
                    other_name = c.get("participant_names", {}).get(other_id)
                    if not other_name:
                        other_u = db.users.find_one({"employee_id": other_id}, {"full_name": 1})
                        other_name = other_u.get("full_name") if other_u else other_id
                    display_title = f"{other_name} ({other_id})"

            c["display_title"] = display_title
            c["unread_count"] = unread_count
            c["is_hidden"] = emp_id in c.get("hidden_for", [])

            is_proj, proj = cls.is_project_chat(c)
            c["is_project"] = is_proj
            if proj:
                c["project_status"] = proj.get("status")

            # Strict HR Isolation: HR and Admin must have ZERO access to project chats
            if user.get("role") in (Role.HR, Role.ADMIN) and (is_proj or c.get("type") == "project"):
                continue

            # Apply search filter
            if search:
                s_lower = search.lower().strip()
                match = (
                    s_lower in display_title.lower() or
                    s_lower in c.get("project_id", "").lower() or
                    s_lower in c.get("last_message", {}).get("content", "").lower()
                )
                if not match:
                    continue

            enriched.append(c)

        return enriched

    @classmethod
    def get_conversation(cls, user: dict, conversation_id: str) -> tuple[dict | None, str | None]:
        """Retrieves and validates user access to a specific conversation."""
        db = get_db()
        conv = db.conversations.find_one({"conversation_id": conversation_id})
        if not conv:
            return None, "Conversation not found."

        emp_id = user["employee_id"]
        role = user.get("role")

        is_proj, project = cls.is_project_chat(conv)

        # Strict HR & Admin restriction: HR and Admin cannot access project chats
        if role in (Role.HR, Role.ADMIN) and (is_proj or conv.get("type") == "project"):
            return None, "Access Denied: HR and Admin personnel are restricted from project operations and project chats."

        # Check if conversation was removed from user view
        if emp_id in conv.get("deleted_for", []):
            return None, "Conversation not found or has been removed from your chat list."

        # Must be in participant_ids to access conversation (unless authorized Manager overseeing project)
        if emp_id not in conv.get("participant_ids", []):
            if is_proj and role == Role.MANAGER:
                pass
            else:
                return None, "Access Denied: You are not authorized to view this conversation."

        # Format display title
        display_title = conv.get("title", "")
        if conv.get("type") == "direct":
            other_ids = [pid for pid in conv.get("participant_ids", []) if pid != emp_id]
            if other_ids:
                other_name = conv.get("participant_names", {}).get(other_ids[0])
                display_title = f"{other_name} ({other_ids[0]})"
        conv["display_title"] = display_title
        conv["is_hidden"] = emp_id in conv.get("hidden_for", [])
        conv["is_project"] = is_proj
        if project:
            conv["project_status"] = project.get("status")

        return conv, None

    @classmethod
    def get_messages(cls, user: dict, conversation_id: str, limit: int = 150) -> tuple[list | None, str | None]:
        """Retrieves message history for a conversation, respecting unsent states, cleared history, and marks messages read."""
        conv, err = cls.get_conversation(user, conversation_id)
        if err:
            return None, err

        db = get_db()
        emp_id = user["employee_id"]

        msg_filter = {
            "conversation_id": conversation_id,
            "deleted_for": {"$ne": emp_id}
        }
        cleared_at = (conv.get("cleared_at_map") or {}).get(emp_id)
        if cleared_at:
            msg_filter["timestamp"] = {"$gt": cleared_at}

        raw_messages = list(
            db.messages.find(msg_filter)
            .sort("timestamp", 1)
            .limit(limit)
        )

        sanitized_messages = []
        for m in raw_messages:
            if m.get("is_unsent"):
                m["content"] = "This message was unsent"
                m["attachment"] = None
            elif m.get("is_deleted"):
                m["content"] = "This message was deleted."
                m["attachment"] = None
            sanitized_messages.append(m)

        # Mark all messages in this conversation as read for this user
        db.messages.update_many(
            {"conversation_id": conversation_id, "read_by": {"$ne": emp_id}},
            {"$addToSet": {"read_by": emp_id}}
        )

        return sanitized_messages, None

    @classmethod
    def send_message(cls, user: dict, conversation_id: str, content: str) -> tuple[dict | None, str | None]:
        """Sends a text message into the conversation, updates header, and dispatches notifications."""
        content = (content or "").strip()
        if not content:
            return None, "Message cannot be empty."

        conv, err = cls.get_conversation(user, conversation_id)
        if err:
            return None, err

        if conv.get("status") == "archived":
            return None, "This conversation is archived. New messages are restricted."

        emp_id = user["employee_id"]
        sender_name = user.get("full_name", emp_id)
        now = datetime.now(timezone.utc)
        db = get_db()

        msg_doc = {
            "conversation_id": conversation_id,
            "sender_id": emp_id,
            "sender_name": sender_name,
            "sender_role": user.get("role", "employee"),
            "content": content,
            "timestamp": now,
            "read_by": [emp_id],
            "is_unsent": False,
            "attachment": None
        }

        res = db.messages.insert_one(msg_doc)
        msg_doc["_id"] = res.inserted_id

        # Update last message on conversation and unhide/restore view for participants
        db.conversations.update_one(
            {"conversation_id": conversation_id},
            {
                "$set": {
                    "last_message": {
                        "content": content[:120],
                        "sender_id": emp_id,
                        "sender_name": sender_name,
                        "timestamp": now
                    },
                    "updated_at": now,
                    "status": "active"
                },
                "$pull": {
                    "deleted_for": {"$in": conv.get("participant_ids", [])},
                    "hidden_for": emp_id
                }
            }
        )

        # Notify other participants
        try:
            for pid in conv.get("participant_ids", []):
                if pid != emp_id:
                    cat = "PROJECT_CHAT" if conv.get("type") == "project" else "DIRECT_MESSAGE"
                    NotificationService.create_notification(
                        title=f"New Message from {sender_name}",
                        message=f"{sender_name}: {content[:90]}",
                        category=cat,
                        recipient_id=pid,
                        link=f"/inbox?conversation_id={conversation_id}",
                        priority="NORMAL"
                    )
        except Exception:
            pass

        return msg_doc, None

    @classmethod
    def unsend_message(cls, user: dict, message_id: str) -> tuple[dict | None, str | None]:
        """
        Allows the original sender to unsend their own message for all participants.
        Replaces message content with 'This message was unsent' and permanently redacts attachments.
        """
        db = get_db()
        try:
            msg_obj_id = ObjectId(message_id)
        except Exception:
            return None, "Invalid message identifier."

        msg = db.messages.find_one({"_id": msg_obj_id})
        if not msg:
            return None, "Message not found."

        emp_id = user["employee_id"]

        # Security check: Only original sender can unsend
        if msg.get("sender_id") != emp_id:
            logger.warning("Unauthorized unsend attempt by %s on message %s (sender: %s)", emp_id, message_id, msg.get("sender_id"))
            return None, "Access Denied: You cannot unsend a message sent by another employee."

        if msg.get("is_unsent"):
            return msg, None

        now = datetime.now(timezone.utc)
        conversation_id = msg.get("conversation_id")

        # Redact the message
        db.messages.update_one(
            {"_id": msg_obj_id},
            {
                "$set": {
                    "content": "This message was unsent",
                    "is_unsent": True,
                    "unsent_at": now,
                    "unsent_by": emp_id,
                    "attachment": None
                }
            }
        )

        # If attachment existed, mark attachment record as deleted
        if msg.get("attachment") and msg["attachment"].get("attachment_id"):
            att_id = msg["attachment"]["attachment_id"]
            db.chat_attachments.update_one(
                {"attachment_id": att_id},
                {"$set": {"is_deleted": True, "deleted_at": now, "deleted_by": emp_id}}
            )

        # If this was the last message in the conversation, update conversation header
        conv = db.conversations.find_one({"conversation_id": conversation_id})
        if conv and conv.get("last_message"):
            last_m = conv["last_message"]
            if last_m.get("sender_id") == emp_id:
                db.conversations.update_one(
                    {"conversation_id": conversation_id},
                    {
                        "$set": {
                            "last_message.content": "This message was unsent",
                            "updated_at": now
                        }
                    }
                )

        # Audit event (redacted, no sensitive content stored)
        AuditService.log_action(
            actor=user,
            action="CHAT_MESSAGE_UNSENT",
            target_type="chat_message",
            target_id=str(message_id),
            details={"conversation_id": conversation_id}
        )

        updated_msg = db.messages.find_one({"_id": msg_obj_id})
        return updated_msg, None

    @classmethod
    def delete_chat_message(cls, user: dict, message_id: str) -> tuple[dict | None, str | None]:
        """
        Deletes an individual chat message with strict role-based controls:
        - In direct (1-on-1) chats: Any sender or conversation participant can delete/remove their messages.
        - In project chats or company announcements: ONLY higher officials
          (Admin, HR, Manager, Team Lead) can delete messages. Regular employees are denied.
        """
        db = get_db()
        try:
            msg_obj_id = ObjectId(message_id)
        except Exception:
            return None, "Invalid message identifier."

        msg = db.messages.find_one({"_id": msg_obj_id})
        if not msg:
            return None, "Message not found."

        emp_id = user["employee_id"]
        role = user.get("role")
        conv_id = msg.get("conversation_id", "")
        conv = db.conversations.find_one({"conversation_id": conv_id})

        is_proj, project_doc = cls.is_project_chat(conv) if conv else (False, None)
        is_announcement = (conv and conv.get("type") in ("announcement", "broadcast")) or msg.get("is_announcement")

        # Higher official roles check: Admin, HR, HR_Manager, Manager, Organization, or Project Lead TL
        is_higher_official = role in (Role.ADMIN, Role.HR, Role.HR_MANAGER, Role.MANAGER, Role.ORGANIZATION)
        if not is_higher_official and role == Role.TEAM_LEAD:
            if project_doc and (project_doc.get("project_lead") == emp_id or project_doc.get("assigned_manager") == emp_id):
                is_higher_official = True

        if is_proj or is_announcement:
            if not is_higher_official:
                logger.warning("Employee %s denied deletion of project/announcement message %s", emp_id, message_id)
                return None, "Access Denied: Only higher officials (Management, HR, Team Leads) can delete project messages or announcements."
        else:
            # Individual/Direct Chat: Sender can delete for everyone or participants can delete for themselves
            if msg.get("sender_id") != emp_id and not is_higher_official:
                if conv and emp_id in conv.get("participant_ids", []):
                    db.messages.update_one({"_id": msg_obj_id}, {"$addToSet": {"deleted_for": emp_id}})
                    return {"_id": str(msg_obj_id), "status": "deleted_for_user"}, None
                return None, "Access Denied: You cannot delete a message from another employee."

        now = datetime.now(timezone.utc)
        # Mark message as deleted
        db.messages.update_one(
            {"_id": msg_obj_id},
            {
                "$set": {
                    "is_deleted": True,
                    "deleted_at": now,
                    "deleted_by": emp_id,
                    "content": "This message was deleted.",
                    "attachment": None
                }
            }
        )

        if msg.get("attachment") and msg["attachment"].get("attachment_id"):
            db.chat_attachments.update_one(
                {"attachment_id": msg["attachment"]["attachment_id"]},
                {"$set": {"is_deleted": True, "deleted_at": now, "deleted_by": emp_id}}
            )

        AuditService.log_action(
            actor=user,
            action="CHAT_MESSAGE_DELETED",
            target_type="chat_message",
            target_id=str(msg_obj_id),
            details={"conversation_id": conv_id, "is_project": is_proj, "deleted_by": emp_id}
        )

        return {"_id": str(msg_obj_id), "status": "deleted"}, None

    @classmethod
    def save_attachment(
        cls,
        user: dict,
        conversation_id: str,
        file_obj,
        caption: str = ""
    ) -> tuple[dict | None, str | None]:
        """
        Securely validates, stores, and attaches a document or image to the conversation.
        Enforces strict extension whitelisting, magic byte validation, and private directory storage.
        """
        conv, err = cls.get_conversation(user, conversation_id)
        if err:
            return None, err

        if conv.get("status") == "archived":
            return None, "Cannot attach files to an archived conversation."

        if not file_obj or not file_obj.filename:
            return None, "No file provided."

        filename = secure_filename(file_obj.filename)
        if not filename:
            return None, "Invalid file name."

        _, ext = os.path.splitext(filename)
        ext = ext.lower()

        # Security: Extension validation
        if ext in DANGEROUS_EXTENSIONS or ext not in ALLOWED_EXTENSIONS:
            logger.warning("Rejected upload with forbidden file extension: %s", ext)
            return None, f"File type '{ext}' is not permitted for security reasons."

        # Read content to check file size and magic bytes
        file_content = file_obj.read()
        file_size = len(file_content)

        if file_size == 0:
            return None, "Uploaded file is empty."

        if file_size > MAX_ATTACHMENT_SIZE_BYTES:
            return None, f"File size exceeds maximum allowed limit of {MAX_ATTACHMENT_SIZE_BYTES // (1024 * 1024)} MB."

        # Magic bytes check for executable headers disguised as documents
        if file_content.startswith(b"MZ") or file_content.startswith(b"\x7fELF"):
            logger.warning("Executable binary magic header detected in upload: %s", filename)
            return None, "Security violation: Executable binaries cannot be uploaded."

        # Determine safe storage path outside public static directory
        base_dir = get_chat_attachments_base_dir() / conversation_id
        os.makedirs(str(base_dir), exist_ok=True)

        attachment_id = str(uuid.uuid4())
        stored_filename = f"{attachment_id}_{filename}"
        full_dest_path = (base_dir / stored_filename).resolve()

        # Path traversal guard
        if not str(full_dest_path).startswith(str(base_dir.resolve())):
            return None, "Invalid destination path detected."

        # Write file to disk
        try:
            with open(full_dest_path, "wb") as f:
                f.write(file_content)
        except Exception as e:
            logger.error("Failed to write chat attachment to disk: %s", e)
            return None, "Server error writing attachment to storage."

        now = datetime.now(timezone.utc)
        emp_id = user["employee_id"]
        sender_name = user.get("full_name", emp_id)
        db = get_db()

        # Store attachment metadata record
        att_doc = {
            "attachment_id": attachment_id,
            "conversation_id": conversation_id,
            "original_filename": filename,
            "stored_filename": stored_filename,
            "file_path": str(full_dest_path),
            "file_size": file_size,
            "mime_type": file_obj.mimetype or "application/octet-stream",
            "uploaded_by": emp_id,
            "uploaded_at": now,
            "is_deleted": False
        }
        db.chat_attachments.insert_one(att_doc)

        # Message doc
        msg_content = caption.strip() if caption else f"Attached: {filename}"
        msg_doc = {
            "conversation_id": conversation_id,
            "sender_id": emp_id,
            "sender_name": sender_name,
            "sender_role": user.get("role", "employee"),
            "content": msg_content,
            "timestamp": now,
            "read_by": [emp_id],
            "is_unsent": False,
            "attachment": {
                "attachment_id": attachment_id,
                "filename": filename,
                "file_size": file_size,
                "mime_type": file_obj.mimetype or "application/octet-stream",
                "download_url": f"/api/conversations/{conversation_id}/attachments/{attachment_id}/download"
            }
        }
        res = db.messages.insert_one(msg_doc)
        msg_doc["_id"] = res.inserted_id

        # Update last message on conversation and unhide/restore view for participants
        db.conversations.update_one(
            {"conversation_id": conversation_id},
            {
                "$set": {
                    "last_message": {
                        "content": f"📎 {filename}",
                        "sender_id": emp_id,
                        "sender_name": sender_name,
                        "timestamp": now
                    },
                    "updated_at": now,
                    "status": "active"
                },
                "$pull": {
                    "deleted_for": {"$in": conv.get("participant_ids", [])},
                    "hidden_for": emp_id
                }
            }
        )

        # Audit event
        AuditService.log_action(
            actor=user,
            action="CHAT_ATTACHMENT_UPLOADED",
            target_type="chat_attachment",
            target_id=attachment_id,
            details={
                "conversation_id": conversation_id,
                "filename": filename,
                "file_size": file_size
            }
        )

        return msg_doc, None

    @classmethod
    def get_attachment_for_download(
        cls,
        user: dict,
        conversation_id: str,
        attachment_id: str
    ) -> tuple[dict | None, str | None]:
        """
        Validates participant access and retrieves attachment file path for download.
        Strictly forbids unauthorized downloads across conversation boundaries.
        """
        # Participant check
        conv, err = cls.get_conversation(user, conversation_id)
        if err:
            return None, err

        db = get_db()
        att = db.chat_attachments.find_one({
            "attachment_id": attachment_id,
            "conversation_id": conversation_id,
            "is_deleted": {"$ne": True}
        })
        if not att:
            return None, "Attachment not found or has been removed."

        file_path = Path(att.get("file_path", ""))
        if not file_path.exists() or not file_path.is_file():
            return None, "Attachment file is missing on the server."

        return att, None

    @classmethod
    def delete_conversation(cls, user: dict, conversation_id: str, confirm_permanent: bool = False) -> tuple[dict | None, str | None]:
        """
        Deletes a conversation with strict authorization, role-based controls, and data safety.
        - Direct chats: Soft-deletes for the requesting user, preserving the other participant's view & history.
          If all participants delete it, marked status='deleted'.
        - Approved Project chats:
          - Employees: 403 Forbidden (must use hide).
          - Team Leads: 403 Forbidden.
          - HR: 403 Forbidden.
          - Managers:
            - Blocked if active project dependencies exist.
            - Allowed if completed/cancelled, requiring explicit confirmation.
            - Messages and audit logs are preserved for compliance retention.
        """
        db = get_db()
        conv = db.conversations.find_one({"conversation_id": conversation_id})
        if not conv:
            return None, "Conversation not found."

        emp_id = user["employee_id"]
        role = user.get("role")
        now = datetime.now(timezone.utc)

        is_proj, project = cls.is_project_chat(conv)

        # 1. HR restriction
        if role == Role.HR and is_proj:
            return None, "Access Denied: HR personnel are restricted from project operations and project chats."

        # 2. Project Group Chat Deletion
        if is_proj:
            if role == Role.EMPLOYEE:
                return None, "Access Denied: Project group chats cannot be deleted by employees. Contact your Project Manager."

            if role == Role.TEAM_LEAD:
                return None, "Access Denied: Team Leads cannot delete approved project group chats. Only authorized Managers can manage project conversation lifecycles."

            if role in (Role.MANAGER, Role.ADMIN):
                # Verify project dependencies
                if project:
                    proj_status = str(project.get("status", "")).strip().upper()
                    if proj_status in ("ACTIVE", "APPROVED", "IN_PROGRESS", "ON_HOLD"):
                        return None, f"Active project dependencies exist. Project chat cannot be deleted while project is active (Status: {proj_status}). Complete or cancel the project first."

                if not confirm_permanent:
                    return None, "Explicit confirmation required to permanently delete an approved project group chat."

                # Soft-delete the project conversation (concurrency-safe)
                db.conversations.update_one(
                    {"conversation_id": conversation_id, "status": {"$ne": "deleted"}},
                    {
                        "$set": {
                            "status": "deleted",
                            "deleted_at": now,
                            "deleted_by": emp_id,
                            "updated_at": now
                        }
                    }
                )

                # Compliance audit log
                AuditService.log_action(
                    actor=user,
                    action="PROJECT_CHAT_DELETED",
                    target_type="project_chat",
                    target_id=conversation_id,
                    details={
                        "project_id": conv.get("project_id"),
                        "project_status": project.get("status") if project else "UNKNOWN",
                        "retention_policy": "soft_deleted_audit_preserved"
                    }
                )
                return {
                    "conversation_id": conversation_id,
                    "scope": "project",
                    "status": "deleted",
                    "message": "Project group chat deleted successfully by Manager."
                }, None

            return None, "Access Denied: You are not authorized to delete project group chats."

        # 3. Direct / Personal Chat Deletion
        # User must be an actual participant in the direct conversation
        participants = conv.get("participant_ids", [])
        if emp_id not in participants:
            return None, "Access Denied: You are not authorized to delete another user's conversation."

        # Add emp_id to deleted_for, record clear timestamp
        db.conversations.update_one(
            {
                "conversation_id": conversation_id,
                "deleted_for": {"$ne": emp_id}
            },
            {
                "$addToSet": {"deleted_for": emp_id},
                "$set": {
                    f"cleared_at_map.{emp_id}": now,
                    "updated_at": now
                }
            }
        )

        # Check if all participants have now deleted this chat
        refreshed = db.conversations.find_one({"conversation_id": conversation_id})
        deleted_for_set = set(refreshed.get("deleted_for", []))
        all_deleted = set(participants).issubset(deleted_for_set)

        if all_deleted:
            db.conversations.update_one(
                {"conversation_id": conversation_id},
                {"$set": {"status": "deleted", "deleted_at": now}}
            )

        # Audit log (redacted details)
        AuditService.log_action(
            actor=user,
            action="CHAT_DIRECT_DELETED",
            target_type="chat_conversation",
            target_id=conversation_id,
            details={
                "scope": "user_view",
                "all_participants_deleted": all_deleted
            }
        )

        return {
            "conversation_id": conversation_id,
            "scope": "user_view",
            "status": "deleted",
            "all_participants_deleted": all_deleted,
            "message": "Conversation removed from your chat list. The other participant will retain their message history unless they also delete it."
        }, None

    @classmethod
    def archive_project_chat(cls, user: dict, conversation_id: str) -> tuple[dict | None, str | None]:
        """
        Authorized archival process for completed or cancelled project group chats by Managers.
        Restricts future messages while preserving all history and attachments.
        """
        db = get_db()
        conv = db.conversations.find_one({"conversation_id": conversation_id})
        if not conv:
            return None, "Conversation not found."

        emp_id = user["employee_id"]
        role = user.get("role")
        now = datetime.now(timezone.utc)

        is_proj, project = cls.is_project_chat(conv)
        if not is_proj:
            return None, "Archival control is designed for project group chats."

        if role == Role.HR:
            return None, "Access Denied: HR personnel are restricted from project operations and project chats."

        if role not in (Role.MANAGER, Role.ADMIN):
            return None, "Access Denied: Only authorized Managers can archive project group chats."

        if project:
            proj_status = str(project.get("status", "")).strip().upper()
            if proj_status in ("ACTIVE", "APPROVED", "IN_PROGRESS", "ON_HOLD"):
                return None, f"Active project dependencies exist. Project chat cannot be archived while project is active (Status: {proj_status}). Complete or cancel the project first."

        # Mark conversation as archived (concurrency-safe)
        db.conversations.update_one(
            {"conversation_id": conversation_id, "status": {"$ne": "archived"}},
            {
                "$set": {
                    "status": "archived",
                    "archived_at": now,
                    "archived_by": emp_id,
                    "updated_at": now
                }
            }
        )

        AuditService.log_action(
            actor=user,
            action="PROJECT_CHAT_ARCHIVED",
            target_type="project_chat",
            target_id=conversation_id,
            details={
                "project_id": conv.get("project_id"),
                "project_status": project.get("status") if project else "UNKNOWN"
            }
        )

        return {
            "conversation_id": conversation_id,
            "status": "archived",
            "message": "Project group chat archived successfully. Collaboration is now in read-only mode."
        }, None

    @classmethod
    def hide_conversation(cls, user: dict, conversation_id: str) -> tuple[dict | None, str | None]:
        """
        Allows an employee or team lead to hide or archive a protected project chat
        from their personal chat list without affecting other members or project records.
        """
        db = get_db()
        conv = db.conversations.find_one({"conversation_id": conversation_id})
        if not conv:
            return None, "Conversation not found."

        emp_id = user["employee_id"]
        role = user.get("role")

        is_proj, _ = cls.is_project_chat(conv)
        if role == Role.HR and is_proj:
            return None, "Access Denied: HR personnel are restricted from project operations and project chats."

        if emp_id not in conv.get("participant_ids", []):
            return None, "Access Denied: You are not authorized to hide this conversation."

        db.conversations.update_one(
            {"conversation_id": conversation_id},
            {"$addToSet": {"hidden_for": emp_id}}
        )

        AuditService.log_action(
            actor=user,
            action="CHAT_CONVERSATION_HIDDEN",
            target_type="chat_conversation",
            target_id=conversation_id,
            details={"scope": "personal_view"}
        )

        return {
            "conversation_id": conversation_id,
            "hidden": True,
            "message": "Conversation hidden from your personal list."
        }, None

    @classmethod
    def unhide_conversation(cls, user: dict, conversation_id: str) -> tuple[dict | None, str | None]:
        """Restores a hidden conversation back into the user's personal chat list."""
        db = get_db()
        conv = db.conversations.find_one({"conversation_id": conversation_id})
        if not conv:
            return None, "Conversation not found."

        emp_id = user["employee_id"]
        role = user.get("role")

        is_proj, _ = cls.is_project_chat(conv)
        if role == Role.HR and is_proj:
            return None, "Access Denied: HR personnel are restricted from project operations and project chats."

        if emp_id not in conv.get("participant_ids", []):
            return None, "Access Denied: You are not authorized to unhide this conversation."

        db.conversations.update_one(
            {"conversation_id": conversation_id},
            {"$pull": {"hidden_for": emp_id}}
        )

        return {
            "conversation_id": conversation_id,
            "hidden": False,
            "message": "Conversation restored to your personal list."
        }, None
