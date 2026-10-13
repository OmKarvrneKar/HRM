from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from apps.accounts.mixins import EmployeeRequiredMixin, HRRequiredMixin
from apps.accounts.utils import get_employee_for
from apps.audit.services import log_action
from apps.employees.models import Employee

from .forms import (
    GroupMembershipForm,
    ProjectAssignmentForm,
    ProjectForm,
    TeamGroupForm,
    WorkLogForm,
)
from .models import (
    GroupMembership,
    Project,
    ProjectAssignment,
    TeamGroup,
    WorkLog,
    WorkLogStatus,
)


# --------------------------------------------------------------------------- #
# HR: Projects
# --------------------------------------------------------------------------- #
class ProjectListView(HRRequiredMixin, ListView):
    model = Project
    template_name = "projects/project_list.html"
    context_object_name = "projects"


class ProjectCreateView(HRRequiredMixin, CreateView):
    model = Project
    form_class = ProjectForm
    template_name = "projects/project_form.html"

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        response = super().form_valid(form)
        log_action(self.request.user, "PROJECT_CREATED", self.object)
        return response

    def get_success_url(self):
        return reverse("projects:detail", kwargs={"pk": self.object.pk})


class ProjectUpdateView(HRRequiredMixin, UpdateView):
    model = Project
    form_class = ProjectForm
    template_name = "projects/project_form.html"

    def get_success_url(self):
        return reverse("projects:detail", kwargs={"pk": self.object.pk})


class ProjectDetailView(HRRequiredMixin, DetailView):
    model = Project
    template_name = "projects/project_detail.html"
    context_object_name = "project"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["assignment_form"] = ProjectAssignmentForm(project=self.object)
        ctx["assignments"] = self.object.assignments.select_related("employee")
        ctx["work_logs"] = self.object.work_logs.select_related("employee")[:20]
        return ctx


class ProjectAssignmentCreateView(HRRequiredMixin, CreateView):
    model = ProjectAssignment
    form_class = ProjectAssignmentForm
    http_method_names = ["post"]

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["project"] = get_object_or_404(Project, pk=self.kwargs["pk"])
        return kwargs

    def form_valid(self, form):
        form.instance.project = get_object_or_404(Project, pk=self.kwargs["pk"])
        response = super().form_valid(form)
        log_action(self.request.user, "PROJECT_ASSIGNMENT_ADDED", self.object)
        return response

    def get_success_url(self):
        return reverse("projects:detail", kwargs={"pk": self.kwargs["pk"]})


class ProjectAssignmentDeleteView(HRRequiredMixin, DeleteView):
    model = ProjectAssignment
    http_method_names = ["post"]

    def get_success_url(self):
        return reverse("projects:detail", kwargs={"pk": self.object.project_id})


# --------------------------------------------------------------------------- #
# HR: Groups
# --------------------------------------------------------------------------- #
class GroupListView(HRRequiredMixin, ListView):
    model = TeamGroup
    template_name = "projects/group_list.html"
    context_object_name = "groups"


class GroupCreateView(HRRequiredMixin, CreateView):
    model = TeamGroup
    form_class = TeamGroupForm
    template_name = "projects/group_form.html"

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        response = super().form_valid(form)
        log_action(self.request.user, "GROUP_CREATED", self.object)
        return response

    def get_success_url(self):
        return reverse("projects:group_detail", kwargs={"pk": self.object.pk})


class GroupDetailView(HRRequiredMixin, DetailView):
    model = TeamGroup
    template_name = "projects/group_detail.html"
    context_object_name = "group"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["membership_form"] = GroupMembershipForm(group=self.object)
        ctx["memberships"] = self.object.memberships.select_related("employee")
        return ctx


class GroupMembershipCreateView(HRRequiredMixin, CreateView):
    model = GroupMembership
    form_class = GroupMembershipForm
    http_method_names = ["post"]

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["group"] = get_object_or_404(TeamGroup, pk=self.kwargs["pk"])
        return kwargs

    def form_valid(self, form):
        form.instance.group = get_object_or_404(TeamGroup, pk=self.kwargs["pk"])
        response = super().form_valid(form)
        log_action(self.request.user, "GROUP_MEMBER_ADDED", self.object)
        return response

    def get_success_url(self):
        return reverse("projects:group_detail", kwargs={"pk": self.kwargs["pk"]})


class GroupMembershipDeleteView(HRRequiredMixin, DeleteView):
    model = GroupMembership
    http_method_names = ["post"]

    def get_success_url(self):
        return reverse("projects:group_detail", kwargs={"pk": self.object.group_id})


# --------------------------------------------------------------------------- #
# HR: Work log review
# --------------------------------------------------------------------------- #
class WorkLogReviewListView(HRRequiredMixin, ListView):
    template_name = "projects/worklog_review.html"
    context_object_name = "logs"

    def get_queryset(self):
        return WorkLog.objects.select_related("employee", "project")


class WorkLogReviewDecisionView(HRRequiredMixin, View):
    def post(self, request, pk):
        work_log = get_object_or_404(WorkLog, pk=pk)
        work_log.status = WorkLogStatus.REVIEWED
        work_log.reviewed_by = request.user
        work_log.reviewed_at = timezone.now()
        work_log.save()
        log_action(request.user, "WORKLOG_REVIEWED", work_log)
        messages.success(request, "Work log marked as reviewed.")
        return redirect("projects:worklog_review")


# --------------------------------------------------------------------------- #
# Employee
# --------------------------------------------------------------------------- #
class MyProjectsView(EmployeeRequiredMixin, ListView):
    template_name = "projects/my_projects.html"
    context_object_name = "assignments"

    def get_queryset(self):
        self.employee = get_employee_for(self.request.user)
        return ProjectAssignment.objects.filter(employee=self.employee).select_related(
            "project"
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["employee"] = self.employee
        return ctx


class MyGroupsView(EmployeeRequiredMixin, ListView):
    template_name = "projects/my_groups.html"
    context_object_name = "memberships"

    def get_queryset(self):
        self.employee = get_employee_for(self.request.user)
        return GroupMembership.objects.filter(employee=self.employee).select_related(
            "group"
        )


class MyWorkLogsView(EmployeeRequiredMixin, ListView):
    template_name = "projects/my_worklogs.html"
    context_object_name = "logs"

    def get_queryset(self):
        employee = get_employee_for(self.request.user)
        return WorkLog.objects.filter(employee=employee).select_related("project")


class WorkLogCreateView(EmployeeRequiredMixin, CreateView):
    model = WorkLog
    form_class = WorkLogForm
    template_name = "projects/worklog_form.html"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["employee"] = get_employee_for(self.request.user)
        return kwargs

    def form_valid(self, form):
        form.instance.employee = get_employee_for(self.request.user)
        response = super().form_valid(form)
        log_action(self.request.user, "WORKLOG_SUBMITTED", self.object)
        messages.success(self.request, "Work log submitted.")
        return response

    def get_success_url(self):
        return reverse("projects:my_worklogs")
