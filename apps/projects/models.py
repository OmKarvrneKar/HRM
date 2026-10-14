"""Projects, teams and work-log models.

Work-log date policy
--------------------
A work log's ``date`` must not be in the future (calendar date in
``settings.TIME_ZONE``, via ``timezone.localdate()``) and must not predate the
project's ``start_date`` when a project is set. Hours are limited to a sensible
daily range (``0 <= hours <= MAX_DAILY_HOURS``). At most one log may exist per
employee per project per date; reviewed logs are locked from employee edits.
"""
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from apps.employees.models import Employee

MAX_DAILY_HOURS = 24


class ProjectStatus(models.TextChoices):
    PLANNED = "PLANNED", "Planned"
    ACTIVE = "ACTIVE", "Active"
    ON_HOLD = "ON_HOLD", "On Hold"
    COMPLETED = "COMPLETED", "Completed"


class Project(models.Model):
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=20, choices=ProjectStatus.choices, default=ProjectStatus.PLANNED
    )
    is_archived = models.BooleanField(
        default=False,
        help_text="Archived projects are retained for history but hidden by default.",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_projects",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def clean(self):
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValidationError(
                {"end_date": "End date cannot be before the start date."}
            )


class ProjectAssignment(models.Model):
    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name="assignments"
    )
    employee = models.ForeignKey(
        Employee, on_delete=models.CASCADE, related_name="project_assignments"
    )
    role = models.CharField(max_length=100, blank=True)
    assigned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("project", "employee")
        ordering = ["employee__employee_id"]

    def __str__(self):
        return f"{self.employee.full_name} @ {self.project.name}"


class TeamGroup(models.Model):
    """A cross-functional group of employees (distinct from a project team)."""

    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_groups",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class GroupMembership(models.Model):
    group = models.ForeignKey(
        TeamGroup, on_delete=models.CASCADE, related_name="memberships"
    )
    employee = models.ForeignKey(
        Employee, on_delete=models.CASCADE, related_name="group_memberships"
    )
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("group", "employee")
        ordering = ["employee__employee_id"]

    def __str__(self):
        return f"{self.employee.full_name} in {self.group.name}"


class WorkLogStatus(models.TextChoices):
    SUBMITTED = "SUBMITTED", "Submitted"
    REVIEWED = "REVIEWED", "Reviewed"


class WorkLog(models.Model):
    employee = models.ForeignKey(
        Employee, on_delete=models.CASCADE, related_name="work_logs"
    )
    project = models.ForeignKey(
        Project,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="work_logs",
    )
    date = models.DateField()
    hours = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    description = models.TextField()
    status = models.CharField(
        max_length=20, choices=WorkLogStatus.choices, default=WorkLogStatus.SUBMITTED
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_work_logs",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["employee", "project", "date"],
                name="unique_worklog_per_project_day",
            ),
            models.CheckConstraint(
                condition=models.Q(hours__gte=0) & models.Q(hours__lte=MAX_DAILY_HOURS),
                name="worklog_hours_range",
            ),
        ]

    def __str__(self):
        return f"{self.employee.employee_id} {self.date} ({self.hours}h)"

    @property
    def is_locked(self):
        """Reviewed logs are locked from employee edits."""
        return self.status == WorkLogStatus.REVIEWED

    def clean(self):
        if self.hours is not None and (
            self.hours < 0 or self.hours > MAX_DAILY_HOURS
        ):
            raise ValidationError(
                {"hours": f"Hours must be between 0 and {MAX_DAILY_HOURS}."}
            )
        if self.date:
            if self.date > timezone.localdate():
                raise ValidationError(
                    {"date": "Work date cannot be in the future."}
                )
            if (
                self.project
                and self.project.start_date
                and self.date < self.project.start_date
            ):
                raise ValidationError(
                    {"date": "Work date cannot be before the project start date."}
                )
        if self.employee_id and self.date is not None:
            duplicates = WorkLog.objects.filter(
                employee_id=self.employee_id, date=self.date, project=self.project
            )
            if self.pk:
                duplicates = duplicates.exclude(pk=self.pk)
            if duplicates.exists():
                raise ValidationError(
                    "A work log for this project and date already exists."
                )
