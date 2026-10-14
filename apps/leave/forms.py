from django import forms

from .models import LeaveRequest, LeaveType


class LeaveTypeForm(forms.ModelForm):
    class Meta:
        model = LeaveType
        fields = ["name", "description", "is_active"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            field.widget.attrs["class"] = (
                "form-check-input" if name == "is_active" else "form-control"
            )

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        duplicates = LeaveType.objects.filter(name__iexact=name)
        if self.instance.pk:
            duplicates = duplicates.exclude(pk=self.instance.pk)
        if duplicates.exists():
            raise forms.ValidationError("A leave type with this name already exists.")
        return name


class LeaveRequestForm(forms.ModelForm):
    class Meta:
        model = LeaveRequest
        fields = ["leave_type", "start_date", "end_date", "reason"]
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, employee=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.employee = employee or getattr(self.instance, "employee", None)
        self.fields["leave_type"].queryset = LeaveType.objects.filter(is_active=True)
        for name, field in self.fields.items():
            field.widget.attrs["class"] = (
                "form-select" if name == "leave_type" else "form-control"
            )

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get("start_date")
        end = cleaned.get("end_date")
        if start and end:
            if end < start:
                self.add_error("end_date", "End date cannot be before the start date.")
            elif self.employee is not None:
                clash = LeaveRequest.overlapping(
                    self.employee,
                    start,
                    end,
                    exclude_pk=self.instance.pk,
                )
                if clash.exists():
                    self.add_error(
                        "start_date",
                        "This overlaps an existing pending or approved leave "
                        "request.",
                    )
        return cleaned


class LeaveDecisionForm(forms.Form):
    decision = forms.ChoiceField(
        choices=[("APPROVED", "Approve"), ("REJECTED", "Reject")]
    )
    note = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}))
