from django.test import TestCase
from django.urls import reverse

from .models import Role, User


class UserModelTests(TestCase):
    def test_role_properties(self):
        hr = User.objects.create_user(username="hr1", password="pw12345!", role=Role.HR)
        employee = User.objects.create_user(username="emp1", password="pw12345!")

        self.assertTrue(hr.is_hr)
        self.assertFalse(hr.is_employee)
        self.assertTrue(employee.is_employee)
        self.assertFalse(employee.is_hr)

    def test_default_role_is_employee(self):
        user = User.objects.create_user(username="plain", password="pw12345!")
        self.assertEqual(user.role, Role.EMPLOYEE)


class AccessControlTests(TestCase):
    def setUp(self):
        self.hr = User.objects.create_user(
            username="hr", password="pw12345!", role=Role.HR
        )
        self.employee = User.objects.create_user(
            username="emp", password="pw12345!", role=Role.EMPLOYEE
        )

    def test_anonymous_redirected_to_login(self):
        response = self.client.get(reverse("accounts:user_list"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response.url)

    def test_employee_blocked_from_hr_view(self):
        self.client.force_login(self.employee)
        response = self.client.get(reverse("accounts:user_list"))
        self.assertEqual(response.status_code, 403)

    def test_hr_can_view_user_list(self):
        self.client.force_login(self.hr)
        response = self.client.get(reverse("accounts:user_list"))
        self.assertEqual(response.status_code, 200)

    def test_hr_creates_hr_with_role_and_temp_password(self):
        self.client.force_login(self.hr)
        response = self.client.post(
            reverse("accounts:hr_create"),
            {
                "username": "hr2",
                "password1": "Str0ngPass!23",
                "password2": "Str0ngPass!23",
            },
        )
        self.assertEqual(response.status_code, 302)
        user = User.objects.get(username="hr2")
        self.assertEqual(user.role, Role.HR)
        self.assertTrue(user.must_change_password)


class ForcePasswordChangeTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="temp", password="pw12345!", must_change_password=True
        )

    def test_redirected_to_change_password(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("core:home"))
        self.assertRedirects(response, reverse("accounts:password_change"))

    def test_flag_cleared_after_change(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("accounts:password_change"),
            {
                "old_password": "pw12345!",
                "new_password1": "N3wStrong!pass",
                "new_password2": "N3wStrong!pass",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.user.refresh_from_db()
        self.assertFalse(self.user.must_change_password)
