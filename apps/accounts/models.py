from django.contrib.auth.models import AbstractUser
from django.db import models


class Role(models.TextChoices):
    """The two business roles in the system. Do not add more."""

    HR = "HR", "HR"
    EMPLOYEE = "EMPLOYEE", "Employee"


class User(AbstractUser):
    """Custom user that carries the business role.

    Django's superuser/staff flags are only used to access the internal admin
    site; the application's business roles remain exactly HR and Employee.
    """

    role = models.CharField(
        max_length=20, choices=Role.choices, default=Role.EMPLOYEE
    )
    must_change_password = models.BooleanField(
        default=False,
        help_text="Force the user to choose a new password on next login.",
    )

    @property
    def is_hr(self):
        return self.role == Role.HR

    @property
    def is_employee(self):
        return self.role == Role.EMPLOYEE

    def __str__(self):
        return f"{self.get_full_name() or self.username} ({self.get_role_display()})"
