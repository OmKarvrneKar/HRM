from django.contrib import admin

from .models import Announcement, CalendarEvent, Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("recipient", "title", "is_read", "created_at")
    list_filter = ("is_read",)
    search_fields = ("title", "recipient__username")


@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    list_display = ("title", "audience", "is_active", "created_at")
    list_filter = ("audience", "is_active")


@admin.register(CalendarEvent)
class CalendarEventAdmin(admin.ModelAdmin):
    list_display = ("title", "event_date", "audience", "project")
    list_filter = ("audience",)
    date_hierarchy = "event_date"
