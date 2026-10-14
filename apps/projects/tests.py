from datetime import date, timedelta

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import Role, User
from apps.audit.models import AuditLog
from apps.employees.models import Employee

from .models import (
    GroupMembership,
    Project,
    ProjectAssignment,
    TeamGroup,
    WorkLog,
    WorkLogStatus,
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


def make_project(name="Apollo", start_date=None):
    return Project.objects.create(name=name, start_date=start_date)


class ProjectManagementTests(TestCase):
    def setUp(self):
        self.hr = make_hr()
        self.employee = make_employee()

    def test_hr_creates_project_with_audit(self):
        self.client.force_login(self.hr)
        response = self.client.post(
            reverse("projects:create"),
            {
                "name": "Orion",
                "description": "New",
                "status": "ACTIVE",
                "start_date": "2024-07-01",
                "end_date": "2024-08-01",
            },
        )
        self.assertEqual(response.status_code, 302)
        project = Project.objects.get(name="Orion")
        self.assertEqual(project.created_by, self.hr)
        self.assertTrue(
            AuditLog.objects.filter(action="PROJECT_CREATED").exists()
        )

    def test_hr_updates_project_with_audit(self):
        project = make_project()
        self.client.force_login(self.hr)
        response = self.client.post(
            reverse("projects:update", args=[project.pk]),
            {"name": "Apollo v2", "description": "", "status": "COMPLETED"},
        )
        self.assertEqual(response.status_code, 302)
        project.refresh_from_db()
        self.assertEqual(project.name, "Apollo v2")
        self.assertTrue(
            AuditLog.objects.filter(action="PROJECT_UPDATED").exists()
        )

    def test_archive_and_restore_project_with_audit(self):
        project = make_project()
        self.client.force_login(self.hr)
        self.client.post(reverse("projects:archive", args=[project.pk]))
        project.refresh_from_db()
        self.assertTrue(project.is_archived)
        self.client.post(reverse("projects:archive", args=[project.pk]))
        project.refresh_from_db()
        self.assertFalse(project.is_archived)
        self.assertTrue(
            AuditLog.objects.filter(action="PROJECT_ARCHIVED").exists()
        )
        self.assertTrue(
            AuditLog.objects.filter(action="PROJECT_UNARCHIVED").exists()
        )

    def test_project_list_hides_archived_by_default(self):
        make_project(name="Active")
        archived = make_project(name="Old")
        archived.is_archived = True
        archived.save()
        self.client.force_login(self.hr)
        response = self.client.get(reverse("projects:list"))
        self.assertContains(response, "Active")
        self.assertNotContains(response, "Old")
        response = self.client.get(reverse("projects:list"), {"archived": "1"})
        self.assertContains(response, "Old")

    def test_employee_cannot_access_hr_project_routes(self):
        project = make_project()
        self.client.force_login(self.employee.user)
        self.assertEqual(self.client.get(reverse("projects:list")).status_code, 403)
        self.assertEqual(
            self.client.get(reverse("projects:detail", args=[project.pk])).status_code,
            403,
        )
        self.assertEqual(
            self.client.get(reverse("projects:create")).status_code, 403
        )
        self.assertEqual(
            self.client.get(reverse("projects:update", args=[project.pk])).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(
                reverse("projects:archive", args=[project.pk])
            ).status_code,
            403,
        )
        project.refresh_from_db()
        self.assertFalse(project.is_archived)


class AssignmentTests(TestCase):
    def setUp(self):
        self.hr = make_hr()
        self.employee = make_employee()
        self.project = make_project()

    def test_hr_assigns_employee_with_audit(self):
        self.client.force_login(self.hr)
        response = self.client.post(
            reverse("projects:assign", args=[self.project.pk]),
            {"employee": self.employee.pk, "role": "Developer"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            ProjectAssignment.objects.filter(
                project=self.project, employee=self.employee
            ).exists()
        )
        self.assertTrue(
            AuditLog.objects.filter(action="PROJECT_ASSIGNMENT_ADDED").exists()
        )

    def test_duplicate_assignment_blocked(self):
        ProjectAssignment.objects.create(
            project=self.project, employee=self.employee
        )
        self.client.force_login(self.hr)
        response = self.client.post(
            reverse("projects:assign", args=[self.project.pk]),
            {"employee": self.employee.pk, "role": "Again"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            ProjectAssignment.objects.filter(project=self.project).count(), 1
        )

    def test_removing_assignment_is_audited(self):
        assignment = ProjectAssignment.objects.create(
            project=self.project, employee=self.employee
        )
        self.client.force_login(self.hr)
        self.client.post(reverse("projects:unassign", args=[assignment.pk]))
        self.assertFalse(ProjectAssignment.objects.filter(pk=assignment.pk).exists())
        self.assertTrue(
            AuditLog.objects.filter(action="PROJECT_ASSIGNMENT_REMOVED").exists()
        )

    def test_employee_cannot_assign(self):
        self.client.force_login(self.employee.user)
        response = self.client.post(
            reverse("projects:assign", args=[self.project.pk]),
            {"employee": self.employee.pk, "role": "X"},
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(ProjectAssignment.objects.exists())


class GroupTests(TestCase):
    def setUp(self):
        self.hr = make_hr()
        self.employee = make_employee()

    def test_hr_creates_group_with_audit(self):
        self.client.force_login(self.hr)
        response = self.client.post(
            reverse("projects:group_create"),
            {"name": "Platform", "description": "Core"},
        )
        self.assertEqual(response.status_code, 302)
        group = TeamGroup.objects.get(name="Platform")
        self.assertEqual(group.created_by, self.hr)
        self.assertTrue(AuditLog.objects.filter(action="GROUP_CREATED").exists())

    def test_group_update_is_audited(self):
        group = TeamGroup.objects.create(name="Platform")
        self.client.force_login(self.hr)
        response = self.client.post(
            reverse("projects:group_edit", args=[group.pk]),
            {"name": "Platform Core", "description": ""},
        )
        self.assertEqual(response.status_code, 302)
        group.refresh_from_db()
        self.assertEqual(group.name, "Platform Core")
        self.assertTrue(AuditLog.objects.filter(action="GROUP_UPDATED").exists())

    def test_add_and_remove_member_audited(self):
        group = TeamGroup.objects.create(name="Platform")
        self.client.force_login(self.hr)
        self.client.post(
            reverse("projects:group_member_add", args=[group.pk]),
            {"employee": self.employee.pk},
        )
        membership = GroupMembership.objects.get(group=group)
        self.assertTrue(AuditLog.objects.filter(action="GROUP_MEMBER_ADDED").exists())
        self.client.post(
            reverse("projects:group_member_remove", args=[membership.pk])
        )
        self.assertFalse(GroupMembership.objects.filter(group=group).exists())
        self.assertTrue(
            AuditLog.objects.filter(action="GROUP_MEMBER_REMOVED").exists()
        )

    def test_employee_cannot_manage_groups(self):
        group = TeamGroup.objects.create(name="Platform")
        self.client.force_login(self.employee.user)
        self.assertEqual(
            self.client.get(reverse("projects:groups")).status_code, 403
        )
        self.assertEqual(
            self.client.get(reverse("projects:group_create")).status_code, 403
        )
        self.assertEqual(
            self.client.get(reverse("projects:group_edit", args=[group.pk])).status_code,
            403,
        )


class WorkLogSubmissionTests(TestCase):
    def setUp(self):
        self.employee = make_employee()
        self.project = make_project(start_date=date(2024, 7, 1))
        ProjectAssignment.objects.create(
            project=self.project, employee=self.employee
        )

    def _payload(self, **overrides):
        data = {
            "project": self.project.pk,
            "date": "2024-07-10",
            "hours": "6",
            "description": "Built the thing",
        }
        data.update(overrides)
        return data

    def _post(self, **overrides):
        self.client.force_login(self.employee.user)
        return self.client.post(
            reverse("projects:worklog_create"), self._payload(**overrides)
        )

    def test_submit_worklog_against_assigned_project(self):
        response = self._post()
        self.assertEqual(response.status_code, 302)
        log = WorkLog.objects.get(employee=self.employee)
        self.assertEqual(log.status, WorkLogStatus.SUBMITTED)
        self.assertEqual(log.project, self.project)
        self.assertTrue(
            AuditLog.objects.filter(action="WORKLOG_SUBMITTED").exists()
        )

    def test_hours_optional_defaults_to_zero(self):
        response = self._post(hours="")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(WorkLog.objects.get(employee=self.employee).hours, 0)

    def test_cannot_log_to_unassigned_project(self):
        other = make_project(name="Gemini")
        response = self._post(project=other.pk)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(WorkLog.objects.exists())

    def test_hours_above_max_rejected(self):
        response = self._post(hours="25")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(WorkLog.objects.exists())

    def test_negative_hours_rejected(self):
        response = self._post(hours="-1")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(WorkLog.objects.exists())

    def test_future_date_rejected(self):
        future = (date.today() + timedelta(days=5)).isoformat()
        response = self._post(date=future)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(WorkLog.objects.exists())

    def test_date_before_project_start_rejected(self):
        response = self._post(date="2024-06-30")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(WorkLog.objects.exists())

    def test_duplicate_project_date_rejected(self):
        self._post()
        response = self._post(description="Second")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(WorkLog.objects.count(), 1)

    def test_model_clean_duplicate_detected(self):
        WorkLog.objects.create(
            employee=self.employee,
            project=self.project,
            date=date(2024, 7, 10),
            hours=4,
            description="First",
        )
        duplicate = WorkLog(
            employee=self.employee,
            project=self.project,
            date=date(2024, 7, 10),
            hours=2,
            description="Second",
        )
        with self.assertRaises(ValidationError):
            duplicate.full_clean()

    def test_database_constraint_blocks_duplicate(self):
        WorkLog.objects.create(
            employee=self.employee,
            project=self.project,
            date=date(2024, 7, 11),
            hours=4,
            description="First",
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                WorkLog.objects.create(
                    employee=self.employee,
                    project=self.project,
                    date=date(2024, 7, 11),
                    hours=2,
                    description="Second",
                )

    def test_employee_worklog_list_isolation(self):
        other = make_employee(username="b", employee_id="E002")
        WorkLog.objects.create(
            employee=other, project=self.project, date=date(2024, 7, 12), hours=1
        )
        self.client.force_login(self.employee.user)
        response = self.client.get(reverse("projects:my_worklogs"))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            all(log.employee_id == self.employee.pk for log in response.context["logs"])
        )


class WorkLogEditTests(TestCase):
    def setUp(self):
        self.employee = make_employee()
        self.project = make_project()
        ProjectAssignment.objects.create(
            project=self.project, employee=self.employee
        )
        self.log = WorkLog.objects.create(
            employee=self.employee,
            project=self.project,
            date=date(2024, 7, 10),
            hours=4,
            description="Original",
        )

    def test_edit_own_submitted_log(self):
        self.client.force_login(self.employee.user)
        response = self.client.get(
            reverse("projects:worklog_edit", args=[self.log.pk])
        )
        self.assertEqual(response.status_code, 200)
        response = self.client.post(
            reverse("projects:worklog_edit", args=[self.log.pk]),
            {
                "project": self.project.pk,
                "date": "2024-07-10",
                "hours": "5",
                "description": "Updated",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.log.refresh_from_db()
        self.assertEqual(self.log.description, "Updated")
        self.assertTrue(AuditLog.objects.filter(action="WORKLOG_UPDATED").exists())

    def test_cannot_edit_reviewed_log(self):
        self.log.status = WorkLogStatus.REVIEWED
        self.log.save()
        self.client.force_login(self.employee.user)
        response = self.client.get(
            reverse("projects:worklog_edit", args=[self.log.pk])
        )
        self.assertEqual(response.status_code, 302)
        response = self.client.post(
            reverse("projects:worklog_edit", args=[self.log.pk]),
            {
                "project": self.project.pk,
                "date": "2024-07-10",
                "hours": "9",
                "description": "Hacked",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.log.refresh_from_db()
        self.assertEqual(self.log.description, "Original")
        self.assertEqual(self.log.hours, 4)

    def test_cannot_edit_other_employees_log(self):
        other = make_employee(username="b", employee_id="E002")
        other_project = make_project(name="Gemini")
        other_log = WorkLog.objects.create(
            employee=other,
            project=other_project,
            date=date(2024, 7, 10),
            hours=1,
            description="Theirs",
        )
        self.client.force_login(self.employee.user)
        response = self.client.get(
            reverse("projects:worklog_edit", args=[other_log.pk])
        )
        self.assertEqual(response.status_code, 404)


class WorkLogReviewTests(TestCase):
    def setUp(self):
        self.hr = make_hr()
        self.employee = make_employee()
        self.project = make_project()
        self.log = WorkLog.objects.create(
            employee=self.employee,
            project=self.project,
            date=date(2024, 7, 10),
            hours=5,
            description="Work",
        )

    def test_hr_reviews_with_metadata_and_audit(self):
        self.client.force_login(self.hr)
        response = self.client.post(
            reverse("projects:worklog_review_decision", args=[self.log.pk])
        )
        self.assertEqual(response.status_code, 302)
        self.log.refresh_from_db()
        self.assertEqual(self.log.status, WorkLogStatus.REVIEWED)
        self.assertEqual(self.log.reviewed_by, self.hr)
        self.assertIsNotNone(self.log.reviewed_at)
        self.assertTrue(AuditLog.objects.filter(action="WORKLOG_REVIEWED").exists())

    def test_cannot_review_twice(self):
        self.client.force_login(self.hr)
        self.client.post(
            reverse("projects:worklog_review_decision", args=[self.log.pk])
        )
        second_hr = make_hr(username="hr2")
        self.client.force_login(second_hr)
        self.client.post(
            reverse("projects:worklog_review_decision", args=[self.log.pk])
        )
        self.log.refresh_from_db()
        self.assertEqual(self.log.reviewed_by, self.hr)

    def test_employee_cannot_access_review(self):
        self.client.force_login(self.employee.user)
        self.assertEqual(
            self.client.get(reverse("projects:worklog_review")).status_code, 403
        )
        self.assertEqual(
            self.client.post(
                reverse("projects:worklog_review_decision", args=[self.log.pk])
            ).status_code,
            403,
        )
        self.log.refresh_from_db()
        self.assertEqual(self.log.status, WorkLogStatus.SUBMITTED)

    def test_review_filters_by_project_and_date(self):
        other_project = make_project(name="Gemini")
        WorkLog.objects.create(
            employee=self.employee,
            project=other_project,
            date=date(2024, 7, 11),
            hours=2,
            description="Other",
        )
        self.client.force_login(self.hr)
        response = self.client.get(
            reverse("projects:worklog_review"), {"project": self.project.pk}
        )
        logs = list(response.context["logs"])
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0].project, self.project)

        response = self.client.get(
            reverse("projects:worklog_review"), {"date": "2024-07-11"}
        )
        logs = list(response.context["logs"])
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0].project, other_project)
