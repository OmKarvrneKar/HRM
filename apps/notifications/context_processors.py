def unread_notifications_count(request):
    """Expose the signed-in user's unread-notification count to templates."""
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return {"unread_notifications_count": 0}
    return {
        "unread_notifications_count": user.notifications.filter(
            is_read=False
        ).count()
    }
