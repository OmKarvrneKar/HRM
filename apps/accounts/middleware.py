from django.conf import settings
from django.shortcuts import redirect
from django.urls import reverse


class ForcePasswordChangeMiddleware:
    """Redirect users flagged with `must_change_password` to the change form.

    This keeps temporary passwords from being used indefinitely: after an HR
    creates an account with a temporary password, the employee cannot reach any
    other page until a new password is set.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if (
            user is not None
            and user.is_authenticated
            and getattr(user, "must_change_password", False)
        ):
            change_url = reverse("accounts:password_change")
            logout_url = reverse("accounts:logout")
            static_prefix = "/" + settings.STATIC_URL.lstrip("/")
            media_prefix = "/" + settings.MEDIA_URL.lstrip("/")
            path = request.path
            if (
                path != change_url
                and path != logout_url
                and not path.startswith(static_prefix)
                and not path.startswith(media_prefix)
            ):
                return redirect("accounts:password_change")
        return self.get_response(request)
