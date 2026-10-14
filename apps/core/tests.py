from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Role, User
from apps.attendance.models import (
    AttendanceCorrectionRequest,
    AttendanceRecord,
    CorrectionStatus,
)
from apps.audit.models import AuditLog
from apps.employees.models import Employee
from apps.leave.models import LeaveRequest, LeaveStatus, LeaveType
from apps.notifications.models import CalendarEvent, Notification
from apps.projects.models import (
    Project,
    ProjectAssignment,
    WorkLog,
    WorkLogStatus,
)


def make_hr(username="hr"):
    return User.objects.create_user(
        username=username, password="pw12345!", role=Role.HR
    )


def make_employee(username="emp", employee_id="E001"):
    user = User.objects.create_user(
        username=username, password="pw12345!", role=Role.EMPLOYEE
    )
    employee = Employee.objects.create(
        user=user, employee_id=employee_id, full_name="Test Employee"
    )
    return user, employee


class DashboardTests(TestCase):
    def setUp(self):
        self.hr = make_hr()
        self.emp_user, self.employee = make_employee()

    def test_hr_dashboard_shows_live_counts(self):
        Project.objects.create(name="Alpha", created_by=self.hr)
        leave_type = LeaveType.objects.create(name="Casual")
        LeaveRequest.objects.create(
            employee=self.employee,
            leave_type=leave_type,
            start_date=timezone.localdate(),
            end_date=timezone.localdate(),
            status=LeaveStatus.PENDING,
        )
        AttendanceCorrectionRequest.objects.create(
            employee=self.employee,
            date=timezone.localdate(),
            reason="forgot",
            status=CorrectionStatus.PENDING,
        )
        project = Project.objects.create(name="Beta", created_by=self.hr)
        WorkLog.objects.create(
            employee=self.employee,
            project=project,
            date=timezone.localdate(),
            hours="2",
            description="work",
            status=WorkLogStatus.SUBMITTED,
        )
        self.client.force_login(self.hr)
        response = self.client.get(reverse("core:home"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["employee_count"], 1)
        self.assertEqual(response.context["pending_leave"], 1)
        self.assertEqual(response.context["pending_corrections"], 1)
        self.assertEqual(response.context["pending_worklogs"], 1)

    def test_employee_dashboard_reflects_own_data(self):
        Notification.objects.create(recipient=self.emp_user, title="Hi")
        AttendanceRecord.objects.create(
            employee=self.employee,
            date=timezone.localdate(),
            check_in="09:00",
        )
        self.client.force_login(self.emp_user)
        response = self.client.get(reverse("core:home"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["unread_notifications"], 1)
        self.assertIsNotNone(response.context["today_record"])

    def test_employee_without_profile_still_renders(self):
        user = User.objects.create_user(
            username="ghost", password="pw12345!", role=Role.EMPLOYEE
        )
        self.client.force_login(user)
        response = self.client.get(reverse("core:home"))
        self.assertEqual(response.status_code, 200)

    def test_login_required(self):
        response = self.client.get(reverse("core:home"))
        self.assertEqual(response.status_code, 302)


class WorkLogNotificationTests(TestCase):
    def setUp(self):
        self.hr = make_hr()
        self.emp_user, self.employee = make_employee()

    def test_review_creates_notification(self):
        project = Project.objects.create(name="Alpha", created_by=self.hr)
        log = WorkLog.objects.create(
            employee=self.employee,
            project=project,
            date=timezone.localdate(),
            hours=5,
            description="Did work",
            status=WorkLogStatus.SUBMITTED,
        )
        self.client.force_login(self.hr)
        response = self.client.post(
            reverse("projects:worklog_review_decision", args=[log.pk])
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            Notification.objects.filter(
                recipient=self.emp_user, title__icontains="reviewed"
            ).exists()
        )
