import logging
from datetime import datetime
from utils.timezone import now_local
from services.holiday_service import HolidayService

logger = logging.getLogger(__name__)


class FestivalService:
    """
    Date-triggered Cultural Festival & Seasonal Animation Engine for AI Samrat HRMS.
    Renders culturally accurate, lightweight CSS/JS themes celebrating Diwali, Christmas,
    Ramzan / Eid, and Bengaluru / Karnataka regional heritage (Kannada Rajyotsava, Ugadi).
    """

    FESTIVAL_CALENDAR = [
        {
            "id": "diwali",
            "name": "Deepavali — Festival of Lights",
            "emoji": "🪔",
            "title": "Deepavali — Festival of Lights 🪔",
            "greeting": "AI Samrat wishes you a luminous, joyful, and prosperous Deepavali!",
            "description": "May the divine glow of diyas illuminate your home and workplace with health, peace, and abundance.",
            "theme_class": "festival-diwali",
            "animation_type": "diwali_lights",
            "primary_color": "#f59e0b",
            "secondary_color": "#d97706",
            "accent_badge": "🪔 Shubh Deepavali"
        },
        {
            "id": "karnataka_rajyotsava",
            "name": "Karnataka Rajyotsava",
            "emoji": "🟡🔴",
            "title": "ಕನ್ನಡ ರಾಜ್ಯೋತ್ಸವ — Karnataka Rajyotsava 🟡🔴",
            "greeting": "ಕನ್ನಡ ರಾಜ್ಯೋತ್ಸವದ ಹಾರ್ದಿಕ ಶುಭಾಶಯಗಳು!",
            "description": "AI Samrat celebrates Bengaluru and Karnataka's glorious cultural heritage, language, and pioneering innovation spirit.",
            "theme_class": "festival-karnataka",
            "animation_type": "karnataka_ribbon",
            "primary_color": "#facc15",
            "secondary_color": "#dc2626",
            "accent_badge": "🟡🔴 ಸಿರಿಗನ್ನಡಂ ಗೆಲ್ಗೆ"
        },
        {
            "id": "christmas",
            "name": "Christmas & Season's Greetings",
            "emoji": "🎄❄️",
            "title": "Merry Christmas & Season's Greetings 🎄❄️",
            "greeting": "Warmest holiday greetings from the entire team at AI Samrat!",
            "description": "Wishing you, your family, and our global team peace, good cheer, and wonderful celebrations.",
            "theme_class": "festival-christmas",
            "animation_type": "christmas_snow",
            "primary_color": "#0ea5e9",
            "secondary_color": "#10b981",
            "accent_badge": "❄️ Festive Season"
        },
        {
            "id": "new_year",
            "name": "New Year Celebrations",
            "emoji": "✨🥂",
            "title": "Happy New Year! ✨🥂",
            "greeting": "Welcome to an extraordinary new year of growth and innovation with AI Samrat!",
            "description": "May this year bring inspiring achievements, groundbreaking technology, and joy to your endeavors.",
            "theme_class": "festival-newyear",
            "animation_type": "confetti_streamers",
            "primary_color": "#00c2ff",
            "secondary_color": "#0056d6",
            "accent_badge": "🎉 New Beginnings"
        },
        {
            "id": "sankranti",
            "name": "Makar Sankranti & Pongal",
            "emoji": "🪁🌾",
            "title": "Happy Makar Sankranti & Pongal 🪁🌾",
            "greeting": "Wishing you a bountiful harvest season and soaring kites of prosperity!",
            "description": "May this harvest festival bring new warmth, positivity, and sweet celebrations to your home.",
            "theme_class": "festival-sankranti",
            "animation_type": "sankranti_kites",
            "primary_color": "#f59e0b",
            "secondary_color": "#10b981",
            "accent_badge": "🪁 Happy Sankranti"
        },
        {
            "id": "republic_day",
            "name": "Republic Day",
            "emoji": "🇮🇳",
            "title": "Republic Day of India 🇮🇳",
            "greeting": "Happy Republic Day! AI Samrat honors the Constitution and sovereignty of India.",
            "description": "Saluting our nation's diversity, integrity, and visionary strides in science and human progress.",
            "theme_class": "festival-patriots",
            "animation_type": "tricolor_accents",
            "primary_color": "#f97316",
            "secondary_color": "#16a34a",
            "accent_badge": "🇮🇳 Jai Hind"
        },
        {
            "id": "ugadi",
            "name": "Ugadi — Karnataka New Year",
            "emoji": "🥭🌿",
            "title": "ಯುಗಾದಿ ಹಬ್ಬದ ಶುಭಾಶಯಗಳು — Happy Ugadi 🥭🌿",
            "greeting": "ಯುಗಾದಿ ಹಬ್ಬದ ಹಾರ್ದಿಕ ಶುಭಾಶಯಗಳು!",
            "description": "May the Bevu-Bella of Ugadi remind us of life's balanced flavors and usher in a year of prosperity.",
            "theme_class": "festival-ugadi",
            "animation_type": "ugadi_foliage",
            "primary_color": "#84cc16",
            "secondary_color": "#f59e0b",
            "accent_badge": "🌿 ಹೊಸ ವರ್ಷದ ಶುಭಾಶಯಗಳು"
        },
        {
            "id": "eid",
            "name": "Eid-ul-Fitr & Ramzan Kareem",
            "emoji": "🌙✨",
            "title": "Eid Mubarak & Ramzan Kareem 🌙✨",
            "greeting": "Eid Mubarak to you and your loved ones from all of us at AI Samrat!",
            "description": "May the peace, compassion, and divine light of this sacred season fill your home with harmony.",
            "theme_class": "festival-eid",
            "animation_type": "crescent_stars",
            "primary_color": "#10b981",
            "secondary_color": "#f59e0b",
            "accent_badge": "🌙 Eid Mubarak"
        },
        {
            "id": "independence_day",
            "name": "Independence Day",
            "emoji": "🇮🇳",
            "title": "Happy Independence Day 🇮🇳",
            "greeting": "Celebrating India's Freedom, Unity, and Global Technological Leadership!",
            "description": "AI Samrat proudly celebrates our nation's relentless journey of progress and self-reliance.",
            "theme_class": "festival-patriots",
            "animation_type": "tricolor_accents",
            "primary_color": "#f97316",
            "secondary_color": "#16a34a",
            "accent_badge": "🇮🇳 Swatantrata Diwas"
        }
    ]

    @classmethod
    def get_active_festival(cls, target_local_dt: datetime = None) -> dict | None:
        """
        Returns a festival only when an organization holiday is scheduled for today.
        """
        cur_dt = target_local_dt or now_local()
        try:
            today_iso = cur_dt.strftime("%Y-%m-%d")
            holidays = HolidayService.get_all_holidays(year=cur_dt.year)
            holiday = next((item for item in holidays if item.get("date") == today_iso), None)
            if not holiday:
                return None

            name = holiday.get("name") or "Corporate Holiday"
            normalized_name = name.casefold()
            festival = next(
                (
                    item for item in cls.FESTIVAL_CALENDAR
                    if any(
                        keyword in normalized_name
                        for keyword in {
                            "diwali": ("diwali", "deepavali"),
                            "karnataka_rajyotsava": ("rajyotsava", "karnataka"),
                            "christmas": ("christmas",),
                            "new_year": ("new year",),
                            "sankranti": ("sankranti", "pongal"),
                            "republic_day": ("republic",),
                            "ugadi": ("ugadi",),
                            "eid": ("eid", "ramzan", "ramadan"),
                            "independence_day": ("independence",)
                        }.get(item["id"], ())
                    )
                ),
                None
            )
            result = dict(festival) if festival else {
                "id": "corporate_holiday",
                "emoji": "🎉",
                "theme_class": "festival-general",
                "animation_type": "celebration",
                "primary_color": "#0056d6",
                "secondary_color": "#00c2ff",
                "accent_badge": "Corporate Holiday"
            }
            result.update({
                "name": name,
                "title": festival["title"] if festival else name,
                "greeting": f"AI Samrat wishes you a happy {name}!",
                "description": holiday.get("description") or "Today is an organization holiday.",
                "today_str": today_iso
            })
            return result
        except Exception as e:
            logger.warning("Could not check today's festival greeting: %s", e)
            raise
