from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

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


class AnnouncementUpdateView(HRRequiredMixin, UpdateView):
    model = Announcement
    form_class = AnnouncementForm
    template_name = "notifications/announcement_form.html"

    def form_valid(self, form):
        was_active = (
            Announcement.objects.filter(pk=self.object.pk)
            .values_list("is_active", flat=True)
            .first()
        )
        response = super().form_valid(form)
        # Fan out again only when the announcement is (re)activated.
        if self.object.is_active and not was_active:
            broadcast_announcement(self.object)
        log_action(
            self.request.user,
            "ANNOUNCEMENT_UPDATED",
            self.object,
            audience=self.object.audience,
            is_active=self.object.is_active,
        )
        return response

    def get_success_url(self):
        return reverse("notifications:announcements_hr")


class AnnouncementDeleteView(HRRequiredMixin, DeleteView):
    model = Announcement
    http_method_names = ["post"]
    success_url = reverse_lazy("notifications:announcements_hr")

    def form_valid(self, form):
        self.object = self.get_object()
        log_action(
            self.request.user,
            "ANNOUNCEMENT_DELETED",
            self.object,
            title=self.object.title,
        )
        return super().form_valid(form)


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


class CalendarUpdateView(HRRequiredMixin, UpdateView):
    model = CalendarEvent
    form_class = CalendarEventForm
    template_name = "notifications/calendar_form.html"

    def form_valid(self, form):
        response = super().form_valid(form)
        log_action(
            self.request.user,
            "CALENDAR_EVENT_UPDATED",
            self.object,
            event_date=str(self.object.event_date),
        )
        return response

    def get_success_url(self):
        return reverse("notifications:calendar_hr")


class CalendarDeleteView(HRRequiredMixin, DeleteView):
    model = CalendarEvent
    http_method_names = ["post"]
    success_url = reverse_lazy("notifications:calendar_hr")

    def form_valid(self, form):
        self.object = self.get_object()
        log_action(
            self.request.user,
            "CALENDAR_EVENT_DELETED",
            self.object,
            title=self.object.title,
        )
        return super().form_valid(form)


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
            if notification.url and url_has_allowed_host_and_scheme(
                notification.url,
                allowed_hosts={request.get_host()},
                require_https=request.is_secure(),
            ):
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
