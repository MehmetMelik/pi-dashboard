"""Google Calendar events via ICS feed."""

from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo

import httpx
from icalendar import Calendar

from app.config import GOOGLE_CALENDAR_ICS

TZ = ZoneInfo("Europe/London")

# In-memory cache
_cache: list[dict] = []


def _to_local_dt(dt_val) -> datetime:
    """Convert icalendar date/datetime to a timezone-aware London datetime."""
    if isinstance(dt_val, datetime):
        if dt_val.tzinfo is None:
            return dt_val.replace(tzinfo=TZ)
        return dt_val.astimezone(TZ)
    if isinstance(dt_val, date):
        return datetime(dt_val.year, dt_val.month, dt_val.day, tzinfo=TZ)
    return datetime.now(TZ)


async def refresh_calendar():
    global _cache
    if not GOOGLE_CALENDAR_ICS:
        return

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(GOOGLE_CALENDAR_ICS)
            resp.raise_for_status()
            ics_text = resp.text
    except Exception as e:
        print(f"[calendar] fetch error: {e}")
        return

    try:
        cal = Calendar.from_ical(ics_text)
    except Exception as e:
        print(f"[calendar] parse error: {e}")
        return

    now = datetime.now(TZ)
    today = now.date()
    window_end = today + timedelta(days=14)

    events = []
    for component in cal.walk():
        if component.name != "VEVENT":
            continue

        summary = str(component.get("summary", ""))
        if not summary:
            continue

        dtstart = component.get("dtstart")
        dtend = component.get("dtend")
        location = str(component.get("location", "")) if component.get("location") else None

        if not dtstart:
            continue

        start = _to_local_dt(dtstart.dt)
        start_date = start.date() if isinstance(start, datetime) else start

        # Filter: only show events from today to 14 days ahead
        if start_date < today or start_date > window_end:
            continue

        # Determine if all-day event
        all_day = isinstance(dtstart.dt, date) and not isinstance(dtstart.dt, datetime)

        end = None
        if dtend:
            end = _to_local_dt(dtend.dt)

        events.append({
            "summary": summary,
            "start": start,
            "end": end,
            "start_date": start_date.isoformat(),
            "start_time": "" if all_day else start.strftime("%H:%M"),
            "end_time": "" if all_day or not end else end.strftime("%H:%M"),
            "all_day": all_day,
            "location": location,
            "is_today": start_date == today,
            "is_tomorrow": start_date == today + timedelta(days=1),
            "weekday": start.strftime("%a"),
            "day": start.strftime("%-d"),
            "month": start.strftime("%b"),
        })

    events.sort(key=lambda e: e["start"])
    _cache = events
    print(f"[calendar] refreshed {len(events)} upcoming events")


def get_events() -> list[dict]:
    return _cache
