from django.contrib import admin

from .models import (
    GroupMembership,
    Project,
    ProjectAssignment,
    TeamGroup,
    WorkLog,
)


class ProjectAssignmentInline(admin.TabularInline):
    model = ProjectAssignment
    extra = 0


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("name", "status", "start_date", "end_date")
    list_filter = ("status",)
    search_fields = ("name",)
    inlines = [ProjectAssignmentInline]


class GroupMembershipInline(admin.TabularInline):
    model = GroupMembership
    extra = 0


@admin.register(TeamGroup)
class TeamGroupAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)
    inlines = [GroupMembershipInline]


@admin.register(WorkLog)
class WorkLogAdmin(admin.ModelAdmin):
    list_display = ("employee", "date", "project", "hours", "status")
    list_filter = ("status", "project")
    search_fields = ("employee__employee_id", "employee__full_name")
