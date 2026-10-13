from django import forms

from apps.employees.models import Employee

from .models import GroupMembership, Project, ProjectAssignment, TeamGroup, WorkLog


def _style(fields):
    for name, field in fields.items():
        if isinstance(field.widget, (forms.Select, forms.SelectMultiple)):
            field.widget.attrs["class"] = "form-select"
        elif isinstance(field.widget, forms.CheckboxInput):
            field.widget.attrs["class"] = "form-check-input"
        else:
            field.widget.attrs["class"] = "form-control"


class ProjectForm(forms.ModelForm):
    class Meta:
        model = Project
        fields = ["name", "description", "start_date", "end_date", "status"]
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _style(self.fields)

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get("start_date")
        end = cleaned.get("end_date")
        if start and end and end < start:
            self.add_error("end_date", "End date cannot be before the start date.")
        return cleaned


class ProjectAssignmentForm(forms.ModelForm):
    class Meta:
        model = ProjectAssignment
        fields = ["employee", "role"]

    def __init__(self, *args, project=None, **kwargs):
        super().__init__(*args, **kwargs)
        _style(self.fields)
        if project is not None:
            assigned = project.assignments.values_list("employee_id", flat=True)
            self.fields["employee"].queryset = Employee.objects.exclude(pk__in=assigned)


class TeamGroupForm(forms.ModelForm):
    class Meta:
        model = TeamGroup
        fields = ["name", "description"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _style(self.fields)


class GroupMembershipForm(forms.ModelForm):
    class Meta:
        model = GroupMembership
        fields = ["employee"]

    def __init__(self, *args, group=None, **kwargs):
        super().__init__(*args, **kwargs)
        _style(self.fields)
        if group is not None:
            members = group.memberships.values_list("employee_id", flat=True)
            self.fields["employee"].queryset = Employee.objects.exclude(pk__in=members)


class WorkLogForm(forms.ModelForm):
    class Meta:
        model = WorkLog
        fields = ["project", "date", "hours", "description"]
        widgets = {"date": forms.DateInput(attrs={"type": "date"})}

    def __init__(self, *args, employee=None, **kwargs):
        super().__init__(*args, **kwargs)
        _style(self.fields)
        if employee is not None:
            projects = Project.objects.filter(assignments__employee=employee)
            self.fields["project"].queryset = projects
        self.fields["project"].required = False
