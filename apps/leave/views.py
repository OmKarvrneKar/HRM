from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, ListView

from apps.accounts.mixins import EmployeeRequiredMixin, HRRequiredMixin
from apps.accounts.utils import get_employee_for
from apps.audit.services import log_action

from .forms import LeaveDecisionForm, LeaveRequestForm, LeaveTypeForm
from .models import LeaveRequest, LeaveStatus, LeaveType


# --------------------------------------------------------------------------- #
# HR views
# --------------------------------------------------------------------------- #
class LeaveTypeListView(HRRequiredMixin, ListView):
    model = LeaveType
    template_name = "leave/leave_type_list.html"
    context_object_name = "leave_types"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.setdefault("form", LeaveTypeForm())
        return ctx


class LeaveTypeCreateView(HRRequiredMixin, CreateView):
    model = LeaveType
    form_class = LeaveTypeForm
    http_method_names = ["post"]
    success_url = reverse_lazy("leave:types")


class LeaveRequestListView(HRRequiredMixin, ListView):
    template_name = "leave/leave_request_list.html"
    context_object_name = "requests"

    def get_queryset(self):
        status = self.request.GET.get("status", LeaveStatus.PENDING)
        qs = LeaveRequest.objects.select_related("employee", "leave_type")
        if status in dict(LeaveStatus.choices):
            qs = qs.filter(status=status)
        self.selected_status = status
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["status_choices"] = LeaveStatus.choices
        ctx["selected_status"] = self.selected_status
        return ctx


class LeaveDecisionView(HRRequiredMixin, View):
    def post(self, request, pk):
        leave_request = get_object_or_404(LeaveRequest, pk=pk)
        form = LeaveDecisionForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Invalid decision.")
            return redirect("leave:requests")

        leave_request.status = form.cleaned_data["decision"]
        leave_request.decision_note = form.cleaned_data["note"]
        leave_request.reviewed_by = request.user
        leave_request.reviewed_at = timezone.now()
        leave_request.save()

        log_action(
            request.user,
            "LEAVE_DECISION",
            leave_request,
            description=f"Leave {leave_request.status.lower()} by HR.",
            status=leave_request.status,
        )
        messages.success(request, f"Leave request {leave_request.status.lower()}.")
        return redirect("leave:requests")


# --------------------------------------------------------------------------- #
# Employee views
# --------------------------------------------------------------------------- #
class MyLeaveView(EmployeeRequiredMixin, ListView):
    template_name = "leave/my_leave.html"
    context_object_name = "requests"

    def get_queryset(self):
        self.employee = get_employee_for(self.request.user)
        return LeaveRequest.objects.filter(employee=self.employee).select_related(
            "leave_type"
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["employee"] = self.employee
        return ctx


class LeaveRequestCreateView(EmployeeRequiredMixin, CreateView):
    model = LeaveRequest
    form_class = LeaveRequestForm
    template_name = "leave/leave_form.html"

    def form_valid(self, form):
        form.instance.employee = get_employee_for(self.request.user)
        response = super().form_valid(form)
        log_action(self.request.user, "LEAVE_REQUESTED", self.object)
        messages.success(self.request, "Leave request submitted.")
        return response

    def get_success_url(self):
        return reverse("leave:my")
