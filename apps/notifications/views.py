from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.views import View
from django.views.generic import CreateView, ListView

from apps.accounts.mixins import EmployeeRequiredMixin, HRRequiredMixin
from apps.audit.services import log_action

from .forms import AnnouncementForm, CalendarEventForm
from .models import Announcement, Audience, CalendarEvent, Notification
from .services import broadcast_announcement


# --------------------------------------------------------------------------- #
# HR views
# --------------------------------------------------------------------------- #
class AnnouncementListView(HRRequiredMixin, ListView):
    model = Announcement
    template_name = "notifications/announcement_list.html"
    context_object_name = "announcements"


class AnnouncementCreateView(HRRequiredMixin, CreateView):
    model = Announcement
    form_class = AnnouncementForm
    template_name = "notifications/announcement_form.html"

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        response = super().form_valid(form)
        if self.object.is_active:
            broadcast_announcement(self.object)
        log_action(
            self.request.user,
            "ANNOUNCEMENT_CREATED",
            self.object,
            audience=self.object.audience,
        )
        return response

    def get_success_url(self):
        return reverse("notifications:announcements_hr")


class CalendarListView(HRRequiredMixin, ListView):
    model = CalendarEvent
    template_name = "notifications/calendar_list.html"
    context_object_name = "events"

    def get_queryset(self):
        return CalendarEvent.objects.select_related("project").all()


class CalendarCreateView(HRRequiredMixin, CreateView):
    model = CalendarEvent
    form_class = CalendarEventForm
    template_name = "notifications/calendar_form.html"

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        response = super().form_valid(form)
        log_action(self.request.user, "CALENDAR_EVENT_CREATED", self.object)
        return response

    def get_success_url(self):
        return reverse("notifications:calendar_hr")


# --------------------------------------------------------------------------- #
# Employee views
# --------------------------------------------------------------------------- #
class MyNotificationsView(EmployeeRequiredMixin, ListView):
    template_name = "notifications/my_notifications.html"
    context_object_name = "notifications"

    def get_queryset(self):
        return self.request.user.notifications.all()


class NotificationMarkReadView(EmployeeRequiredMixin, View):
    def post(self, request, pk):
        notification = request.user.notifications.filter(pk=pk).first()
        if notification:
            notification.is_read = True
            notification.save(update_fields=["is_read"])
            if notification.url:
                return redirect(notification.url)
        return redirect("notifications:my")


class NotificationsMarkAllReadView(EmployeeRequiredMixin, View):
    def post(self, request):
        request.user.notifications.filter(is_read=False).update(is_read=True)
        return redirect("notifications:my")


class MyAnnouncementsView(EmployeeRequiredMixin, ListView):
    template_name = "notifications/my_announcements.html"
    context_object_name = "announcements"

    def get_queryset(self):
        return Announcement.objects.filter(
            is_active=True, audience__in=[Audience.ALL, Audience.EMPLOYEE]
        )


class MyCalendarView(EmployeeRequiredMixin, ListView):
    template_name = "notifications/my_calendar.html"
    context_object_name = "events"

    def get_queryset(self):
        return CalendarEvent.objects.filter(
            audience__in=[Audience.ALL, Audience.EMPLOYEE]
        ).select_related("project")
