"""Role-based access mixins and decorators. Enforced server-side, not in the UI."""
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin


class HRRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Allow access only to signed-in HR users."""

    def test_func(self):
        return getattr(self.request.user, "is_hr", False)


class EmployeeRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Allow access only to signed-in Employee users."""

    def test_func(self):
        return getattr(self.request.user, "is_employee", False)
