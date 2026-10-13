from django.contrib.auth.decorators import login_required
from django.shortcuts import render


@login_required
def home(request):
    """Route each signed-in user to the dashboard for their role."""
    if request.user.is_hr:
        template = "core/dashboard_hr.html"
    else:
        template = "core/dashboard_employee.html"
    return render(request, template, {})
