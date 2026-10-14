from django.test import TestCase
from django.urls import reverse

from apps.audit.models import AuditLog
from apps.employees.models import Department, Employee

from .forms import HRUserCreateForm
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

    def test_all_routes_redirect_to_change_password(self):
        self.client.force_login(self.user)
        routes = [
            reverse("core:home"),
            reverse("employees:my_profile"),
            reverse("attendance:my"),
            reverse("leave:my"),
            reverse("projects:my_projects"),
            reverse("documents:my_documents"),
            reverse("notifications:my"),
            "/django-admin/",
        ]
        for url in routes:
            with self.subTest(url=url):
                self.assertRedirects(
                    self.client.get(url), reverse("accounts:password_change")
                )

    def test_logout_is_allowed_while_flagged(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse("accounts:logout"))
        self.assertEqual(response.status_code, 302)
        self.assertNotEqual(response.url, reverse("accounts:password_change"))


class HRAccessTests(TestCase):
    """Item 3: an Employee cannot reach any HR-only route, method aside."""

    def setUp(self):
        self.employee = User.objects.create_user(
            username="emp", password="pw12345!", role=Role.EMPLOYEE
        )
        Employee.objects.create(
            user=self.employee, employee_id="E001", full_name="Emp"
        )
        self.client.force_login(self.employee)

    def test_employee_gets_403_on_all_hr_routes(self):
        routes = [
            reverse("accounts:user_list"),
            reverse("accounts:hr_create"),
            reverse("employees:list"),
            reverse("employees:create"),
            reverse("employees:departments"),
            reverse("employees:department_create"),
            reverse("employees:detail", args=[999999]),
            reverse("employees:update", args=[999999]),
            reverse("employees:status_update", args=[999999]),
            reverse("employees:contact_add", args=[999999]),
            reverse("employees:contact_delete", args=[999999]),
            reverse("attendance:list"),
            reverse("attendance:create"),
            reverse("attendance:update", args=[999999]),
            reverse("attendance:corrections"),
            reverse("attendance:correction_decision", args=[999999]),
            reverse("leave:requests"),
            reverse("leave:decision", args=[999999]),
            reverse("leave:types"),
            reverse("leave:type_create"),
            reverse("projects:list"),
            reverse("projects:create"),
            reverse("projects:detail", args=[999999]),
            reverse("projects:update", args=[999999]),
            reverse("projects:assign", args=[999999]),
            reverse("projects:unassign", args=[999999]),
            reverse("projects:groups"),
            reverse("projects:group_create"),
            reverse("projects:group_detail", args=[999999]),
            reverse("projects:group_member_add", args=[999999]),
            reverse("projects:group_member_remove", args=[999999]),
            reverse("projects:worklog_review"),
            reverse("projects:worklog_review_decision", args=[999999]),
            reverse("documents:list"),
            reverse("documents:create"),
            reverse("documents:delete", args=[999999]),
            reverse("documents:legal"),
            reverse("documents:legal_create"),
            reverse("notifications:announcements_hr"),
            reverse("notifications:announcement_create"),
            reverse("notifications:calendar_hr"),
            reverse("notifications:calendar_create"),
        ]
        for url in routes:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 403)


class RoleEscalationTests(TestCase):
    """Item 4: an Employee cannot create HR accounts or self-assign a role."""

    def setUp(self):
        self.employee = User.objects.create_user(
            username="emp", password="pw12345!", role=Role.EMPLOYEE
        )
        Employee.objects.create(
            user=self.employee, employee_id="E001", full_name="Emp"
        )

    def test_employee_cannot_create_hr_account(self):
        self.client.force_login(self.employee)
        response = self.client.post(
            reverse("accounts:hr_create"),
            {
                "username": "escalated",
                "password1": "Str0ngPass!23",
                "password2": "Str0ngPass!23",
                "role": Role.HR,
            },
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(User.objects.filter(username="escalated").exists())

    def test_hr_create_form_forces_hr_role(self):
        form = HRUserCreateForm(
            data={
                "username": "hr2",
                "password1": "Str0ngPass!23",
                "password2": "Str0ngPass!23",
                "role": Role.EMPLOYEE,
            }
        )
        self.assertTrue(form.is_valid())
        self.assertEqual(form.save().role, Role.HR)


class AdminAccessTests(TestCase):
    """Item 5: Django admin is gated to staff/superusers."""

    def test_non_staff_users_redirected_from_admin(self):
        employee = User.objects.create_user(
            username="emp", password="pw12345!", role=Role.EMPLOYEE
        )
        hr = User.objects.create_user(
            username="hr", password="pw12345!", role=Role.HR
        )
        self.assertFalse(employee.is_staff)
        self.assertFalse(hr.is_staff)
        for user in (employee, hr):
            self.client.force_login(user)
            response = self.client.get("/django-admin/")
            self.assertEqual(response.status_code, 302)
            self.assertIn("/django-admin/login/", response.url)


class PasswordStorageTests(TestCase):
    """Item 7: temporary passwords are hashed, never stored/logged in plaintext."""

    def test_temp_password_hashed_and_not_audited(self):
        hr = User.objects.create_user(
            username="hr", password="pw12345!", role=Role.HR
        )
        department = Department.objects.create(name="Engineering")
        self.client.force_login(hr)
        response = self.client.post(
            reverse("employees:create"),
            {
                "username": "tempuser",
                "password1": "Str0ngPass!23",
                "password2": "Str0ngPass!23",
                "employee_id": "E700",
                "full_name": "Temp User",
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
        self.assertEqual(response.status_code, 302)
        user = User.objects.get(username="tempuser")
        self.assertTrue(user.password.startswith("pbkdf2_sha256$"))
        self.assertNotEqual(user.password, "Str0ngPass!23")
        for entry in AuditLog.objects.all():
            self.assertNotIn(
                "Str0ngPass!23", f"{entry.description} {entry.metadata}"
            )
