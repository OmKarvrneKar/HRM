from django.conf import settings
from django.db import models

from apps.employees.models import Employee
from apps.projects.models import TeamGroup

from .storage import private_storage


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
    file = models.FileField(upload_to="hr_documents/%Y/%m/", storage=private_storage)
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
