from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import Role, User
from apps.employees.models import Department, Employee

from .models import AuditLog
from .services import log_action


class AuditLogTests(TestCase):
    def test_log_action_records_object(self):
        user = User.objects.create_user(username="hr", password="pw12345!", role=Role.HR)
        entry = log_action(user, "TEST_ACTION", user, description="something happened")
        self.assertEqual(entry.actor, user)
        self.assertEqual(entry.action, "TEST_ACTION")
        self.assertEqual(entry.model_name, "User")

    def test_employee_creation_is_audited(self):
        hr = User.objects.create_user(username="hr2", password="pw12345!", role=Role.HR)
        department = Department.objects.create(name="Engineering")
        self.client.force_login(hr)
        self.client.post(
            reverse("employees:create"),
            {
                "username": "newbie",
                "password1": "Str0ngPass!23",
                "password2": "Str0ngPass!23",
                "employee_id": "E900",
                "full_name": "New Bie",
                "phone": "",
                "address": "",
                "company_email": "",
                "personal_email": "",
                "department": department.pk,
                "designation": "",
                "joining_date": "",
                "reporting_manager": "",
                "employment_status": "ACTIVE",
            },
        )
        self.assertTrue(Employee.objects.filter(employee_id="E900").exists())
        self.assertTrue(
            AuditLog.objects.filter(action="EMPLOYEE_CREATED").exists()
        )
