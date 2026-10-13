"""Root URL configuration for the HR Management System."""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("django-admin/", admin.site.urls),
    path("accounts/", include("apps.accounts.urls")),
    path("people/", include("apps.employees.urls")),
    path("", include("apps.core.urls")),
]

if settings.DEBUG:
    # Only non-private media (e.g. profile photos) is served directly. HR
    # documents use a permission-checked download view instead.
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
