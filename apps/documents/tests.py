from pathlib import Path

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import Role, User
from apps.audit.models import AuditLog
from apps.employees.models import Employee
from apps.projects.models import GroupMembership, TeamGroup

from .models import CommunicationAudience, DocumentVisibility, HRDocument
from .validators import MAX_DOCUMENT_SIZE

PDF_BYTES = b"%PDF-1.4 secret-bytes"


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


def pdf(name="contract.pdf", content=PDF_BYTES):
    return SimpleUploadedFile(name, content, content_type="application/pdf")


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
            file=SimpleUploadedFile("contract.pdf", PDF_BYTES),
        )
        self.created_docs.append(document)
        return document

    # -- Download authorization -------------------------------------------- #
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
        self.assertEqual(response.status_code, 404)

    def test_hr_only_document_hidden_from_employee(self):
        document = self._make_document(DocumentVisibility.HR_ONLY)
        self.client.force_login(self.other.user)
        response = self.client.get(reverse("documents:download", args=[document.pk]))
        self.assertEqual(response.status_code, 404)

    def test_all_employees_document_visible(self):
        document = self._make_document(DocumentVisibility.ALL_EMPLOYEES)
        self.client.force_login(self.other.user)
        response = self.client.get(reverse("documents:download", args=[document.pk]))
        self.assertEqual(response.status_code, 200)
        response.close()

    def test_hr_can_download_any_document(self):
        document = self._make_document(DocumentVisibility.HR_ONLY)
        self.client.force_login(self.hr)
        response = self.client.get(reverse("documents:download", args=[document.pk]))
        self.assertEqual(response.status_code, 200)
        response.close()

    def test_anonymous_cannot_download(self):
        document = self._make_document(DocumentVisibility.ALL_EMPLOYEES)
        response = self.client.get(reverse("documents:download", args=[document.pk]))
        self.assertEqual(response.status_code, 302)

    def test_download_of_missing_document_is_404(self):
        self.client.force_login(self.owner.user)
        response = self.client.get(reverse("documents:download", args=[999999]))
        self.assertEqual(response.status_code, 404)

    def test_employee_lists_only_see_authorized_documents(self):
        self._make_document(DocumentVisibility.HR_ONLY)
        self._make_document(DocumentVisibility.ALL_EMPLOYEES)
        self._make_document(DocumentVisibility.SINGLE_EMPLOYEE, self.owner)
        self._make_document(DocumentVisibility.SINGLE_EMPLOYEE, self.other)
        self.client.force_login(self.owner.user)
        response = self.client.get(reverse("documents:my_documents"))
        titles = [doc.pk for doc in response.context["documents"]]
        self.assertEqual(len(titles), 2)

    def test_employee_cannot_reach_hr_document_routes(self):
        self.client.force_login(self.owner.user)
        for name, args in [
            ("documents:list", []),
            ("documents:create", []),
            ("documents:legal", []),
        ]:
            self.assertEqual(
                self.client.get(reverse(name, args=args)).status_code, 403
            )

    # -- Safe storage ------------------------------------------------------ #
    def test_stored_filename_is_randomised(self):
        document = self._make_document(DocumentVisibility.HR_ONLY)
        self.assertNotIn("contract", document.file.name)
        self.assertTrue(document.file.name.startswith("hr_documents/"))
        self.assertTrue(document.file.name.endswith(".pdf"))

    def test_download_name_is_safe(self):
        document = self._make_document(DocumentVisibility.HR_ONLY)
        document.title = "Q1 Report / 2026"
        self.assertEqual(document.download_name, "q1-report-2026.pdf")
        self.assertNotIn("/", document.download_name)

    # -- Upload validation ------------------------------------------------- #
    def test_rejects_disallowed_extension(self):
        self.client.force_login(self.hr)
        response = self.client.post(
            reverse("documents:create"),
            {
                "title": "Bad",
                "document_type": "OTHER",
                "visibility": DocumentVisibility.HR_ONLY,
                "file": SimpleUploadedFile("evil.exe", b"MZ..."),
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("file", response.context["form"].errors)

    def test_rejects_content_type_mismatch(self):
        self.client.force_login(self.hr)
        response = self.client.post(
            reverse("documents:create"),
            {
                "title": "Spoofed",
                "document_type": "OTHER",
                "visibility": DocumentVisibility.HR_ONLY,
                "file": SimpleUploadedFile(
                    "report.pdf", b"MZ nope", content_type="application/pdf"
                ),
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("file", response.context["form"].errors)

    def test_rejects_oversized_file(self):
        self.client.force_login(self.hr)
        oversized = SimpleUploadedFile(
            "big.pdf", b"%PDF" + b"0" * (MAX_DOCUMENT_SIZE + 1)
        )
        response = self.client.post(
            reverse("documents:create"),
            {
                "title": "Big",
                "document_type": "OTHER",
                "visibility": DocumentVisibility.HR_ONLY,
                "file": oversized,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("file", response.context["form"].errors)

    def test_accepts_valid_upload_and_audits(self):
        self.client.force_login(self.hr)
        response = self.client.post(
            reverse("documents:create"),
            {
                "title": "Policy",
                "document_type": "POLICY",
                "visibility": DocumentVisibility.ALL_EMPLOYEES,
                "file": pdf("policy.pdf"),
            },
        )
        self.assertEqual(response.status_code, 302)
        document = HRDocument.objects.get(title="Policy")
        self.created_docs.append(document)
        self.assertTrue(
            AuditLog.objects.filter(action="DOCUMENT_UPLOADED").exists()
        )

    def test_download_is_audited(self):
        document = self._make_document(DocumentVisibility.ALL_EMPLOYEES)
        self.client.force_login(self.other.user)
        response = self.client.get(reverse("documents:download", args=[document.pk]))
        response.close()
        self.assertTrue(
            AuditLog.objects.filter(action="DOCUMENT_DOWNLOADED").exists()
        )

    # -- HR metadata management ------------------------------------------- #
    def test_hr_can_update_metadata(self):
        document = self._make_document(DocumentVisibility.HR_ONLY)
        self.client.force_login(self.hr)
        response = self.client.post(
            reverse("documents:update", args=[document.pk]),
            {
                "title": "Renamed",
                "document_type": "POLICY",
                "visibility": DocumentVisibility.ALL_EMPLOYEES,
            },
        )
        self.assertRedirects(response, reverse("documents:list"))
        document.refresh_from_db()
        self.assertEqual(document.title, "Renamed")
        self.assertEqual(document.visibility, DocumentVisibility.ALL_EMPLOYEES)
        self.assertTrue(
            AuditLog.objects.filter(action="DOCUMENT_UPDATED").exists()
        )

    def test_delete_removes_file_and_audits(self):
        document = self._make_document(DocumentVisibility.HR_ONLY)
        storage = document.file.storage
        name = document.file.name
        self.client.force_login(self.hr)
        response = self.client.post(reverse("documents:delete", args=[document.pk]))
        self.assertRedirects(response, reverse("documents:list"))
        self.assertFalse(HRDocument.objects.filter(pk=document.pk).exists())
        self.assertFalse(storage.exists(name))
        self.assertTrue(
            AuditLog.objects.filter(action="DOCUMENT_DELETED").exists()
        )


class LegalCommunicationTests(TestCase):
    def setUp(self):
        self.hr = make_hr()
        self.alice = make_employee(username="alice", employee_id="E001")
        self.bob = make_employee(username="bob", employee_id="E002")
        self.group = TeamGroup.objects.create(name="Site A", created_by=self.hr)
        GroupMembership.objects.create(group=self.group, employee=self.alice)
        self.created = []

    def tearDown(self):
        for document in self.created:
            if document.file:
                try:
                    document.file.delete(save=False)
                except PermissionError:
                    pass

    def _attachment(self, visibility=DocumentVisibility.HR_ONLY):
        document = HRDocument.objects.create(
            title="Notice",
            visibility=visibility,
            uploaded_by=self.hr,
            file=SimpleUploadedFile("notice.pdf", PDF_BYTES),
        )
        self.created.append(document)
        return document

    def _communication(self, audience, employee=None, group=None, attachment=None):
        from .models import LegalCommunication

        return LegalCommunication.objects.create(
            title="Policy notice",
            body="Body",
            audience=audience,
            employee=employee,
            group=group,
            attachment=attachment,
            created_by=self.hr,
        )

    def test_single_employee_communication_visibility(self):
        self._communication(
            CommunicationAudience.SINGLE_EMPLOYEE, employee=self.alice
        )
        self.client.force_login(self.alice.user)
        self.assertEqual(
            len(self.client.get(reverse("documents:my_communications")).context[
                "communications"
            ]),
            1,
        )
        self.client.force_login(self.bob.user)
        self.assertEqual(
            len(self.client.get(reverse("documents:my_communications")).context[
                "communications"
            ]),
            0,
        )

    def test_group_communication_visibility(self):
        self._communication(CommunicationAudience.GROUP, group=self.group)
        self.client.force_login(self.alice.user)
        self.assertEqual(
            len(self.client.get(reverse("documents:my_communications")).context[
                "communications"
            ]),
            1,
        )
        self.client.force_login(self.bob.user)
        self.assertEqual(
            len(self.client.get(reverse("documents:my_communications")).context[
                "communications"
            ]),
            0,
        )

    def test_company_wide_communication_visibility(self):
        self._communication(CommunicationAudience.ALL_EMPLOYEES)
        for employee in (self.alice, self.bob):
            self.client.force_login(employee.user)
            self.assertEqual(
                len(
                    self.client.get(
                        reverse("documents:my_communications")
                    ).context["communications"]
                ),
                1,
            )

    def test_inactive_communication_hidden(self):
        comm = self._communication(
            CommunicationAudience.ALL_EMPLOYEES
        )
        comm.is_active = False
        comm.save(update_fields=["is_active"])
        self.client.force_login(self.bob.user)
        self.assertEqual(
            len(self.client.get(reverse("documents:my_communications")).context[
                "communications"
            ]),
            0,
        )

    def test_attachment_downloadable_when_communication_visible(self):
        attachment = self._attachment(DocumentVisibility.HR_ONLY)
        self._communication(
            CommunicationAudience.SINGLE_EMPLOYEE,
            employee=self.alice,
            attachment=attachment,
        )
        self.client.force_login(self.alice.user)
        response = self.client.get(reverse("documents:download", args=[attachment.pk]))
        self.assertEqual(response.status_code, 200)
        response.close()

    def test_attachment_blocked_for_unauthorized_employee(self):
        attachment = self._attachment(DocumentVisibility.HR_ONLY)
        self._communication(
            CommunicationAudience.SINGLE_EMPLOYEE,
            employee=self.alice,
            attachment=attachment,
        )
        self.client.force_login(self.bob.user)
        response = self.client.get(reverse("documents:download", args=[attachment.pk]))
        self.assertEqual(response.status_code, 404)

    def test_audience_requires_target(self):
        from .forms import LegalCommunicationForm

        form = LegalCommunicationForm(
            data={
                "title": "x",
                "body": "y",
                "audience": CommunicationAudience.SINGLE_EMPLOYEE,
                "is_active": True,
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("employee", form.errors)

        form = LegalCommunicationForm(
            data={
                "title": "x",
                "body": "y",
                "audience": CommunicationAudience.GROUP,
                "is_active": True,
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("group", form.errors)

    def test_hr_can_create_and_update_communication(self):
        self.client.force_login(self.hr)
        response = self.client.post(
            reverse("documents:legal_create"),
            {
                "title": "All staff",
                "body": "Notice",
                "audience": CommunicationAudience.ALL_EMPLOYEES,
                "is_active": "on",
            },
        )
        self.assertRedirects(response, reverse("documents:legal"))
        from .models import LegalCommunication

        comm = LegalCommunication.objects.get(title="All staff")
        self.assertTrue(
            AuditLog.objects.filter(action="LEGAL_COMMUNICATION_CREATED").exists()
        )
        response = self.client.post(
            reverse("documents:legal_edit", args=[comm.pk]),
            {
                "title": "Notice v2",
                "body": "Notice",
                "audience": CommunicationAudience.ALL_EMPLOYEES,
                "is_active": "on",
            },
        )
        self.assertRedirects(response, reverse("documents:legal"))
        comm.refresh_from_db()
        self.assertEqual(comm.title, "Notice v2")
        self.assertTrue(
            AuditLog.objects.filter(action="LEGAL_COMMUNICATION_UPDATED").exists()
        )

    def test_oversized_document_constant(self):
        self.assertGreater(MAX_DOCUMENT_SIZE, 0)


class PrivateStorageTests(TestCase):
    """M8: private documents must never be reachable via a public media URL."""

    def setUp(self):
        self.hr = make_hr(username="priv_hr")
        self.document = HRDocument.objects.create(
            title="Secret",
            visibility=DocumentVisibility.HR_ONLY,
            uploaded_by=self.hr,
            file=SimpleUploadedFile("contract.pdf", PDF_BYTES),
        )

    def tearDown(self):
        try:
            self.document.file.delete(save=False)
        except Exception:
            pass

    def test_storage_never_generates_public_url(self):
        field = HRDocument._meta.get_field("file")
        self.assertIsNone(field.storage.url("hr_documents/anything.pdf"))

    def test_private_root_is_outside_public_media(self):
        from django.conf import settings

        private_root = Path(settings.PRIVATE_MEDIA_ROOT).resolve()
        media_root = Path(settings.MEDIA_ROOT).resolve()
        self.assertNotEqual(private_root, media_root)
        self.assertNotIn(str(media_root), str(private_root))

    def test_private_file_is_not_served_under_media_url(self):
        self.client.force_login(self.hr)
        url = "/media/" + self.document.file.name
        self.assertEqual(self.client.get(url).status_code, 404)
