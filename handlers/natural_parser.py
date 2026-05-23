from datetime import datetime
from typing import Optional, Tuple

from dateparser.search import search_dates


def parse_event_text(
    text: str,
    user_tz: str = 'Europe/Moscow',
) -> Tuple[Optional[datetime], Optional[str]]:
    """
    Извлекает дату/время и название события из произвольного текста.
    Возвращает (datetime, summary) или (None, None).
    """
    settings = {
        'TIMEZONE': user_tz,
        'RETURN_AS_TIMEZONE_AWARE': True,
        'PREFER_DATES_FROM': 'future',
        'LANGUAGES': ['ru'],
    }
    results = search_dates(text, languages=['ru'], settings=settings)
    if not results:
        return None, None

    phrase, parsed_dt = results[0]
    summary = text.replace(phrase, '', 1).strip(' ,.-–—').strip()
    if not summary:
        return None, None

    return parsed_dt, summary
