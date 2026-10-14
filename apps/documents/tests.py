from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import Role, User
from apps.employees.models import Employee

from .models import DocumentVisibility, HRDocument


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


class DocumentSecurityTests(TestCase):
    def setUp(self):
        self.hr = make_hr()
        self.owner = make_employee(username="owner", employee_id="E001")
        self.other = make_employee(username="other", employee_id="E002")
        self.created_docs = []

    def tearDown(self):
        for document in self.created_docs:
            if document.file:
                try:
                    document.file.delete(save=False)
                except PermissionError:
                    pass

    def _make_document(self, visibility, employee=None):
        document = HRDocument.objects.create(
            title="Contract",
            visibility=visibility,
            employee=employee,
            uploaded_by=self.hr,
            file=SimpleUploadedFile("contract.pdf", b"secret-bytes"),
        )
        self.created_docs.append(document)
        return document

    def test_owner_can_download_own_document(self):
        document = self._make_document(
            DocumentVisibility.SINGLE_EMPLOYEE, self.owner
        )
        self.client.force_login(self.owner.user)
        response = self.client.get(reverse("documents:download", args=[document.pk]))
        self.assertEqual(response.status_code, 200)
        response.close()

    def test_other_employee_cannot_download(self):
        document = self._make_document(
            DocumentVisibility.SINGLE_EMPLOYEE, self.owner
        )
        self.client.force_login(self.other.user)
        response = self.client.get(reverse("documents:download", args=[document.pk]))
        self.assertEqual(response.status_code, 403)

    def test_hr_only_document_hidden_from_employee(self):
        document = self._make_document(DocumentVisibility.HR_ONLY)
        self.client.force_login(self.owner.user)
        response = self.client.get(reverse("documents:download", args=[document.pk]))
        self.assertEqual(response.status_code, 403)

    def test_all_employees_document_visible(self):
        document = self._make_document(DocumentVisibility.ALL_EMPLOYEES)
        self.client.force_login(self.other.user)
        response = self.client.get(reverse("documents:download", args=[document.pk]))
        self.assertEqual(response.status_code, 200)
        response.close()

    def test_anonymous_cannot_download(self):
        document = self._make_document(DocumentVisibility.ALL_EMPLOYEES)
        response = self.client.get(reverse("documents:download", args=[document.pk]))
        self.assertEqual(response.status_code, 302)
