from datetime import date

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import Role, User
from apps.employees.models import Employee
from apps.notifications.models import Notification

from .models import LeaveRequest, LeaveStatus, LeaveType


def make_hr(username="hr"):
    return User.objects.create_user(
        username=username, password="pw12345!", role=Role.HR
    )


def make_employee(username="emp", employee_id="E001"):
    user = User.objects.create_user(
        username=username, password="pw12345!", role=Role.EMPLOYEE
    )
    return Employee.objects.create(
        user=user, employee_id=employee_id, full_name="Test Employee"
    )


class LeaveFlowTests(TestCase):
    def setUp(self):
        self.hr = make_hr()
        self.employee = make_employee()
        self.leave_type = LeaveType.objects.create(name="Casual")

    def test_employee_applies_for_leave(self):
        self.client.force_login(self.employee.user)
        response = self.client.post(
            reverse("leave:create"),
            {
                "leave_type": self.leave_type.pk,
                "start_date": "2024-07-01",
                "end_date": "2024-07-03",
                "reason": "Family",
            },
        )
        self.assertEqual(response.status_code, 302)
        request_obj = LeaveRequest.objects.get(employee=self.employee)
        self.assertEqual(request_obj.status, LeaveStatus.PENDING)
        self.assertEqual(request_obj.days, 3)

    def test_hr_decision_notifies_employee(self):
        leave_request = LeaveRequest.objects.create(
            employee=self.employee,
            leave_type=self.leave_type,
            start_date=date(2024, 7, 1),
            end_date=date(2024, 7, 3),
            reason="Family",
        )
        self.client.force_login(self.hr)
        response = self.client.post(
            reverse("leave:decision", args=[leave_request.pk]),
            {"decision": "APPROVED", "note": "Approved"},
        )
        self.assertEqual(response.status_code, 302)
        leave_request.refresh_from_db()
        self.assertEqual(leave_request.status, LeaveStatus.APPROVED)
        self.assertTrue(
            Notification.objects.filter(recipient=self.employee.user).exists()
        )

    def test_employee_cannot_access_hr_leave_list(self):
        self.client.force_login(self.employee.user)
        response = self.client.get(reverse("leave:requests"))
        self.assertEqual(response.status_code, 403)
