from django.shortcuts import get_object_or_404


def get_employee_for(user):
    """Return the Employee record linked to a signed-in user (404 if none)."""
    from apps.employees.models import Employee

    return get_object_or_404(Employee, user=user)
