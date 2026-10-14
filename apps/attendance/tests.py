from datetime import date, time

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import Role, User
from apps.audit.models import AuditLog
from apps.employees.models import Employee

from .forms import CorrectionRequestForm
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

    def test_duplicate_check_in_is_ignored(self):
        self.client.force_login(self.employee.user)
        self.client.post(reverse("attendance:check_in"))
        first = AttendanceRecord.objects.get(
            employee=self.employee, date=date.today()
        )
        self.client.post(reverse("attendance:check_in"))
        self.assertEqual(
            AttendanceRecord.objects.filter(
                employee=self.employee, date=date.today()
            ).count(),
            1,
        )
        first.refresh_from_db()
        self.assertIsNotNone(first.check_in)

    def test_duplicate_check_out_is_rejected(self):
        self.client.force_login(self.employee.user)
        self.client.post(reverse("attendance:check_in"))
        self.client.post(reverse("attendance:check_out"))
        record = AttendanceRecord.objects.get(
            employee=self.employee, date=date.today()
        )
        self.assertIsNotNone(record.check_out)
        first_check_out = record.check_out
        self.client.post(reverse("attendance:check_out"))
        record.refresh_from_db()
        self.assertEqual(record.check_out, first_check_out)


class AttendanceValidationTests(TestCase):
    """Requirement 11: inconsistent records are rejected at model level."""

    def setUp(self):
        self.employee = make_employee()

    def test_checkout_without_checkin_invalid(self):
        record = AttendanceRecord(
            employee=self.employee, date=date(2024, 5, 1), check_out=time(17, 0)
        )
        with self.assertRaises(ValidationError):
            record.full_clean()

    def test_checkout_before_checkin_invalid(self):
        record = AttendanceRecord(
            employee=self.employee,
            date=date(2024, 5, 1),
            check_in=time(14, 0),
            check_out=time(9, 0),
        )
        with self.assertRaises(ValidationError):
            record.full_clean()

    def test_database_constraint_blocks_inconsistent_row(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                AttendanceRecord.objects.create(
                    employee=self.employee,
                    date=date(2024, 5, 2),
                    check_in=time(14, 0),
                    check_out=time(9, 0),
                )

    def test_correction_requires_at_least_one_time(self):
        form = CorrectionRequestForm(
            data={"date": "2024-05-01", "reason": "Missed"}
        )
        self.assertFalse(form.is_valid())

    def test_correction_rejects_reversed_times(self):
        form = CorrectionRequestForm(
            data={
                "date": "2024-05-01",
                "requested_check_in": "14:00",
                "requested_check_out": "09:00",
                "reason": "Oops",
            }
        )
        self.assertFalse(form.is_valid())


class AttendanceIsolationTests(TestCase):
    """Item 2: an Employee only sees their own attendance."""

    def test_employee_list_hides_other_employee_records(self):
        employee = make_employee(username="a", employee_id="E001")
        other = make_employee(username="b", employee_id="E002")
        AttendanceRecord.objects.create(employee=other, date=date(2024, 7, 1))

        self.client.force_login(employee.user)
        response = self.client.get(reverse("attendance:my"))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            all(r.employee_id == employee.pk for r in response.context["records"])
        )


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

    def test_hr_manual_entry_is_audited(self):
        self.client.force_login(self.hr)
        self.client.post(
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
        self.assertTrue(
            AuditLog.objects.filter(
                actor=self.hr, action="ATTENDANCE_MANUAL_ENTRY"
            ).exists()
        )

    def test_employee_cannot_post_hr_entry(self):
        self.client.force_login(self.employee.user)
        response = self.client.post(
            reverse("attendance:create"),
            {
                "employee": self.employee.pk,
                "date": "2024-05-01",
                "status": AttendanceStatus.PRESENT,
            },
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(AttendanceRecord.objects.exists())


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

    def test_approve_records_reviewer_time_and_note(self):
        correction = AttendanceCorrectionRequest.objects.create(
            employee=self.employee,
            date=date(2024, 6, 4),
            requested_check_in="09:30",
            reason="Missed check-in",
        )
        self.client.force_login(self.hr)
        self.client.post(
            reverse("attendance:correction_decision", args=[correction.pk]),
            {"decision": "APPROVED", "note": "Verified with gate log"},
        )
        correction.refresh_from_db()
        self.assertEqual(correction.reviewed_by, self.hr)
        self.assertIsNotNone(correction.reviewed_at)
        self.assertEqual(correction.decision_note, "Verified with gate log")
        self.assertTrue(
            AuditLog.objects.filter(
                action="ATTENDANCE_CORRECTION_DECISION"
            ).exists()
        )

    def test_reject_does_not_change_attendance(self):
        correction = AttendanceCorrectionRequest.objects.create(
            employee=self.employee,
            date=date(2024, 6, 5),
            requested_check_out="18:00",
            reason="Left early",
        )
        self.client.force_login(self.hr)
        self.client.post(
            reverse("attendance:correction_decision", args=[correction.pk]),
            {"decision": "REJECTED", "note": "Not approved"},
        )
        correction.refresh_from_db()
        self.assertEqual(correction.status, CorrectionStatus.REJECTED)
        self.assertEqual(correction.reviewed_by, self.hr)
        self.assertIsNotNone(correction.reviewed_at)
        self.assertEqual(correction.decision_note, "Not approved")
        self.assertFalse(
            AttendanceRecord.objects.filter(
                employee=self.employee, date=date(2024, 6, 5)
            ).exists()
        )

    def test_employee_cannot_decide_correction(self):
        correction = AttendanceCorrectionRequest.objects.create(
            employee=self.employee,
            date=date(2024, 6, 6),
            requested_check_in="09:30",
            reason="Missed",
        )
        self.client.force_login(self.employee.user)
        response = self.client.post(
            reverse("attendance:correction_decision", args=[correction.pk]),
            {"decision": "APPROVED", "note": ""},
        )
        self.assertEqual(response.status_code, 403)
        correction.refresh_from_db()
        self.assertEqual(correction.status, CorrectionStatus.PENDING)

    def test_duplicate_pending_correction_blocked(self):
        self.client.force_login(self.employee.user)
        payload = {
            "date": "2024-06-07",
            "requested_check_in": "09:30",
            "reason": "Missed check-in",
        }
        self.client.post(reverse("attendance:correction_create"), data=payload)
        self.client.post(reverse("attendance:correction_create"), data=payload)
        self.assertEqual(
            AttendanceCorrectionRequest.objects.filter(
                employee=self.employee,
                date=date(2024, 6, 6 + 1),
                status=CorrectionStatus.PENDING,
            ).count(),
            1,
        )

    def test_employee_correction_request_audited(self):
        self.client.force_login(self.employee.user)
        self.client.post(
            reverse("attendance:correction_create"),
            {
                "date": "2024-06-07",
                "requested_check_in": "09:30",
                "reason": "Missed",
            },
        )
        self.assertTrue(
            AuditLog.objects.filter(
                actor=self.employee.user,
                action="ATTENDANCE_CORRECTION_REQUESTED",
            ).exists()
        )
