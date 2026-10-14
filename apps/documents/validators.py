"""Upload validation for private HR documents.

The browser-supplied filename and content type are never trusted. We validate
by file extension, enforce a maximum size, and confirm a lightweight magic-byte
signature for the declared type. Stored filenames are randomised separately
(see ``models.hr_document_upload_to``) so uploads are not guessable.
"""
import os

from django.core.exceptions import ValidationError

ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg"}

# 10 MB is a deliberately modest cap for HR paperwork.
MAX_DOCUMENT_SIZE = 10 * 1024 * 1024

_MAGIC_PREFIXES = {
    ".pdf": (b"%PDF",),
    ".png": (b"\x89PNG",),
    ".jpg": (b"\xff\xd8\xff",),
    ".jpeg": (b"\xff\xd8\xff",),
}


def _read_header(file_obj, length=8):
    try:
        file_obj.seek(0)
        header = file_obj.read(length)
        file_obj.seek(0)
        return header or b""
    except Exception:
        return b""


def validate_document_file(file_obj):
    """Validate extension, size and magic bytes of an uploaded document."""
    name = getattr(file_obj, "name", "") or ""
    extension = os.path.splitext(name)[1].lower()

    if extension not in ALLOWED_EXTENSIONS:
        allowed = ", ".join(sorted(ALLOWED_EXTENSIONS))
        raise ValidationError(f"Unsupported file type. Allowed types: {allowed}.")

    size = getattr(file_obj, "size", 0) or 0
    if size > MAX_DOCUMENT_SIZE:
        raise ValidationError(
            f"File too large. Maximum size is {MAX_DOCUMENT_SIZE // (1024 * 1024)} MB."
        )

    header = _read_header(file_obj)
    if header:
        prefixes = _MAGIC_PREFIXES.get(extension, ())
        if prefixes and not any(header.startswith(p) for p in prefixes):
            raise ValidationError(
                "The file contents do not match its extension."
            )
