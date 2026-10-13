from django.contrib import admin

from .models import AttendanceCorrectionRequest, AttendanceRecord


@admin.register(AttendanceRecord)
class AttendanceRecordAdmin(admin.ModelAdmin):
    list_display = ("employee", "date", "check_in", "check_out", "status", "source")
    list_filter = ("status", "source", "date")
    search_fields = ("employee__employee_id", "employee__full_name")
    date_hierarchy = "date"


@admin.register(AttendanceCorrectionRequest)
class AttendanceCorrectionRequestAdmin(admin.ModelAdmin):
    list_display = ("employee", "date", "status", "reviewed_by", "created_at")
    list_filter = ("status",)
    search_fields = ("employee__employee_id", "employee__full_name")
