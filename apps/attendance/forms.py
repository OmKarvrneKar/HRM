from django import forms

from .models import AttendanceCorrectionRequest, AttendanceRecord


class AttendanceRecordForm(forms.ModelForm):
    """HR manual attendance entry / edit."""

    class Meta:
        model = AttendanceRecord
        fields = ["employee", "date", "check_in", "check_out", "status", "note"]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}),
            "check_in": forms.TimeInput(attrs={"type": "time"}),
            "check_out": forms.TimeInput(attrs={"type": "time"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            css = "form-select" if isinstance(field.widget, forms.Select) else "form-control"
            field.widget.attrs["class"] = css
        self.fields["employee"].queryset = self.fields["employee"].queryset.order_by(
            "employee_id"
        )


class CorrectionRequestForm(forms.ModelForm):
    """Employee attendance correction request."""

    class Meta:
        model = AttendanceCorrectionRequest
        fields = ["date", "requested_check_in", "requested_check_out", "reason"]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}),
            "requested_check_in": forms.TimeInput(attrs={"type": "time"}),
            "requested_check_out": forms.TimeInput(attrs={"type": "time"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = "form-control"


class CorrectionDecisionForm(forms.Form):
    decision = forms.ChoiceField(
        choices=[("APPROVED", "Approve"), ("REJECTED", "Reject")]
    )
    note = forms.CharField(
        required=False,
        label="Reason (optional)",
        widget=forms.Textarea(attrs={"rows": 2}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            css = "form-select" if isinstance(field.widget, forms.Select) else "form-control"
            field.widget.attrs.setdefault("class", css)
