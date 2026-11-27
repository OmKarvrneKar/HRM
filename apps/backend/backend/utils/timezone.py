from datetime import datetime, date, time
from zoneinfo import ZoneInfo
from config import Config

def get_app_timezone() -> ZoneInfo:
    """Returns the application default timezone (e.g. Asia/Kolkata)."""
    return ZoneInfo(Config.DEFAULT_TIMEZONE)


def now_utc() -> datetime:
    """Returns the current UTC datetime with timezone awareness."""
    return datetime.now(ZoneInfo("UTC"))


def now_local() -> datetime:
    """Returns the current local datetime in Asia/Kolkata."""
    return datetime.now(get_app_timezone())


def to_local(dt: datetime) -> datetime:
    """Converts a UTC or naive datetime to local Asia/Kolkata datetime."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo("UTC"))
    return dt.astimezone(get_app_timezone())


def to_utc(dt: datetime) -> datetime:
    """Converts a local or naive datetime to UTC datetime."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=get_app_timezone())
    return dt.astimezone(ZoneInfo("UTC"))


def get_local_date_str(dt: datetime = None) -> str:
    """Returns 'YYYY-MM-DD' formatted date in Asia/Kolkata."""
    target = dt if dt is not None else now_utc()
    return to_local(target).strftime("%Y-%m-%d")


def parse_time_str(time_str: str) -> time:
    """Parses 'HH:MM' string into a time object."""
    parts = time_str.split(":")
    return time(hour=int(parts[0]), minute=int(parts[1]))


def is_leap_year(year: int) -> bool:
    """Determines whether a year is a leap year."""
    return (year % 4 == 0 and year % 100 != 0) or (year % 400 == 0)
