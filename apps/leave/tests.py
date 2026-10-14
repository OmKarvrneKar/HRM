from datetime import date

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import Role, User
from apps.audit.models import AuditLog
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


class LeaveIsolationTests(TestCase):
    """Item 2: an Employee only sees their own leave requests."""

    def test_employee_list_hides_other_employee_requests(self):
        owner = make_employee(username="a", employee_id="E001")
        other = make_employee(username="b", employee_id="E002")
        leave_type = LeaveType.objects.create(name="Sick")
        LeaveRequest.objects.create(
            employee=other,
            leave_type=leave_type,
            start_date=date(2024, 7, 1),
            end_date=date(2024, 7, 2),
            reason="Not yours",
        )

        self.client.force_login(owner.user)
        response = self.client.get(reverse("leave:my"))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            all(r.employee_id == owner.pk for r in response.context["requests"])
        )


class LeaveValidationTests(TestCase):
    def setUp(self):
        self.employee = make_employee()
        self.leave_type = LeaveType.objects.create(name="Casual")

    def test_model_clean_rejects_reversed_dates(self):
        request_obj = LeaveRequest(
            employee=self.employee,
            leave_type=self.leave_type,
            start_date=date(2024, 7, 5),
            end_date=date(2024, 7, 1),
            reason="Oops",
        )
        with self.assertRaises(ValidationError):
            request_obj.full_clean()

    def test_database_constraint_blocks_reversed_dates(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                LeaveRequest.objects.create(
                    employee=self.employee,
                    leave_type=self.leave_type,
                    start_date=date(2024, 7, 5),
                    end_date=date(2024, 7, 1),
                    reason="Oops",
                )

    def test_view_rejects_reversed_dates(self):
        self.client.force_login(self.employee.user)
        response = self.client.post(
            reverse("leave:create"),
            {
                "leave_type": self.leave_type.pk,
                "start_date": "2024-07-05",
                "end_date": "2024-07-01",
                "reason": "Oops",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(LeaveRequest.objects.exists())


class LeaveOverlapTests(TestCase):
    def setUp(self):
        self.employee = make_employee()
        self.leave_type = LeaveType.objects.create(name="Casual")

    def _post(self, start, end):
        return self.client.post(
            reverse("leave:create"),
            {
                "leave_type": self.leave_type.pk,
                "start_date": start,
                "end_date": end,
                "reason": "Request",
            },
        )

    def _existing(self, start, end, status=LeaveStatus.PENDING, employee=None):
        return LeaveRequest.objects.create(
            employee=employee or self.employee,
            leave_type=self.leave_type,
            start_date=start,
            end_date=end,
            reason="Existing",
            status=status,
        )

    def test_overlapping_pending_blocked(self):
        self._existing(date(2024, 7, 1), date(2024, 7, 3))
        self.client.force_login(self.employee.user)
        response = self._post("2024-07-02", "2024-07-04")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(LeaveRequest.objects.count(), 1)

    def test_overlapping_approved_blocked(self):
        self._existing(
            date(2024, 7, 1), date(2024, 7, 3), status=LeaveStatus.APPROVED
        )
        self.client.force_login(self.employee.user)
        response = self._post("2024-07-02", "2024-07-04")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(LeaveRequest.objects.count(), 1)

    def test_rejected_does_not_block(self):
        self._existing(
            date(2024, 7, 1), date(2024, 7, 3), status=LeaveStatus.REJECTED
        )
        self.client.force_login(self.employee.user)
        response = self._post("2024-07-02", "2024-07-04")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(LeaveRequest.objects.count(), 2)

    def test_boundary_touching_dates_overlap(self):
        self._existing(date(2024, 7, 1), date(2024, 7, 3))
        self.client.force_login(self.employee.user)
        response = self._post("2024-07-03", "2024-07-05")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(LeaveRequest.objects.count(), 1)

    def test_non_overlapping_allowed(self):
        self._existing(date(2024, 7, 1), date(2024, 7, 3))
        self.client.force_login(self.employee.user)
        response = self._post("2024-07-04", "2024-07-06")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(LeaveRequest.objects.count(), 2)

    def test_other_employee_overlap_not_blocked(self):
        other = make_employee(username="x", employee_id="E002")
        self._existing(date(2024, 7, 1), date(2024, 7, 3), employee=other)
        self.client.force_login(self.employee.user)
        response = self._post("2024-07-02", "2024-07-04")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(LeaveRequest.objects.count(), 2)


class LeaveDecisionTests(TestCase):
    def setUp(self):
        self.hr = make_hr()
        self.employee = make_employee()
        self.leave_type = LeaveType.objects.create(name="Casual")
        self.leave_request = LeaveRequest.objects.create(
            employee=self.employee,
            leave_type=self.leave_type,
            start_date=date(2024, 7, 1),
            end_date=date(2024, 7, 3),
            reason="Family",
        )

    def test_decision_records_reviewer_time_note_and_audit(self):
        self.client.force_login(self.hr)
        self.client.post(
            reverse("leave:decision", args=[self.leave_request.pk]),
            {"decision": "APPROVED", "note": "Enjoy"},
        )
        self.leave_request.refresh_from_db()
        self.assertEqual(self.leave_request.reviewed_by, self.hr)
        self.assertIsNotNone(self.leave_request.reviewed_at)
        self.assertEqual(self.leave_request.decision_note, "Enjoy")
        self.assertTrue(
            AuditLog.objects.filter(
                actor=self.hr, action="LEAVE_DECISION"
            ).exists()
        )

    def test_employee_cannot_decide(self):
        self.client.force_login(self.employee.user)
        response = self.client.post(
            reverse("leave:decision", args=[self.leave_request.pk]),
            {"decision": "APPROVED", "note": ""},
        )
        self.assertEqual(response.status_code, 403)
        self.leave_request.refresh_from_db()
        self.assertEqual(self.leave_request.status, LeaveStatus.PENDING)

    def test_already_decided_cannot_be_changed(self):
        self.leave_request.status = LeaveStatus.APPROVED
        self.leave_request.save()
        self.client.force_login(make_hr(username="hr2"))
        self.client.post(
            reverse("leave:decision", args=[self.leave_request.pk]),
            {"decision": "REJECTED", "note": "Flip"},
        )
        self.leave_request.refresh_from_db()
        self.assertEqual(self.leave_request.status, LeaveStatus.APPROVED)


class LeaveTypeManagementTests(TestCase):
    def setUp(self):
        self.hr = make_hr()
        self.employee = make_employee()

    def test_hr_creates_leave_type_and_audits(self):
        self.client.force_login(self.hr)
        response = self.client.post(
            reverse("leave:type_create"),
            {"name": "Sick", "description": "Medical", "is_active": "on"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(LeaveType.objects.filter(name="Sick").exists())
        self.assertTrue(
            AuditLog.objects.filter(
                actor=self.hr, action="LEAVE_TYPE_CREATED"
            ).exists()
        )

    def test_hr_updates_leave_type_and_audits(self):
        leave_type = LeaveType.objects.create(name="Casual")
        self.client.force_login(self.hr)
        response = self.client.post(
            reverse("leave:type_edit", args=[leave_type.pk]),
            {"name": "Casual Leave", "description": "", "is_active": "on"},
        )
        self.assertEqual(response.status_code, 302)
        leave_type.refresh_from_db()
        self.assertEqual(leave_type.name, "Casual Leave")
        self.assertTrue(
            AuditLog.objects.filter(
                actor=self.hr, action="LEAVE_TYPE_UPDATED"
            ).exists()
        )

    def test_duplicate_name_rejected(self):
        LeaveType.objects.create(name="Casual")
        self.client.force_login(self.hr)
        response = self.client.post(
            reverse("leave:type_create"),
            {"name": "casual", "description": "", "is_active": "on"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(LeaveType.objects.count(), 1)

    def test_employee_cannot_manage_types(self):
        leave_type = LeaveType.objects.create(name="Casual")
        self.client.force_login(self.employee.user)
        self.assertEqual(
            self.client.get(reverse("leave:type_create")).status_code, 403
        )
        self.assertEqual(
            self.client.get(
                reverse("leave:type_edit", args=[leave_type.pk])
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(
                reverse("leave:type_create"),
                {"name": "X", "description": "", "is_active": "on"},
            ).status_code,
            403,
        )
