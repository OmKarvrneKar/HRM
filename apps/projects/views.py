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

    def get_queryset(self):
        self.show_archived = self.request.GET.get("archived") == "1"
        return Project.objects.filter(is_archived=self.show_archived)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["show_archived"] = self.show_archived
        return ctx


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

    def form_valid(self, form):
        response = super().form_valid(form)
        log_action(
            self.request.user,
            "PROJECT_UPDATED",
            self.object,
            description=f"Project '{self.object.name}' updated.",
            status=self.object.status,
        )
        messages.success(self.request, "Project updated.")
        return response

    def get_success_url(self):
        return reverse("projects:detail", kwargs={"pk": self.object.pk})


class ProjectArchiveView(HRRequiredMixin, View):
    """Toggle a project's archived flag (HR only)."""

    def post(self, request, pk):
        project = get_object_or_404(Project, pk=pk)
        project.is_archived = not project.is_archived
        project.save(update_fields=["is_archived"])
        action = "PROJECT_ARCHIVED" if project.is_archived else "PROJECT_UNARCHIVED"
        log_action(
            request.user,
            action,
            project,
            description=f"Project '{project.name}' "
            f"{'archived' if project.is_archived else 'restored'}.",
        )
        messages.success(
            request,
            f"Project {'archived' if project.is_archived else 'restored'}.",
        )
        return redirect("projects:detail", pk=project.pk)


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

    def form_invalid(self, form):
        messages.error(self.request, "Could not assign employee.")
        return redirect("projects:detail", pk=self.kwargs["pk"])

    def get_success_url(self):
        return reverse("projects:detail", kwargs={"pk": self.kwargs["pk"]})


class ProjectAssignmentDeleteView(HRRequiredMixin, DeleteView):
    model = ProjectAssignment
    http_method_names = ["post"]

    def form_valid(self, form):
        log_action(
            self.request.user,
            "PROJECT_ASSIGNMENT_REMOVED",
            self.get_object(),
            description="Employee removed from project.",
        )
        return super().form_valid(form)

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
        messages.success(self.request, "Group created.")
        return response

    def get_success_url(self):
        return reverse("projects:group_detail", kwargs={"pk": self.object.pk})


class GroupUpdateView(HRRequiredMixin, UpdateView):
    model = TeamGroup
    form_class = TeamGroupForm
    template_name = "projects/group_form.html"

    def form_valid(self, form):
        response = super().form_valid(form)
        log_action(
            self.request.user,
            "GROUP_UPDATED",
            self.object,
            description=f"Group '{self.object.name}' updated.",
        )
        messages.success(self.request, "Group updated.")
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

    def form_invalid(self, form):
        messages.error(self.request, "Could not add member.")
        return redirect("projects:group_detail", pk=self.kwargs["pk"])

    def get_success_url(self):
        return reverse("projects:group_detail", kwargs={"pk": self.kwargs["pk"]})


class GroupMembershipDeleteView(HRRequiredMixin, DeleteView):
    model = GroupMembership
    http_method_names = ["post"]

    def form_valid(self, form):
        log_action(
            self.request.user,
            "GROUP_MEMBER_REMOVED",
            self.get_object(),
            description="Employee removed from group.",
        )
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("projects:group_detail", kwargs={"pk": self.object.group_id})


# --------------------------------------------------------------------------- #
# HR: Work log review
# --------------------------------------------------------------------------- #
class WorkLogReviewListView(HRRequiredMixin, ListView):
    template_name = "projects/worklog_review.html"
    context_object_name = "logs"

    def get_queryset(self):
        qs = WorkLog.objects.select_related("employee", "project")
        employee_id = self.request.GET.get("employee")
        project_id = self.request.GET.get("project")
        date_value = self.request.GET.get("date")
        status = self.request.GET.get("status")
        if employee_id:
            qs = qs.filter(employee_id=employee_id)
        if project_id:
            qs = qs.filter(project_id=project_id)
        if date_value:
            qs = qs.filter(date=date_value)
        if status in dict(WorkLogStatus.choices):
            qs = qs.filter(status=status)
        self.filters = {
            "employee": employee_id or "",
            "project": project_id or "",
            "date": date_value or "",
            "status": status or "",
        }
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["employees"] = Employee.objects.order_by("employee_id")
        ctx["projects"] = Project.objects.order_by("name")
        ctx["status_choices"] = WorkLogStatus.choices
        ctx["filters"] = self.filters
        return ctx


class WorkLogReviewDecisionView(HRRequiredMixin, View):
    def post(self, request, pk):
        work_log = get_object_or_404(WorkLog, pk=pk)
        if work_log.status == WorkLogStatus.REVIEWED:
            messages.info(request, "This work log is already reviewed.")
            return redirect("projects:worklog_review")
        work_log.status = WorkLogStatus.REVIEWED
        work_log.reviewed_by = request.user
        work_log.reviewed_at = timezone.now()
        work_log.save(update_fields=["status", "reviewed_by", "reviewed_at"])
        log_action(
            request.user,
            "WORKLOG_REVIEWED",
            work_log,
            description="Work log marked as reviewed.",
            employee_id=work_log.employee_id,
            date=str(work_log.date),
        )
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


class WorkLogUpdateView(EmployeeRequiredMixin, UpdateView):
    """Employees may edit their own logs while still SUBMITTED (unlocked)."""

    model = WorkLog
    form_class = WorkLogForm
    template_name = "projects/worklog_form.html"

    def get_queryset(self):
        return WorkLog.objects.filter(employee=get_employee_for(self.request.user))

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return super().dispatch(request, *args, **kwargs)
        self.object = self.get_object()
        if self.object.is_locked:
            messages.error(request, "Reviewed work logs cannot be edited.")
            return redirect("projects:my_worklogs")
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        response = super().form_valid(form)
        log_action(self.request.user, "WORKLOG_UPDATED", self.object)
        messages.success(self.request, "Work log updated.")
        return response

    def get_success_url(self):
        return reverse("projects:my_worklogs")
