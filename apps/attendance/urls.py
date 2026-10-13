from django.urls import path

from . import views

app_name = "attendance"

urlpatterns = [
    # HR
    path("", views.AttendanceListView.as_view(), name="list"),
    path("new/", views.AttendanceCreateView.as_view(), name="create"),
    path("<int:pk>/edit/", views.AttendanceUpdateView.as_view(), name="update"),
    path("corrections/", views.CorrectionReviewListView.as_view(), name="corrections"),
    path(
        "corrections/<int:pk>/decision/",
        views.CorrectionDecisionView.as_view(),
        name="correction_decision",
    ),
    # Employee
    path("me/", views.MyAttendanceView.as_view(), name="my"),
    path("check-in/", views.CheckInView.as_view(), name="check_in"),
    path("check-out/", views.CheckOutView.as_view(), name="check_out"),
    path(
        "corrections/new/",
        views.CorrectionRequestCreateView.as_view(),
        name="correction_create",
    ),
    path(
        "corrections/me/",
        views.MyCorrectionsView.as_view(),
        name="my_corrections",
    ),
]
