from django.conf import settings
from django.core.files.storage import FileSystemStorage


class PrivateFileSystemStorage(FileSystemStorage):
    """Storage for sensitive files that must never have a public URL.

    Files live outside ``MEDIA_ROOT`` and are streamed only through
    permission-checked download views. ``url()`` deliberately returns ``None``
    so Django can never generate (or leak) a public link, regardless of how
    ``MEDIA_URL`` is configured.
    """

    def url(self, name):
        return None

    def deconstruct(self):
        # Keep migration state identical to a plain FileSystemStorage so that
        # adding this no-URL guard never produces a spurious schema migration.
        _, args, kwargs = super().deconstruct()
        return "django.core.files.storage.FileSystemStorage", args, kwargs


private_storage = PrivateFileSystemStorage(
    location=settings.PRIVATE_MEDIA_ROOT, base_url=None
)
