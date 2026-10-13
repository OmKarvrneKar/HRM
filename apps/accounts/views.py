from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import PasswordChangeView
from django.urls import reverse_lazy
from django.views.generic import CreateView, ListView

from .forms import BootstrapPasswordChangeForm, HRUserCreateForm
from .mixins import HRRequiredMixin
from .models import User


class ForcePasswordChangeView(LoginRequiredMixin, PasswordChangeView):
    """Password change page. Clears the must_change_password flag on success."""

    template_name = "registration/password_change.html"
    form_class = BootstrapPasswordChangeForm
    success_url = reverse_lazy("core:home")

    def form_valid(self, form):
        response = super().form_valid(form)
        user = self.request.user
        user.must_change_password = False
        user.save(update_fields=["must_change_password"])
        return response


class UserListView(HRRequiredMixin, ListView):
    """HR-only list of all user accounts."""

    model = User
    template_name = "accounts/user_list.html"
    context_object_name = "users"
    ordering = ["role", "username"]

    def get_queryset(self):
        qs = super().get_queryset()
        role = self.request.GET.get("role")
        query = self.request.GET.get("q")
        if role in dict(User.role.field.choices):
            qs = qs.filter(role=role)
        if query:
            qs = qs.filter(username__icontains=query)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["role_choices"] = User.role.field.choices
        ctx["selected_role"] = self.request.GET.get("role", "")
        ctx["query"] = self.request.GET.get("q", "")
        return ctx


class HRUserCreateView(HRRequiredMixin, CreateView):
    """HR-only. Create another HR account with a temporary password."""

    model = User
    form_class = HRUserCreateForm
    template_name = "accounts/user_form.html"
    success_url = reverse_lazy("accounts:user_list")
