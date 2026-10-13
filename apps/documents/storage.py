from django.conf import settings
from django.core.files.storage import FileSystemStorage

# Sensitive HR documents live outside the public media root and are only
# reached through permission-checked download views. base_url=None prevents
# Django from ever generating a public URL for these files.
private_storage = FileSystemStorage(
    location=settings.PRIVATE_MEDIA_ROOT, base_url=None
)
