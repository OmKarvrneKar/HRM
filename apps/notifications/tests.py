from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import Role, User
from apps.audit.models import AuditLog

from .models import Announcement, Audience, CalendarEvent, Notification


def make_hr(username="hr"):
    return User.objects.create_user(
        username=username, password="pw12345!", role=Role.HR
    )


def make_employee(username="emp"):
    return User.objects.create_user(
        username=username, password="pw12345!", role=Role.EMPLOYEE
    )


class AnnouncementBroadcastTests(TestCase):
    def setUp(self):
        self.hr = make_hr()
        self.employee = make_employee()

    def test_announcement_to_employees_creates_notification(self):
        self.client.force_login(self.hr)
        response = self.client.post(
            reverse("notifications:announcement_create"),
            {
                "title": "Office closed",
                "body": "The office is closed on Friday.",
                "audience": Audience.EMPLOYEE,
                "is_active": "on",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            Notification.objects.filter(
                recipient=self.employee, title__icontains="Announcement"
            ).exists()
        )
        # HR-only audience should not have been notified about their own blast
        self.assertFalse(Notification.objects.filter(recipient=self.hr).exists())

    def test_announcement_visible_to_employee(self):
        Announcement.objects.create(
            title="Holiday", body="Holiday notice", audience=Audience.ALL
        )
        self.client.force_login(make_employee(username="emp2"))
        response = self.client.get(reverse("notifications:announcements"))
        self.assertContains(response, "Holiday")


class NotificationReadTests(TestCase):
    def setUp(self):
        self.employee = make_employee()

    def test_mark_all_read(self):
        Notification.objects.create(recipient=self.employee, title="Hi")
        self.client.force_login(self.employee)
        self.client.post(reverse("notifications:mark_all_read"))
        self.assertFalse(
            Notification.objects.filter(
                recipient=self.employee, is_read=False
            ).exists()
        )


class NotificationOwnershipTests(TestCase):
    """Item 2: an Employee cannot read or act on another user's notifications."""

    def test_cannot_mark_other_users_notification_read(self):
        other = make_employee(username="other")
        notification = Notification.objects.create(recipient=other, title="Secret")
        self.client.force_login(make_employee(username="me"))
        self.client.post(reverse("notifications:mark_read", args=[notification.pk]))
        notification.refresh_from_db()
        self.assertFalse(notification.is_read)

    def test_list_hides_other_users_notifications(self):
        other = make_employee(username="other")
        Notification.objects.create(recipient=other, title="Secret")
        self.client.force_login(make_employee(username="me"))
        response = self.client.get(reverse("notifications:my"))
        titles = [n.title for n in response.context["notifications"]]
        self.assertNotIn("Secret", titles)


class AnnouncementManagementTests(TestCase):
    def setUp(self):
        self.hr = make_hr()
        self.employee = make_employee()
        self.announcement = Announcement.objects.create(
            title="Old", body="Body", audience=Audience.EMPLOYEE
        )

    def test_hr_can_update_and_audits(self):
        self.client.force_login(self.hr)
        response = self.client.post(
            reverse("notifications:announcement_edit", args=[self.announcement.pk]),
            {
                "title": "New",
                "body": "Body",
                "audience": Audience.EMPLOYEE,
                "is_active": "on",
            },
        )
        self.assertRedirects(response, reverse("notifications:announcements_hr"))
        self.announcement.refresh_from_db()
        self.assertEqual(self.announcement.title, "New")
        self.assertTrue(
            AuditLog.objects.filter(action="ANNOUNCEMENT_UPDATED").exists()
        )

    def test_reactivation_rebroadcasts(self):
        self.announcement.is_active = False
        self.announcement.save(update_fields=["is_active"])
        Notification.objects.all().delete()
        self.client.force_login(self.hr)
        self.client.post(
            reverse("notifications:announcement_edit", args=[self.announcement.pk]),
            {
                "title": "Old",
                "body": "Body",
                "audience": Audience.EMPLOYEE,
                "is_active": "on",
            },
        )
        self.assertTrue(
            Notification.objects.filter(recipient=self.employee).exists()
        )

    def test_hr_can_delete_and_audits(self):
        self.client.force_login(self.hr)
        response = self.client.post(
            reverse("notifications:announcement_delete", args=[self.announcement.pk])
        )
        self.assertRedirects(response, reverse("notifications:announcements_hr"))
        self.assertFalse(
            Announcement.objects.filter(pk=self.announcement.pk).exists()
        )
        self.assertTrue(
            AuditLog.objects.filter(action="ANNOUNCEMENT_DELETED").exists()
        )

    def test_employee_cannot_manage_announcements(self):
        self.client.force_login(self.employee)
        for name in ("announcement_edit", "announcement_delete"):
            response = self.client.get(
                reverse(f"notifications:{name}", args=[self.announcement.pk])
            )
            self.assertEqual(response.status_code, 403)


class CalendarManagementTests(TestCase):
    def setUp(self):
        self.hr = make_hr()
        self.employee = make_employee()
        self.event = CalendarEvent.objects.create(
            title="Meeting",
            event_date="2026-01-02",
            start_time="09:00",
            end_time="10:00",
        )

    def test_rejects_end_before_start(self):
        self.client.force_login(self.hr)
        response = self.client.post(
            reverse("notifications:calendar_create"),
            {
                "title": "Bad",
                "event_date": "2026-01-02",
                "start_time": "10:00",
                "end_time": "09:00",
                "audience": Audience.ALL,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors)

    def test_rejects_end_without_start(self):
        self.client.force_login(self.hr)
        response = self.client.post(
            reverse("notifications:calendar_create"),
            {
                "title": "Bad",
                "event_date": "2026-01-02",
                "end_time": "09:00",
                "audience": Audience.ALL,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors)

    def test_hr_can_update_and_audits(self):
        self.client.force_login(self.hr)
        response = self.client.post(
            reverse("notifications:calendar_edit", args=[self.event.pk]),
            {
                "title": "Renamed",
                "event_date": "2026-01-02",
                "start_time": "09:00",
                "end_time": "10:00",
                "audience": Audience.ALL,
            },
        )
        self.assertRedirects(response, reverse("notifications:calendar_hr"))
        self.event.refresh_from_db()
        self.assertEqual(self.event.title, "Renamed")
        self.assertTrue(
            AuditLog.objects.filter(action="CALENDAR_EVENT_UPDATED").exists()
        )

    def test_hr_can_delete_and_audits(self):
        self.client.force_login(self.hr)
        response = self.client.post(
            reverse("notifications:calendar_delete", args=[self.event.pk])
        )
        self.assertRedirects(response, reverse("notifications:calendar_hr"))
        self.assertFalse(CalendarEvent.objects.filter(pk=self.event.pk).exists())
        self.assertTrue(
            AuditLog.objects.filter(action="CALENDAR_EVENT_DELETED").exists()
        )

    def test_employee_cannot_manage_calendar(self):
        self.client.force_login(self.employee)
        for name in ("calendar_edit", "calendar_delete"):
            response = self.client.get(
                reverse(f"notifications:{name}", args=[self.event.pk])
            )
            self.assertEqual(response.status_code, 403)


class NotificationRedirectTests(TestCase):
    def setUp(self):
        self.employee = make_employee()

    def test_external_url_is_not_followed(self):
        note = Notification.objects.create(
            recipient=self.employee, title="Go", url="https://evil.example.com"
        )
        self.client.force_login(self.employee)
        response = self.client.post(
            reverse("notifications:mark_read", args=[note.pk])
        )
        self.assertRedirects(response, reverse("notifications:my"))

    def test_internal_url_is_followed(self):
        target = reverse("notifications:announcements")
        note = Notification.objects.create(
            recipient=self.employee, title="Go", url=target
        )
        self.client.force_login(self.employee)
        response = self.client.post(
            reverse("notifications:mark_read", args=[note.pk])
        )
        self.assertRedirects(response, target)


class UnreadBadgeTests(TestCase):
    def test_badge_shows_unread_count(self):
        employee = make_employee()
        Notification.objects.create(recipient=employee, title="One")
        Notification.objects.create(recipient=employee, title="Two")
        self.client.force_login(employee)
        response = self.client.get(reverse("core:home"))
        self.assertEqual(response.context["unread_notifications_count"], 2)
        self.assertContains(response, "rounded-pill")
