from django import forms

from .models import HRDocument, LegalCommunication


def _style(fields):
    for field in fields.values():
        if isinstance(field.widget, forms.Select):
            field.widget.attrs["class"] = "form-select"
        elif isinstance(field.widget, forms.CheckboxInput):
            field.widget.attrs["class"] = "form-check-input"
        else:
            field.widget.attrs["class"] = "form-control"


class HRDocumentForm(forms.ModelForm):
    class Meta:
        model = HRDocument
        fields = ["title", "document_type", "employee", "visibility", "file"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _style(self.fields)
        self.fields["employee"].required = False
        if self.instance.pk:
            # Editing metadata does not require re-uploading the file.
            self.fields["file"].required = False


class LegalCommunicationForm(forms.ModelForm):
    class Meta:
        model = LegalCommunication
        fields = [
            "title",
            "body",
            "audience",
            "employee",
            "group",
            "attachment",
            "is_active",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _style(self.fields)
        for name in ("employee", "group", "attachment"):
            self.fields[name].required = False

    def clean(self):
        cleaned = super().clean()
        audience = cleaned.get("audience")
        if audience == "SINGLE_EMPLOYEE" and not cleaned.get("employee"):
            self.add_error("employee", "Choose an employee for this audience.")
        if audience == "GROUP" and not cleaned.get("group"):
            self.add_error("group", "Choose a group for this audience.")
        return cleaned
