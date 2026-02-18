"""Weather data from Open-Meteo API."""

import httpx
from app.config import WEATHER_URL, WEATHER_LAT, WEATHER_LON
from app.database import save_weather, load_weather

# WMO Weather Code descriptions
WMO_CODES = {
    0: ("Clear sky", "☀️"),
    1: ("Mainly clear", "🌤️"),
    2: ("Partly cloudy", "⛅"),
    3: ("Overcast", "☁️"),
    45: ("Foggy", "🌫️"),
    48: ("Rime fog", "🌫️"),
    51: ("Light drizzle", "🌦️"),
    53: ("Moderate drizzle", "🌦️"),
    55: ("Dense drizzle", "🌧️"),
    61: ("Slight rain", "🌦️"),
    63: ("Moderate rain", "🌧️"),
    65: ("Heavy rain", "🌧️"),
    71: ("Slight snow", "🌨️"),
    73: ("Moderate snow", "🌨️"),
    75: ("Heavy snow", "❄️"),
    80: ("Slight showers", "🌦️"),
    81: ("Moderate showers", "🌧️"),
    82: ("Violent showers", "⛈️"),
    95: ("Thunderstorm", "⛈️"),
    96: ("Thunderstorm + hail", "⛈️"),
    99: ("Thunderstorm + heavy hail", "⛈️"),
}

WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


async def fetch_weather() -> dict | None:
    params = {
        "latitude": WEATHER_LAT,
        "longitude": WEATHER_LON,
        "current": "temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,wind_speed_10m",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
        "timezone": "Europe/London",
        "forecast_days": 5,
    }
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(WEATHER_URL, params=params)
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        print(f"[weather] fetch error: {e}")
        return None

    current = data.get("current", {})
    daily = data.get("daily", {})

    code = current.get("weather_code", 0)
    desc, icon = WMO_CODES.get(code, ("Unknown", "❓"))

    parsed = {
        "current": {
            "temp": current.get("temperature_2m"),
            "feels_like": current.get("apparent_temperature"),
            "humidity": current.get("relative_humidity_2m"),
            "wind": current.get("wind_speed_10m"),
            "description": desc,
            "icon": icon,
        },
        "forecast": [],
    }

    dates = daily.get("time", [])
    codes = daily.get("weather_code", [])
    maxs = daily.get("temperature_2m_max", [])
    mins = daily.get("temperature_2m_min", [])
    precip = daily.get("precipitation_probability_max", [])

    for i in range(len(dates)):
        fc_code = codes[i] if i < len(codes) else 0
        fc_desc, fc_icon = WMO_CODES.get(fc_code, ("Unknown", "❓"))
        # Parse weekday from date string
        from datetime import date as dt_date
        d = dt_date.fromisoformat(dates[i])
        weekday = WEEKDAYS[d.weekday()]

        parsed["forecast"].append({
            "date": dates[i],
            "weekday": weekday,
            "high": maxs[i] if i < len(maxs) else None,
            "low": mins[i] if i < len(mins) else None,
            "precip": precip[i] if i < len(precip) else None,
            "description": fc_desc,
            "icon": fc_icon,
        })

    save_weather(parsed)
    return parsed


def get_weather() -> dict | None:
    return load_weather()
