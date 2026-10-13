import os

from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse, reverse_lazy
from django.views import View
from django.views.generic import CreateView, DeleteView, ListView

from apps.accounts.mixins import EmployeeRequiredMixin, HRRequiredMixin
from apps.accounts.utils import get_employee_for
from apps.audit.services import log_action

from .forms import HRDocumentForm, LegalCommunicationForm
from .models import (
    CommunicationAudience,
    DocumentVisibility,
    HRDocument,
    LegalCommunication,
)


# --------------------------------------------------------------------------- #
# Secure download (shared by HR and employees)
# --------------------------------------------------------------------------- #
class HRDocumentDownloadView(LoginRequiredMixin, View):
    def get(self, request, pk):
        document = get_object_or_404(HRDocument, pk=pk)
        if not document.is_visible_to(request.user):
            raise PermissionDenied("You are not allowed to access this document.")
        log_action(
            request.user,
            "DOCUMENT_DOWNLOADED",
            document,
            description="Document downloaded.",
        )
        filename = os.path.basename(document.file.name)
        return FileResponse(
            document.file.open("rb"), as_attachment=True, filename=filename
        )


# --------------------------------------------------------------------------- #
# HR views
# --------------------------------------------------------------------------- #
class DocumentListView(HRRequiredMixin, ListView):
    model = HRDocument
    template_name = "documents/document_list.html"
    context_object_name = "documents"

    def get_queryset(self):
        return HRDocument.objects.select_related("employee").all()


class DocumentCreateView(HRRequiredMixin, CreateView):
    model = HRDocument
    form_class = HRDocumentForm
    template_name = "documents/document_form.html"

    def form_valid(self, form):
        form.instance.uploaded_by = self.request.user
        response = super().form_valid(form)
        log_action(
            self.request.user,
            "DOCUMENT_UPLOADED",
            self.object,
            description="HR document uploaded.",
            visibility=self.object.visibility,
        )
        return response

    def get_success_url(self):
        return reverse("documents:list")


class DocumentDeleteView(HRRequiredMixin, DeleteView):
    model = HRDocument
    http_method_names = ["post"]
    success_url = reverse_lazy("documents:list")


class LegalListView(HRRequiredMixin, ListView):
    model = LegalCommunication
    template_name = "documents/legal_list.html"
    context_object_name = "communications"


class LegalCreateView(HRRequiredMixin, CreateView):
    model = LegalCommunication
    form_class = LegalCommunicationForm
    template_name = "documents/legal_form.html"

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        response = super().form_valid(form)
        log_action(
            self.request.user, "LEGAL_COMMUNICATION_CREATED", self.object
        )
        return response

    def get_success_url(self):
        return reverse("documents:legal")


# --------------------------------------------------------------------------- #
# Employee views
# --------------------------------------------------------------------------- #
class MyDocumentsView(EmployeeRequiredMixin, ListView):
    template_name = "documents/my_documents.html"
    context_object_name = "documents"

    def get_queryset(self):
        employee = get_employee_for(self.request.user)
        return HRDocument.objects.filter(
            Q(visibility=DocumentVisibility.ALL_EMPLOYEES)
            | Q(
                visibility=DocumentVisibility.SINGLE_EMPLOYEE,
                employee=employee,
            )
        ).distinct()


class MyCommunicationsView(EmployeeRequiredMixin, ListView):
    template_name = "documents/my_communications.html"
    context_object_name = "communications"

    def get_queryset(self):
        employee = get_employee_for(self.request.user)
        group_ids = list(
            employee.group_memberships.values_list("group_id", flat=True)
        )
        return (
            LegalCommunication.objects.filter(is_active=True)
            .filter(
                Q(audience=CommunicationAudience.ALL_EMPLOYEES)
                | Q(
                    audience=CommunicationAudience.SINGLE_EMPLOYEE,
                    employee=employee,
                )
                | Q(
                    audience=CommunicationAudience.GROUP,
                    group_id__in=group_ids,
                )
            )
            .select_related("attachment")
        )
