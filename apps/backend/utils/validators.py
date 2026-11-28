import re
from datetime import datetime

EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")
PHONE_REGEX = re.compile(r"^\+?[0-9\s\-]{7,15}$")
DATE_REGEX = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def validate_email(email: str) -> bool:
    if not email or not isinstance(email, str):
        return False
    return bool(EMAIL_REGEX.match(email.strip()))


def validate_phone(phone: str) -> bool:
    if not phone or not isinstance(phone, str):
        return False
    return bool(PHONE_REGEX.match(phone.strip()))


def validate_date_str(date_str: str) -> bool:
    if not date_str or not isinstance(date_str, str):
        return False
    if not DATE_REGEX.match(date_str.strip()):
        return False
    try:
        datetime.strptime(date_str.strip(), "%Y-%m-%d")
        return True
    except ValueError:
        return False


def validate_password_strength(password: str) -> tuple[bool, str]:
    if not password or len(password) < 8:
        return False, "Password must be at least 8 characters long."
    if not any(c.isupper() for c in password):
        return False, "Password must contain at least one uppercase letter."
    if not any(c.islower() for c in password):
        return False, "Password must contain at least one lowercase letter."
    if not any(c.isdigit() for c in password):
        return False, "Password must contain at least one number."
    return True, ""
