from django.urls import path

from . import views

app_name = "notifications"

urlpatterns = [
    # HR
    path(
        "announcements/",
        views.AnnouncementListView.as_view(),
        name="announcements_hr",
    ),
    path(
        "announcements/new/",
        views.AnnouncementCreateView.as_view(),
        name="announcement_create",
    ),
    path("calendar/", views.CalendarListView.as_view(), name="calendar_hr"),
    path("calendar/new/", views.CalendarCreateView.as_view(), name="calendar_create"),
    # Employee
    path("me/", views.MyNotificationsView.as_view(), name="my"),
    path("me/<int:pk>/read/", views.NotificationMarkReadView.as_view(), name="mark_read"),
    path(
        "me/read-all/",
        views.NotificationsMarkAllReadView.as_view(),
        name="mark_all_read",
    ),
    path(
        "me/announcements/",
        views.MyAnnouncementsView.as_view(),
        name="announcements",
    ),
    path("me/calendar/", views.MyCalendarView.as_view(), name="calendar"),
]
