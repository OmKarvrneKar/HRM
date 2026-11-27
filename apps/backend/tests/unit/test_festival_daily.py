from datetime import datetime

from backend.services.festival_service import FestivalService
from backend.services.holiday_service import HolidayService


def test_festival_greeting_is_limited_to_the_scheduled_day(monkeypatch):
    holiday = {
        "date": "2026-10-25",
        "name": "Diwali",
        "description": "Organization holiday"
    }
    monkeypatch.setattr(
        HolidayService,
        "get_all_holidays",
        classmethod(lambda cls, year=None: [holiday] if year == 2026 else [])
    )

    active = FestivalService.get_active_festival(datetime(2026, 10, 25, 9))
    expired = FestivalService.get_active_festival(datetime(2026, 10, 26, 9))

    assert active is not None
    assert active["id"] == "diwali"
    assert active["emoji"] == "🪔"
    assert active["today_str"] == "2026-10-25"
    assert expired is None


def test_festival_greeting_is_not_issued_for_upcoming_holidays(monkeypatch):
    holiday = {"date": "2026-10-25", "name": "Diwali"}
    monkeypatch.setattr(
        HolidayService,
        "get_all_holidays",
        classmethod(lambda cls, year=None: [holiday])
    )

    assert FestivalService.get_active_festival(datetime(2026, 10, 24, 9)) is None
