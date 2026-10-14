import os
from uuid import uuid4

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.text import slugify

from apps.employees.models import Employee
from apps.projects.models import TeamGroup

from .storage import private_storage
from .validators import validate_document_file


def hr_document_upload_to(instance, filename):
    """Return a non-guessable storage path, keeping only a safe extension."""
    extension = os.path.splitext(filename)[1].lower()
    return f"hr_documents/{uuid4().hex}{extension}"


class DocumentType(models.TextChoices):
    CONTRACT = "CONTRACT", "Employment contract"
    ID_PROOF = "IDENTITY", "Identity document"
    CERTIFICATE = "CERTIFICATE", "Certificate"
    POLICY = "POLICY", "Policy"
    OTHER = "OTHER", "Other"


class DocumentVisibility(models.TextChoices):
    ALL_EMPLOYEES = "ALL_EMPLOYEES", "All employees"
    SINGLE_EMPLOYEE = "SINGLE_EMPLOYEE", "Specific employee"
    HR_ONLY = "HR_ONLY", "HR only"


class HRDocument(models.Model):
    title = models.CharField(max_length=200)
    document_type = models.CharField(
        max_length=30, choices=DocumentType.choices, default="OTHER"
    )
    employee = models.ForeignKey(
        "employees.Employee",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="hr_documents",
        help_text="Set when the document belongs to a single employee.",
    )
    file = models.FileField(
        upload_to=hr_document_upload_to,
        storage=private_storage,
        validators=[validate_document_file],
        help_text="Allowed: PDF, PNG, JPG/JPEG. Max 10 MB.",
    )
    visibility = models.CharField(
        max_length=20,
        choices=DocumentVisibility.choices,
        default=DocumentVisibility.HR_ONLY,
    )
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="uploaded_documents",
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-uploaded_at"]

    def __str__(self):
        return self.title

    @property
    def download_name(self):
        """A safe, human-friendly download filename (no filesystem path)."""
        extension = os.path.splitext(self.file.name or "")[1].lower()
        base = slugify(self.title) or "document"
        return f"{base}{extension}"

    def is_visible_to(self, user):
        """Server-side visibility check used by download and list views."""
        if not getattr(user, "is_authenticated", False):
            return False
        if getattr(user, "is_hr", False):
            return True
        if self.visibility == DocumentVisibility.ALL_EMPLOYEES:
            return True
        if (
            self.visibility == DocumentVisibility.SINGLE_EMPLOYEE
            and self.employee is not None
            and self.employee.user_id == user.id
        ):
            return True
        return False

    def is_downloadable_by(self, user):
        """Visible directly, or attached to a communication visible to `user`.

        This keeps attachment access consistent: an employee who may read a
        legal communication may also download its attachment, even when the
        underlying document is otherwise HR-only.
        """
        if self.is_visible_to(user):
            return True
        if not getattr(user, "is_authenticated", False):
            return False
        return any(
            communication.is_visible_to(user)
            for communication in self.communications.filter(is_active=True)
        )


class CommunicationAudience(models.TextChoices):
    ALL_EMPLOYEES = "ALL_EMPLOYEES", "All employees"
    SINGLE_EMPLOYEE = "SINGLE_EMPLOYEE", "Specific employee"
    GROUP = "GROUP", "Group"
    HR_ONLY = "HR_ONLY", "HR only"


class LegalCommunication(models.Model):
    """Authorized legal / official communication with related documents."""

    title = models.CharField(max_length=200)
    body = models.TextField()
    audience = models.CharField(
        max_length=20,
        choices=CommunicationAudience.choices,
        default=CommunicationAudience.HR_ONLY,
    )
    employee = models.ForeignKey(
        "employees.Employee",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="legal_communications",
    )
    group = models.ForeignKey(
        "projects.TeamGroup",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="legal_communications",
    )
    attachment = models.ForeignKey(
        HRDocument,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="communications",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_communications",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title

    def clean(self):
        if (
            self.audience == CommunicationAudience.SINGLE_EMPLOYEE
            and self.employee_id is None
        ):
            raise ValidationError(
                {"employee": "Choose an employee for this audience."}
            )
        if self.audience == CommunicationAudience.GROUP and self.group_id is None:
            raise ValidationError({"group": "Choose a group for this audience."})

    def is_visible_to(self, user):
        if not getattr(user, "is_authenticated", False):
            return False
        if getattr(user, "is_hr", False):
            return True
        if not self.is_active:
            return False
        if self.audience == CommunicationAudience.ALL_EMPLOYEES:
            return True
        employee = getattr(user, "employee", None)
        if employee is None:
            return False
        if (
            self.audience == CommunicationAudience.SINGLE_EMPLOYEE
            and self.employee_id == employee.id
        ):
            return True
        if (
            self.audience == CommunicationAudience.GROUP
            and self.group_id is not None
            and self.group.memberships.filter(employee=employee).exists()
        ):
            return True
        return False
