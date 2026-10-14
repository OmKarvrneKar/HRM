"""Role-aware dashboard data.

Kept deliberately small: each function returns a plain dict of already-counted
values so the templates stay logic-free. No new models are introduced.
"""
from django.utils import timezone

from apps.attendance.models import (
    AttendanceCorrectionRequest,
    AttendanceRecord,
    CorrectionStatus,
)
from apps.employees.models import Employee
from apps.leave.models import LeaveRequest, LeaveStatus
from apps.notifications.models import Audience, CalendarEvent
from apps.projects.models import Project, ProjectAssignment, WorkLog, WorkLogStatus


def _upcoming_events(audiences, limit=5):
    return list(
        CalendarEvent.objects.filter(
            event_date__gte=timezone.localdate(),
            audience__in=audiences,
        )
        .select_related("project")
        .order_by("event_date", "start_time")[:limit]
    )


def hr_dashboard_context():
    today = timezone.localdate()
    return {
        "employee_count": Employee.objects.count(),
        "pending_leave": LeaveRequest.objects.filter(
            status=LeaveStatus.PENDING
        ).count(),
        "pending_corrections": AttendanceCorrectionRequest.objects.filter(
            status=CorrectionStatus.PENDING
        ).count(),
        "pending_worklogs": WorkLog.objects.filter(
            status=WorkLogStatus.SUBMITTED
        ).count(),
        "active_projects": Project.objects.filter(is_archived=False)
        .exclude(status="COMPLETED")
        .count(),
        "upcoming_events": _upcoming_events(
            [Audience.ALL, Audience.HR], limit=5
        ),
        "today": today,
    }


def employee_dashboard_context(user):
    today = timezone.localdate()
    employee = getattr(user, "employee", None)
    context = {
        "employee": employee,
        "today": today,
        "unread_notifications": user.notifications.filter(
            is_read=False
        ).count(),
        "upcoming_events": _upcoming_events(
            [Audience.ALL, Audience.EMPLOYEE], limit=5
        ),
        "today_record": None,
        "my_pending_leave": 0,
        "my_projects": 0,
    }
    if employee is not None:
        context["today_record"] = AttendanceRecord.objects.filter(
            employee=employee, date=today
        ).first()
        context["my_pending_leave"] = LeaveRequest.objects.filter(
            employee=employee, status=LeaveStatus.PENDING
        ).count()
        context["my_projects"] = ProjectAssignment.objects.filter(
            employee=employee, project__is_archived=False
        ).count()
    return context
