from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import Role, User

from .models import Announcement, Audience, Notification


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
