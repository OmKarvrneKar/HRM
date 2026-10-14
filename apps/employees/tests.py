from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import Role, User

from .models import Department, Employee, EmploymentStatus


class EmployeeIdTests(TestCase):
    """Item 1: employee_id is manually assigned, unique, and separate from the PK."""

    def test_employee_id_unique_and_separate_from_pk(self):
        first = User.objects.create_user(username="u1", password="pw12345!")
        second = User.objects.create_user(username="u2", password="pw12345!")
        employee = Employee.objects.create(
            user=first, employee_id="E001", full_name="One"
        )

        self.assertTrue(Employee._meta.get_field("employee_id").unique)
        self.assertEqual(Employee._meta.pk.name, "id")
        self.assertNotEqual(str(employee.pk), employee.employee_id)

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Employee.objects.create(
                    user=second, employee_id="E001", full_name="Duplicate"
                )


class EmployeeManagementTests(TestCase):
    def setUp(self):
        self.hr = User.objects.create_user(
            username="hr", password="pw12345!", role=Role.HR
        )
        self.department = Department.objects.create(name="Engineering")

    def _create_employee(self, employee_id="E001", full_name="Jane Doe"):
        self.client.force_login(self.hr)
        return self.client.post(
            reverse("employees:create"),
            {
                "username": f"user_{employee_id}",
                "password1": "Str0ngPass!23",
                "password2": "Str0ngPass!23",
                "employee_id": employee_id,
                "full_name": full_name,
                "phone": "1234567890",
                "address": "Somewhere",
                "company_email": "jane@example.com",
                "personal_email": "jane@home.com",
                "department": self.department.pk,
                "designation": "Engineer",
                "joining_date": "2024-01-01",
                "reporting_manager": "",
                "employment_status": EmploymentStatus.ACTIVE,
            },
        )

    def test_hr_creates_employee_with_user_account(self):
        response = self._create_employee()
        self.assertEqual(response.status_code, 302)
        employee = Employee.objects.get(employee_id="E001")
        self.assertEqual(employee.user.role, Role.EMPLOYEE)
        self.assertTrue(employee.user.must_change_password)
        self.assertEqual(employee.full_name, "Jane Doe")

    def test_employee_blocked_from_people_list(self):
        self._create_employee()
        employee_user = Employee.objects.get(employee_id="E001").user
        employee_user.must_change_password = False
        employee_user.save(update_fields=["must_change_password"])
        self.client.force_login(employee_user)
        response = self.client.get(reverse("employees:list"))
        self.assertEqual(response.status_code, 403)

    def test_employee_sees_own_profile_only(self):
        self._create_employee("E001", "Jane Doe")
        self._create_employee("E002", "John Smith")
        jane = Employee.objects.get(employee_id="E001").user
        jane.must_change_password = False
        jane.save(update_fields=["must_change_password"])
        self.client.force_login(jane)

        own = self.client.get(reverse("employees:my_profile"))
        self.assertEqual(own.status_code, 200)
        self.assertContains(own, "E001")
        self.assertNotContains(own, "E002")

        other = Employee.objects.get(employee_id="E002")
        response = self.client.get(reverse("employees:detail", args=[other.pk]))
        self.assertEqual(response.status_code, 403)

    def test_search_and_filter(self):
        self._create_employee(employee_id="E001", full_name="Jane Doe")
        self._create_employee(employee_id="E002", full_name="John Smith")
        self.client.force_login(self.hr)

        response = self.client.get(reverse("employees:list"), {"q": "John"})
        self.assertContains(response, "John Smith")
        self.assertNotContains(response, "Jane Doe")

        response = self.client.get(
            reverse("employees:list"), {"status": EmploymentStatus.RESIGNED}
        )
        self.assertNotContains(response, "John Smith")


class EmploymentStatusTests(TestCase):
    def test_status_is_separate_field(self):
        user = User.objects.create_user(username="e", password="pw12345!")
        employee = Employee.objects.create(
            user=user,
            employee_id="E100",
            full_name="Test User",
            employment_status=EmploymentStatus.ON_LEAVE,
        )
        self.assertEqual(employee.employment_status, EmploymentStatus.ON_LEAVE)
        self.assertFalse(employee.is_active)
