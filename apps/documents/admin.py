from django.contrib import admin

from .models import HRDocument, LegalCommunication


@admin.register(HRDocument)
class HRDocumentAdmin(admin.ModelAdmin):
    list_display = ("title", "document_type", "employee", "visibility", "uploaded_at")
    list_filter = ("document_type", "visibility")
    search_fields = ("title", "employee__employee_id", "employee__full_name")


@admin.register(LegalCommunication)
class LegalCommunicationAdmin(admin.ModelAdmin):
    list_display = ("title", "audience", "employee", "group", "is_active", "created_at")
    list_filter = ("audience", "is_active")
    search_fields = ("title", "body")
