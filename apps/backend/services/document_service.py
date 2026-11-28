import os
import logging
from werkzeug.utils import secure_filename
from database.connection import get_db
from permissions.rbac import Role, normalize_role
from services.audit_service import AuditService
from utils.serializers import serialize_doc, serialize_docs
from utils.timezone import now_utc
from config import Config

logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {"pdf", "doc", "docx", "txt", "xlsx", "xls", "png", "jpg", "jpeg"}


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


class DocumentService:
    """
    Company Policies and Documents Service for AISamrat HRMS:
    - HR & Admin upload company policies, guidelines, and handbooks.
    - All authenticated staff can browse and download authorized company policies.
    """

    @classmethod
    def upload_document(cls, uploader: dict, file_obj, form_data: dict) -> tuple[dict | None, str | None]:
        db = get_db()
        role = normalize_role(uploader.get("role"))

        if role not in (Role.HR, Role.ADMIN):
            return None, "Unauthorized: Only HR and Administrators can upload company policies and documents."

        if not file_obj or file_obj.filename == "":
            return None, "No file selected for upload."

        if not allowed_file(file_obj.filename):
            return None, f"Unsupported file type. Allowed formats: {', '.join(ALLOWED_EXTENSIONS)}"

        title = (form_data.get("title") or file_obj.filename).strip()
        category = (form_data.get("category") or "Company Policy").strip()
        description = (form_data.get("description") or "").strip()

        # Target storage directory in user data directory
        docs_dir = os.path.join(str(Config.DATA_DIR), "uploads", "documents")
        os.makedirs(docs_dir, exist_ok=True)

        orig_filename = secure_filename(file_obj.filename)
        count = db.documents.count_documents({})
        doc_id = f"DOC-{1001 + count}"
        saved_filename = f"{doc_id}_{orig_filename}"
        target_path = os.path.join(docs_dir, saved_filename)

        file_obj.save(target_path)
        file_size = os.path.getsize(target_path)

        doc = {
            "document_id": doc_id,
            "title": title,
            "category": category,
            "description": description,
            "original_filename": orig_filename,
            "saved_filename": saved_filename,
            "file_path": target_path,
            "file_size": file_size,
            "mime_type": getattr(file_obj, "content_type", "application/octet-stream"),
            "uploaded_by_id": uploader.get("employee_id"),
            "uploaded_by_name": uploader.get("full_name"),
            "created_at": now_utc(),
            "updated_at": now_utc()
        }

        db.documents.insert_one(doc)
        logger.info("Uploaded company document %s (%s) by %s", doc_id, title, uploader.get("employee_id"))

        # Audit
        try:
            AuditService.log_action(
                actor=uploader,
                action="UPLOAD_DOCUMENT",
                target_type="document",
                target_id=doc_id,
                details={"title": title, "category": category, "file_name": orig_filename}
            )
        except Exception as e:
            logger.warning("Failed to log document upload audit: %s", e)

        return serialize_doc(doc), None

    @classmethod
    def list_documents(cls, category: str = None) -> list[dict]:
        db = get_db()
        query = {}
        if category and category.upper() != "ALL":
            query["category"] = category
        docs = list(db.documents.find(query).sort("created_at", -1))
        return serialize_docs(docs)

    @classmethod
    def get_document_for_download(cls, doc_id: str) -> tuple[dict | None, str | None]:
        db = get_db()
        doc = db.documents.find_one({"document_id": doc_id})
        if not doc:
            return None, f"Document '{doc_id}' not found."

        file_path = doc.get("file_path")
        if not file_path or not os.path.exists(file_path):
            return None, "Document file not found on disk."

        return doc, None

    @classmethod
    def delete_document(cls, user: dict, doc_id: str) -> tuple[bool, str | None]:
        db = get_db()
        role = normalize_role(user.get("role"))
        if role not in (Role.HR, Role.ADMIN):
            return False, "Unauthorized: Only HR and Admin can delete company documents."

        doc = db.documents.find_one({"document_id": doc_id})
        if not doc:
            return False, f"Document '{doc_id}' not found."

        file_path = doc.get("file_path")
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception as e:
                logger.warning("Failed to remove document file: %s", e)

        db.documents.delete_one({"document_id": doc_id})
        logger.info("Deleted document %s by %s", doc_id, user.get("employee_id"))
        return True, None
