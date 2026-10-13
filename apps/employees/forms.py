from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password

from apps.accounts.models import Role

from .models import Department, EmergencyContact, Employee

User = get_user_model()


class EmployeeCreateForm(forms.ModelForm):
    """HR form that creates the login account and the employee record together.

    The HR user types a temporary password; the employee is forced to change it
    on first login.
    """

    username = forms.CharField(
        max_length=150, help_text="Login username for the employee."
    )
    password1 = forms.CharField(
        label="Temporary password", widget=forms.PasswordInput
    )
    password2 = forms.CharField(
        label="Confirm temporary password", widget=forms.PasswordInput
    )

    class Meta:
        model = Employee
        fields = [
            "employee_id",
            "full_name",
            "photo",
            "phone",
            "address",
            "company_email",
            "personal_email",
            "department",
            "designation",
            "joining_date",
            "reporting_manager",
            "employment_status",
        ]
        widgets = {"joining_date": forms.DateInput(attrs={"type": "date"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            css = "form-control"
            if isinstance(field.widget, (forms.Select,)):
                css = "form-select"
            elif isinstance(field.widget, forms.CheckboxInput):
                css = "form-check-input"
            field.widget.attrs["class"] = css

    def clean_username(self):
        username = self.cleaned_data["username"]
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError("A user with that username already exists.")
        return username

    def clean(self):
        cleaned = super().clean()
        password1 = cleaned.get("password1")
        password2 = cleaned.get("password2")
        if password1 and password2 and password1 != password2:
            self.add_error("password2", "The two passwords do not match.")
        elif password1:
            probe = User(username=cleaned.get("username", ""))
            try:
                validate_password(password1, probe)
            except forms.ValidationError as exc:
                self.add_error("password1", exc)
        return cleaned

    def save(self, commit=True):
        employee = super().save(commit=False)
        user = User(
            username=self.cleaned_data["username"],
            role=Role.EMPLOYEE,
            must_change_password=True,
            email=self.cleaned_data.get("company_email") or "",
        )
        name = (self.cleaned_data.get("full_name") or "").strip()
        first, _, last = name.partition(" ")
        user.first_name = first
        user.last_name = last
        user.set_password(self.cleaned_data["password1"])
        if commit:
            user.save()
            employee.user = user
            employee.save()
        return employee


class EmployeeUpdateForm(forms.ModelForm):
    """HR edit form for employee details (does not touch login credentials)."""

    class Meta:
        model = Employee
        fields = [
            "employee_id",
            "full_name",
            "photo",
            "phone",
            "address",
            "company_email",
            "personal_email",
            "department",
            "designation",
            "joining_date",
            "reporting_manager",
            "employment_status",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            css = "form-select" if isinstance(field.widget, forms.Select) else "form-control"
            field.widget.attrs["class"] = css
        if self.instance and self.instance.pk:
            self.fields["reporting_manager"].queryset = Employee.objects.exclude(
                pk=self.instance.pk
            )
        self.fields["reporting_manager"].required = False


class DepartmentForm(forms.ModelForm):
    class Meta:
        model = Department
        fields = ["name", "description"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = "form-control"


class EmergencyContactForm(forms.ModelForm):
    class Meta:
        model = EmergencyContact
        fields = ["name", "relationship", "phone", "email"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = "form-control"


class EmployeeStatusForm(forms.ModelForm):
    class Meta:
        model = Employee
        fields = ["employment_status"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["employment_status"].widget.attrs["class"] = "form-select"
