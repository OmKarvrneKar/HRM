"""Attendance models.

Attendance date policy
----------------------
The "attendance date" is the calendar date in the configured project timezone
(``settings.TIME_ZONE = "Asia/Kolkata"``), taken with
``django.utils.timezone.localdate()``. Every self-service action (check-in,
check-out) operates on *today* in that timezone, never the raw UTC date. HR may
record or correct any explicit date. One row is allowed per employee per date.
"""
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from apps.employees.models import Employee


class AttendanceStatus(models.TextChoices):
    PRESENT = "PRESENT", "Present"
    ABSENT = "ABSENT", "Absent"
    LATE = "LATE", "Late"
    HALF_DAY = "HALF_DAY", "Half Day"
    ON_LEAVE = "ON_LEAVE", "On Leave"


class AttendanceSource(models.TextChoices):
    SELF = "SELF", "Self check-in"
    HR = "HR", "HR entry"


class AttendanceRecord(models.Model):
    """One attendance row per employee per day."""

    employee = models.ForeignKey(
        Employee, on_delete=models.CASCADE, related_name="attendance_records"
    )
    date = models.DateField()
    check_in = models.TimeField(null=True, blank=True)
    check_out = models.TimeField(null=True, blank=True)
    status = models.CharField(
        max_length=20, choices=AttendanceStatus.choices, default=AttendanceStatus.PRESENT
    )
    source = models.CharField(
        max_length=10, choices=AttendanceSource.choices, default=AttendanceSource.SELF
    )
    note = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_attendance_records",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("employee", "date")
        ordering = ["-date", "employee__employee_id"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(check_out__isnull=True)
                    | models.Q(check_in__isnull=True)
                    | models.Q(check_out__gte=models.F("check_in"))
                ),
                name="attendance_checkout_gte_checkin",
            ),
        ]

    def __str__(self):
        return f"{self.employee.employee_id} @ {self.date} ({self.get_status_display()})"

    def clean(self):
        if self.check_out and not self.check_in:
            raise ValidationError(
                {"check_out": "A check-out time requires a check-in time."}
            )
        if self.check_in and self.check_out and self.check_out < self.check_in:
            raise ValidationError(
                {"check_out": "Check-out must be at or after check-in."}
            )

    @property
    def is_complete(self):
        return self.check_in is not None and self.check_out is not None


class CorrectionStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    APPROVED = "APPROVED", "Approved"
    REJECTED = "REJECTED", "Rejected"


class AttendanceCorrectionRequest(models.Model):
    """Employee asks HR to fix an attendance record."""

    employee = models.ForeignKey(
        Employee, on_delete=models.CASCADE, related_name="attendance_corrections"
    )
    attendance = models.ForeignKey(
        AttendanceRecord,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="corrections",
    )
    date = models.DateField()
    requested_check_in = models.TimeField(null=True, blank=True)
    requested_check_out = models.TimeField(null=True, blank=True)
    reason = models.TextField()
    status = models.CharField(
        max_length=20, choices=CorrectionStatus.choices, default=CorrectionStatus.PENDING
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_corrections",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    decision_note = models.TextField(
        blank=True,
        help_text="Reason recorded by HR when approving or rejecting the request.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Correction {self.employee.employee_id} {self.date} ({self.status})"

    def clean(self):
        if not self.requested_check_in and not self.requested_check_out:
            raise ValidationError(
                "Provide at least one requested time (check-in or check-out)."
            )
        if (
            self.requested_check_in
            and self.requested_check_out
            and self.requested_check_out < self.requested_check_in
        ):
            raise ValidationError(
                {
                    "requested_check_out": (
                        "Requested check-out must be at or after the requested "
                        "check-in."
                    )
                }
            )
