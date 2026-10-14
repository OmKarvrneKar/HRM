from django.contrib import messages
from django.db import IntegrityError
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, ListView, UpdateView

from apps.accounts.mixins import EmployeeRequiredMixin, HRRequiredMixin
from apps.accounts.utils import get_employee_for
from apps.audit.services import log_action
from apps.notifications.services import notify

from .forms import (
    AttendanceRecordForm,
    CorrectionDecisionForm,
    CorrectionRequestForm,
)
from .models import (
    AttendanceCorrectionRequest,
    AttendanceRecord,
    AttendanceSource,
    AttendanceStatus,
    CorrectionStatus,
)


# --------------------------------------------------------------------------- #
# HR views
# --------------------------------------------------------------------------- #
class AttendanceListView(HRRequiredMixin, ListView):
    template_name = "attendance/attendance_list.html"
    context_object_name = "records"

    def get_queryset(self):
        qs = AttendanceRecord.objects.select_related("employee")
        date = self.request.GET.get("date") or timezone.localdate().isoformat()
        self.selected_date = date
        qs = qs.filter(date=date)
        employee_q = self.request.GET.get("q")
        status = self.request.GET.get("status")
        if employee_q:
            qs = qs.filter(
                employee__full_name__icontains=employee_q
            ) | qs.filter(employee__employee_id__icontains=employee_q)
        if status in dict(AttendanceStatus.choices):
            qs = qs.filter(status=status)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["selected_date"] = self.selected_date
        ctx["status_choices"] = AttendanceStatus.choices
        ctx["selected_status"] = self.request.GET.get("status", "")
        ctx["query"] = self.request.GET.get("q", "")
        return ctx


class AttendanceCreateView(HRRequiredMixin, CreateView):
    model = AttendanceRecord
    form_class = AttendanceRecordForm
    template_name = "attendance/attendance_form.html"

    def form_valid(self, form):
        form.instance.source = AttendanceSource.HR
        form.instance.created_by = self.request.user
        response = super().form_valid(form)
        log_action(
            self.request.user,
            "ATTENDANCE_MANUAL_ENTRY",
            self.object,
            description="HR entered attendance manually.",
            status=self.object.status,
            date=str(self.object.date),
        )
        return response

    def get_success_url(self):
        return reverse("attendance:list")


class AttendanceUpdateView(HRRequiredMixin, UpdateView):
    model = AttendanceRecord
    form_class = AttendanceRecordForm
    template_name = "attendance/attendance_form.html"

    def get_success_url(self):
        return reverse("attendance:list")

    def form_valid(self, form):
        form.instance.source = AttendanceSource.HR
        form.instance.created_by = self.request.user
        response = super().form_valid(form)
        log_action(
            self.request.user,
            "ATTENDANCE_UPDATED",
            self.object,
            description="HR updated an attendance record.",
        )
        return response


class CorrectionReviewListView(HRRequiredMixin, ListView):
    template_name = "attendance/correction_review.html"
    context_object_name = "requests"

    def get_queryset(self):
        status = self.request.GET.get("status", CorrectionStatus.PENDING)
        qs = AttendanceCorrectionRequest.objects.select_related("employee")
        if status in dict(CorrectionStatus.choices):
            qs = qs.filter(status=status)
        self.selected_status = status
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["status_choices"] = CorrectionStatus.choices
        ctx["selected_status"] = self.selected_status
        return ctx


class CorrectionDecisionView(HRRequiredMixin, View):
    def post(self, request, pk):
        correction = get_object_or_404(AttendanceCorrectionRequest, pk=pk)
        form = CorrectionDecisionForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Invalid decision.")
            return redirect("attendance:corrections")

        decision = form.cleaned_data["decision"]
        correction.status = decision
        correction.reviewed_by = request.user
        correction.reviewed_at = timezone.now()
        correction.decision_note = form.cleaned_data.get("note", "")

        if decision == CorrectionStatus.APPROVED:
            record, _ = AttendanceRecord.objects.get_or_create(
                employee=correction.employee, date=correction.date
            )
            if correction.requested_check_in:
                record.check_in = correction.requested_check_in
            if correction.requested_check_out:
                record.check_out = correction.requested_check_out
            record.source = AttendanceSource.HR
            record.created_by = request.user
            record.save()
            correction.attendance = record
        correction.save()

        log_action(
            request.user,
            "ATTENDANCE_CORRECTION_DECISION",
            correction,
            description=f"Correction {decision.lower()} by HR.",
            decision=decision,
            note=correction.decision_note,
        )
        notify(
            correction.employee.user,
            f"Attendance correction {decision.lower()}",
            f"Your correction request for {correction.date} was {decision.lower()}.",
            reverse("attendance:my_corrections"),
        )
        messages.success(request, f"Correction {decision.lower()}.")
        return redirect("attendance:corrections")


# --------------------------------------------------------------------------- #
# Employee views
# --------------------------------------------------------------------------- #
class MyAttendanceView(EmployeeRequiredMixin, ListView):
    template_name = "attendance/my_attendance.html"
    context_object_name = "records"

    def get_queryset(self):
        self.employee = get_employee_for(self.request.user)
        return AttendanceRecord.objects.filter(employee=self.employee)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["employee"] = self.employee
        ctx["today"] = timezone.localdate()
        ctx["today_record"] = AttendanceRecord.objects.filter(
            employee=self.employee, date=timezone.localdate()
        ).first()
        return ctx


class CheckInView(EmployeeRequiredMixin, View):
    def post(self, request):
        employee = get_employee_for(request.user)
        today = timezone.localdate()
        try:
            record, created = AttendanceRecord.objects.get_or_create(
                employee=employee,
                date=today,
                defaults={
                    "check_in": timezone.localtime().time(),
                    "status": AttendanceStatus.PRESENT,
                    "source": AttendanceSource.SELF,
                },
            )
        except IntegrityError:
            messages.info(request, "Already checked in today.")
            return redirect("attendance:my")
        if not created and record.check_in is None:
            record.check_in = timezone.localtime().time()
            record.source = AttendanceSource.SELF
            record.save(update_fields=["check_in", "source"])
            created = True
        if created:
            log_action(request.user, "ATTENDANCE_CHECK_IN", record)
            messages.success(request, "Checked in.")
        else:
            messages.info(request, "Already checked in today.")
        return redirect("attendance:my")


class CheckOutView(EmployeeRequiredMixin, View):
    def post(self, request):
        employee = get_employee_for(request.user)
        today = timezone.localdate()
        record = AttendanceRecord.objects.filter(
            employee=employee, date=today
        ).first()
        if record is None or record.check_in is None:
            messages.error(request, "You must check in before checking out.")
            return redirect("attendance:my")
        if record.check_out is not None:
            messages.info(request, "You have already checked out today.")
            return redirect("attendance:my")
        now = timezone.localtime().time()
        if now < record.check_in:
            messages.error(request, "Check-out cannot be earlier than check-in.")
            return redirect("attendance:my")
        record.check_out = now
        record.save(update_fields=["check_out"])
        log_action(request.user, "ATTENDANCE_CHECK_OUT", record)
        messages.success(request, "Checked out.")
        return redirect("attendance:my")


class MyCorrectionsView(EmployeeRequiredMixin, ListView):
    template_name = "attendance/my_corrections.html"
    context_object_name = "requests"

    def get_queryset(self):
        employee = get_employee_for(self.request.user)
        return AttendanceCorrectionRequest.objects.filter(employee=employee)


class CorrectionRequestCreateView(EmployeeRequiredMixin, CreateView):
    model = AttendanceCorrectionRequest
    form_class = CorrectionRequestForm
    template_name = "attendance/correction_form.html"

    def form_valid(self, form):
        employee = get_employee_for(self.request.user)
        date = form.instance.date
        if AttendanceCorrectionRequest.objects.filter(
            employee=employee, date=date, status=CorrectionStatus.PENDING
        ).exists():
            messages.error(
                self.request,
                "You already have a pending correction request for that date.",
            )
            return redirect("attendance:my_corrections")
        form.instance.employee = employee
        form.instance.attendance = AttendanceRecord.objects.filter(
            employee=employee, date=date
        ).first()
        response = super().form_valid(form)
        log_action(self.request.user, "ATTENDANCE_CORRECTION_REQUESTED", self.object)
        messages.success(
            self.request, "Correction request submitted for HR review."
        )
        return response

    def get_success_url(self):
        return reverse("attendance:my_corrections")
