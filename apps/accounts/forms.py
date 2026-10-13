from django import forms
from django.contrib.auth.forms import (
    AuthenticationForm,
    PasswordChangeForm,
    UserCreationForm,
)

from .models import Role, User


class BootstrapAuthenticationForm(AuthenticationForm):
    """Login form with Bootstrap-friendly widgets."""

    username = forms.CharField(
        widget=forms.TextInput(
            attrs={"class": "form-control", "autofocus": True, "placeholder": "Username"}
        )
    )
    password = forms.CharField(
        widget=forms.PasswordInput(
            attrs={"class": "form-control", "placeholder": "Password"}
        )
    )


class BootstrapPasswordChangeForm(PasswordChangeForm):
    """Password change form with Bootstrap-friendly widgets."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")


class HRUserCreateForm(UserCreationForm):
    """Form used by HR to create another HR account with a temporary password."""

    first_name = forms.CharField(max_length=150, required=False)
    last_name = forms.CharField(max_length=150, required=False)
    email = forms.EmailField(required=False)

    class Meta:
        model = User
        fields = ("username", "first_name", "last_name", "email")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")

    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = Role.HR
        user.must_change_password = True
        if commit:
            user.save()
        return user
