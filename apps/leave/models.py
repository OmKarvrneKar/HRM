"""Leave models.

Leave status is an independent workflow state (pending/approved/rejected). It is
deliberately *not* linked to ``Employee`` employment status or to
``AttendanceRecord``; approving leave never writes attendance rows.
"""
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from apps.employees.models import Employee


class LeaveType(models.Model):
    """HR-configurable category of leave (e.g. Casual, Sick)."""

    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class LeaveStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    APPROVED = "APPROVED", "Approved"
    REJECTED = "REJECTED", "Rejected"


class LeaveRequest(models.Model):
    """A leave request. Status is independent of employment/attendance state."""

    employee = models.ForeignKey(
        Employee, on_delete=models.CASCADE, related_name="leave_requests"
    )
    leave_type = models.ForeignKey(
        LeaveType, on_delete=models.PROTECT, related_name="requests"
    )
    start_date = models.DateField()
    end_date = models.DateField()
    reason = models.TextField()
    status = models.CharField(
        max_length=20, choices=LeaveStatus.choices, default=LeaveStatus.PENDING
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_leave_requests",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    decision_note = models.TextField(
        blank=True,
        help_text="Optional reason recorded by HR when approving or rejecting.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(end_date__gte=models.F("start_date")),
                name="leave_end_date_gte_start_date",
            ),
        ]

    def __str__(self):
        return f"{self.employee.employee_id} {self.start_date}–{self.end_date} ({self.status})"

    def clean(self):
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValidationError(
                {"end_date": "End date cannot be before the start date."}
            )

    @classmethod
    def overlapping(cls, employee, start_date, end_date, exclude_pk=None):
        """Return PENDING/APPROVED requests for `employee` overlapping the range.

        Rejected requests are deliberately excluded so they stay in history
        without blocking new submissions.
        """
        qs = cls.objects.filter(
            employee=employee,
            status__in=[LeaveStatus.PENDING, LeaveStatus.APPROVED],
            start_date__lte=end_date,
            end_date__gte=start_date,
        )
        if exclude_pk is not None:
            qs = qs.exclude(pk=exclude_pk)
        return qs

    @property
    def days(self):
        return (self.end_date - self.start_date).days + 1
