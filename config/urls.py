"""Root URL configuration for the HR Management System."""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("django-admin/", admin.site.urls),
    path("accounts/", include("apps.accounts.urls")),
    path("people/", include("apps.employees.urls")),
    path("attendance/", include("apps.attendance.urls")),
    path("leave/", include("apps.leave.urls")),
    path("projects/", include("apps.projects.urls")),
    path("documents/", include("apps.documents.urls")),
    path("notifications/", include("apps.notifications.urls")),
    path("", include("apps.core.urls")),
]

if settings.DEBUG:
    # Only non-private media (e.g. profile photos) is served directly. HR
    # documents use a permission-checked download view instead.
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
