from datetime import date

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import Role, User
from apps.employees.models import Employee

from .models import (
    AttendanceCorrectionRequest,
    AttendanceRecord,
    AttendanceSource,
    AttendanceStatus,
    CorrectionStatus,
)


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


class AttendanceCheckInOutTests(TestCase):
    def setUp(self):
        self.employee = make_employee()

    def test_check_in_creates_record(self):
        self.client.force_login(self.employee.user)
        response = self.client.post(reverse("attendance:check_in"))
        self.assertEqual(response.status_code, 302)
        record = AttendanceRecord.objects.get(
            employee=self.employee, date=date.today()
        )
        self.assertIsNotNone(record.check_in)
        self.assertEqual(record.source, AttendanceSource.SELF)

    def test_check_out_requires_check_in(self):
        self.client.force_login(self.employee.user)
        self.client.post(reverse("attendance:check_out"))
        self.assertFalse(
            AttendanceRecord.objects.filter(employee=self.employee).exists()
        )

    def test_employee_cannot_access_hr_list(self):
        self.client.force_login(self.employee.user)
        response = self.client.get(reverse("attendance:list"))
        self.assertEqual(response.status_code, 403)


class AttendanceHRTests(TestCase):
    def setUp(self):
        self.hr = make_hr()
        self.employee = make_employee()

    def test_hr_manual_entry(self):
        self.client.force_login(self.hr)
        response = self.client.post(
            reverse("attendance:create"),
            {
                "employee": self.employee.pk,
                "date": "2024-05-01",
                "check_in": "09:00",
                "check_out": "18:00",
                "status": AttendanceStatus.PRESENT,
                "note": "Manual",
            },
        )
        self.assertEqual(response.status_code, 302)
        record = AttendanceRecord.objects.get(employee=self.employee)
        self.assertEqual(record.source, AttendanceSource.HR)
        self.assertEqual(record.created_by, self.hr)


class CorrectionFlowTests(TestCase):
    def setUp(self):
        self.hr = make_hr()
        self.employee = make_employee()

    def test_correction_approved_updates_record(self):
        correction = AttendanceCorrectionRequest.objects.create(
            employee=self.employee,
            date=date(2024, 6, 3),
            requested_check_in="09:30",
            requested_check_out="18:30",
            reason="Forgot to check in",
        )
        self.client.force_login(self.hr)
        response = self.client.post(
            reverse("attendance:correction_decision", args=[correction.pk]),
            {"decision": "APPROVED", "note": ""},
        )
        self.assertEqual(response.status_code, 302)
        correction.refresh_from_db()
        self.assertEqual(correction.status, CorrectionStatus.APPROVED)
        record = AttendanceRecord.objects.get(
            employee=self.employee, date=date(2024, 6, 3)
        )
        self.assertEqual(str(record.check_in), "09:30:00")
