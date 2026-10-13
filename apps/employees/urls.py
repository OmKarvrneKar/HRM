from django.urls import path

from . import views

app_name = "employees"

urlpatterns = [
    path("", views.EmployeeListView.as_view(), name="list"),
    path("me/", views.MyProfileView.as_view(), name="my_profile"),
    path("departments/", views.DepartmentListView.as_view(), name="departments"),
    path(
        "departments/new/",
        views.DepartmentCreateView.as_view(),
        name="department_create",
    ),
    path("new/", views.EmployeeCreateView.as_view(), name="create"),
    path(
        "contacts/<int:pk>/delete/",
        views.EmergencyContactDeleteView.as_view(),
        name="contact_delete",
    ),
    path("<int:pk>/", views.EmployeeDetailView.as_view(), name="detail"),
    path("<int:pk>/edit/", views.EmployeeUpdateView.as_view(), name="update"),
    path(
        "<int:pk>/status/",
        views.EmployeeStatusUpdateView.as_view(),
        name="status_update",
    ),
    path(
        "<int:pk>/contacts/add/",
        views.EmergencyContactCreateView.as_view(),
        name="contact_add",
    ),
]
