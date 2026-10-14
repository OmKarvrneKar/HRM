"""
Django settings for the Office HR Management System.

Values that must not be committed to source control are read from a local
`.env` file (see `.env.example`). Never hard-code secrets or real employee data.
"""
from pathlib import Path

from decouple import Csv, config
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent

# --- Security -----------------------------------------------------------------
_SECRET_KEY_DEFAULT = "dev-only-insecure-change-me"
SECRET_KEY = config("DJANGO_SECRET_KEY", default=_SECRET_KEY_DEFAULT)
DEBUG = config("DJANGO_DEBUG", default=True, cast=bool)
ALLOWED_HOSTS = config(
    "DJANGO_ALLOWED_HOSTS", default="127.0.0.1,localhost", cast=Csv()
)
CSRF_TRUSTED_ORIGINS = [
    origin
    for origin in config("DJANGO_CSRF_TRUSTED_ORIGINS", default="", cast=Csv())
    if origin
]

if not DEBUG and SECRET_KEY == _SECRET_KEY_DEFAULT:
    # Refuse to start a production instance with the placeholder key.
    raise ImproperlyConfigured(
        "DJANGO_SECRET_KEY must be set to a long random value when DEBUG is off."
    )

if not DEBUG:
    # Hardening applied automatically outside development. Each value can still
    # be overridden from the environment for unusual deployments.
    SECURE_SSL_REDIRECT = config("DJANGO_SECURE_SSL_REDIRECT", True, cast=bool)
    SESSION_COOKIE_SECURE = config("DJANGO_SESSION_COOKIE_SECURE", True, cast=bool)
    CSRF_COOKIE_SECURE = config("DJANGO_CSRF_COOKIE_SECURE", True, cast=bool)
    SECURE_HSTS_SECONDS = config("DJANGO_SECURE_HSTS_SECONDS", 31536000, cast=int)
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    # Trust the reverse proxy's forwarded protocol so redirects/cookies are HTTPS.
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

X_FRAME_OPTIONS = "DENY"

# --- Applications -------------------------------------------------------------
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Local apps
    "apps.core",
    "apps.accounts",
    "apps.employees",
    "apps.attendance",
    "apps.leave",
    "apps.projects",
    "apps.documents",
    "apps.notifications",
    "apps.audit",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.accounts.middleware.ForcePasswordChangeMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.notifications.context_processors.unread_notifications_count",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# --- Database -----------------------------------------------------------------
# SQLite for development. Move to PostgreSQL later by swapping this block for
# env-driven settings; the ORM and migrations stay the same.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

# --- Authentication -----------------------------------------------------------
AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "core:home"
LOGOUT_REDIRECT_URL = "accounts:login"

# --- Internationalization -----------------------------------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_TZ = True

# --- Static & media -----------------------------------------------------------
STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

# HR documents and other sensitive files are stored OUTSIDE the public media
# root and are only served through authenticated, permission-checked views.
PRIVATE_MEDIA_ROOT = BASE_DIR / "private_media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
