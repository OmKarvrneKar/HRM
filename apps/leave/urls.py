from django.urls import path

from . import views

app_name = "leave"

urlpatterns = [
    # HR
    path("requests/", views.LeaveRequestListView.as_view(), name="requests"),
    path(
        "requests/<int:pk>/decision/",
        views.LeaveDecisionView.as_view(),
        name="decision",
    ),
    path("types/", views.LeaveTypeListView.as_view(), name="types"),
    path("types/new/", views.LeaveTypeCreateView.as_view(), name="type_create"),
    path(
        "types/<int:pk>/edit/",
        views.LeaveTypeUpdateView.as_view(),
        name="type_edit",
    ),
    # Employee
    path("me/", views.MyLeaveView.as_view(), name="my"),
    path("new/", views.LeaveRequestCreateView.as_view(), name="create"),
]
