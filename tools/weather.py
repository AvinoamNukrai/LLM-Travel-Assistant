"""
tools/weather.py

Weather and geocoding utilities using Open-Meteo (free, no key required).
- geocode_city: get coordinates for a city name
- fetch_weather: get daily forecast range for tmax/tmin and precip prob
- summarize_weather: build a short 'Tool facts' line for prompts
"""

from dataclasses import dataclass

from util.http import get_json


@dataclass
class Geo:
    name: str
    lat: float
    lon: float
    country: str | None = None


def geocode_city(name):
    if not name:
        return None
    data = get_json(
        "https://geocoding-api.open-meteo.com/v1/search",
        params={"name": name, "count": 3, "language": "en"},
        retries=1,
    )
    results = data.get("results") or []
    if not results:
        return None
    top = results[0]
    return Geo(
        name=top.get("name", name),
        lat=float(top["latitude"]),
        lon=float(top["longitude"]),
        country=top.get("country"),
    )


def fetch_weather(lat, lon, start, end):
    data = get_json(
        "https://api.open-meteo.com/v1/forecast",
        params={
            "latitude": lat,
            "longitude": lon,
            "start_date": start,
            "end_date": end,
            "daily": ["temperature_2m_max", "temperature_2m_min", "precipitation_probability_max"],
            "timezone": "UTC",
        },
        retries=1,
    )
    daily = data.get("daily")
    if not daily:
        return None
    return {
        "dates": daily.get("time", []),
        "tmax": daily.get("temperature_2m_max", []),
        "tmin": daily.get("temperature_2m_min", []),
        "pop": daily.get("precipitation_probability_max", []),
    }


def summarize_weather(city, start, end, w):
    try:
        highs = round(sum(w["tmax"]) / max(len(w["tmax"]), 1))
        lows = round(sum(w["tmin"]) / max(len(w["tmin"]), 1))
        pop = round(sum(w["pop"]) / max(len(w["pop"]), 1))
        return f"Tool facts: {city} {start}→{end} | highs {highs}°C, lows {lows}°C, rain {pop}%"
    except Exception:
        return f"Tool facts: {city} {start}→{end} | weather summary unavailable"
