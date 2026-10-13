from django.contrib import admin

from .models import Department, EmergencyContact, Employee


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ("name", "created_at")
    search_fields = ("name",)


class EmergencyContactInline(admin.TabularInline):
    model = EmergencyContact
    extra = 0


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = (
        "employee_id",
        "full_name",
        "department",
        "designation",
        "employment_status",
    )
    list_filter = ("employment_status", "department")
    search_fields = ("employee_id", "full_name", "company_email", "personal_email")
    inlines = [EmergencyContactInline]
