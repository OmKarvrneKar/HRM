from django.urls import reverse

from .models import Audience, Notification


def notify(user, title, message="", url=""):
    """Create an in-app notification for a single user."""
    return Notification.objects.create(
        recipient=user, title=title, message=message, url=url
    )


def recipients_for_audience(audience):
    from apps.accounts.models import Role, User

    if audience == Audience.HR:
        return User.objects.filter(role=Role.HR)
    if audience == Audience.EMPLOYEE:
        return User.objects.filter(role=Role.EMPLOYEE)
    return User.objects.all()


def broadcast_announcement(announcement):
    """Fan an announcement out to notifications for its audience."""
    url = reverse("notifications:announcements")
    for user in recipients_for_audience(announcement.audience):
        notify(user, f"Announcement: {announcement.title}", announcement.body, url)
