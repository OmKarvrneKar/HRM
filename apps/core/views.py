from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from .services import employee_dashboard_context, hr_dashboard_context


@login_required
def home(request):
    """Route each signed-in user to the dashboard for their role."""
    if request.user.is_hr:
        template = "core/dashboard_hr.html"
        context = hr_dashboard_context()
    else:
        template = "core/dashboard_employee.html"
        context = employee_dashboard_context(request.user)
    return render(request, template, context)
