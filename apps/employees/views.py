from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.urls import reverse, reverse_lazy
from django.views.generic import (
    CreateView,
    DeleteView,
    DetailView,
    ListView,
    UpdateView,
)

from apps.accounts.mixins import HRRequiredMixin
from apps.audit.services import log_action

from .forms import (
    DepartmentForm,
    EmergencyContactForm,
    EmployeeCreateForm,
    EmployeeStatusForm,
    EmployeeUpdateForm,
)
from .models import Department, EmergencyContact, Employee, EmploymentStatus


class EmployeeListView(HRRequiredMixin, ListView):
    """HR: search, filter and page through employee records."""

    model = Employee
    template_name = "employees/employee_list.html"
    context_object_name = "employees"
    paginate_by = 20

    def get_queryset(self):
        qs = Employee.objects.select_related("department", "reporting_manager")
        query = self.request.GET.get("q", "").strip()
        department = self.request.GET.get("department", "")
        status = self.request.GET.get("status", "")
        if query:
            qs = qs.filter(
                Q(full_name__icontains=query)
                | Q(employee_id__icontains=query)
                | Q(company_email__icontains=query)
                | Q(personal_email__icontains=query)
            )
        if department.isdigit():
            qs = qs.filter(department_id=department)
        if status in dict(EmploymentStatus.choices):
            qs = qs.filter(employment_status=status)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["departments"] = Department.objects.all()
        ctx["status_choices"] = EmploymentStatus.choices
        ctx["query"] = self.request.GET.get("q", "")
        ctx["selected_department"] = self.request.GET.get("department", "")
        ctx["selected_status"] = self.request.GET.get("status", "")
        return ctx


class EmployeeDetailView(HRRequiredMixin, DetailView):
    model = Employee
    template_name = "employees/employee_detail.html"
    context_object_name = "employee"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["contact_form"] = EmergencyContactForm()
        ctx["status_form"] = EmployeeStatusForm(instance=self.object)
        return ctx


class EmployeeCreateView(HRRequiredMixin, CreateView):
    model = Employee
    form_class = EmployeeCreateForm
    template_name = "employees/employee_form.html"

    def form_valid(self, form):
        response = super().form_valid(form)
        log_action(
            self.request.user,
            "EMPLOYEE_CREATED",
            self.object,
            description="HR created an employee record.",
        )
        return response

    def get_success_url(self):
        return reverse("employees:detail", kwargs={"pk": self.object.pk})


class EmployeeUpdateView(HRRequiredMixin, UpdateView):
    model = Employee
    form_class = EmployeeUpdateForm
    template_name = "employees/employee_form.html"

    def form_valid(self, form):
        response = super().form_valid(form)
        log_action(
            self.request.user,
            "EMPLOYEE_UPDATED",
            self.object,
            description="HR updated an employee record.",
        )
        return response

    def get_success_url(self):
        return reverse("employees:detail", kwargs={"pk": self.object.pk})


class EmployeeStatusUpdateView(HRRequiredMixin, UpdateView):
    model = Employee
    form_class = EmployeeStatusForm
    http_method_names = ["post"]

    def form_valid(self, form):
        response = super().form_valid(form)
        log_action(
            self.request.user,
            "EMPLOYEE_STATUS_CHANGED",
            self.object,
            description="HR changed employment status.",
            status=self.object.employment_status,
        )
        return response

    def get_success_url(self):
        return reverse("employees:detail", kwargs={"pk": self.object.pk})


class EmergencyContactCreateView(HRRequiredMixin, CreateView):
    model = EmergencyContact
    form_class = EmergencyContactForm
    http_method_names = ["post"]

    def form_valid(self, form):
        self.employee = Employee.objects.get(pk=self.kwargs["pk"])
        form.instance.employee = self.employee
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("employees:detail", kwargs={"pk": self.kwargs["pk"]})


class EmergencyContactDeleteView(HRRequiredMixin, DeleteView):
    model = EmergencyContact
    http_method_names = ["post"]

    def get_success_url(self):
        return reverse(
            "employees:detail", kwargs={"pk": self.object.employee_id}
        )


class DepartmentListView(HRRequiredMixin, ListView):
    model = Department
    template_name = "employees/department_list.html"
    context_object_name = "departments"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.setdefault("form", DepartmentForm())
        return ctx


class DepartmentCreateView(HRRequiredMixin, CreateView):
    model = Department
    form_class = DepartmentForm
    http_method_names = ["post"]
    success_url = reverse_lazy("employees:departments")


class MyProfileView(DetailView):
    """Employee self-service profile. HR has no employee record."""

    template_name = "employees/my_profile.html"
    context_object_name = "employee"

    def get(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        if not getattr(request.user, "is_employee", False):
            raise PermissionDenied("Only employees have a personal profile.")
        self.object = get_object_or_404(Employee, user=request.user)
        context = self.get_context_data(object=self.object)
        return self.render_to_response(context)
