"""Weather data: a real OpenWeatherMap client, and a mock stand-in for
before you have an API key.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Protocol

import requests

OWM_URL = "https://api.openweathermap.org/data/2.5/weather"


@dataclass
class WeatherReading:
    temp: float
    description: str
    icon_code: str  # OpenWeatherMap icon code, e.g. "01d", "10n"
    weather_main: str  # OWM's coarse condition family, e.g. "Clear", "Rain", "Clouds"
    clouds_pct: int  # 0-100 cloud cover, used to tell "partly" from "overcast"
    wind_speed_kmh: float
    fetched_at: float  # time.monotonic() timestamp, for staleness checks


class WeatherClient(Protocol):
    def fetch(self) -> WeatherReading: ...


def _wind_speed_to_kmh(raw_speed: float, units: str) -> float:
    """OpenWeatherMap reports wind speed in m/s for metric/standard units,
    but mph for imperial - it does NOT follow the temperature unit choice
    the way you'd expect. The sentence-generation logic (tinyscreen/sentence.py)
    always works in km/h regardless of the temperature display unit, so we
    normalize here, once, rather than every caller needing to remember OWM's
    quirk.
    """
    if units == "imperial":
        return raw_speed * 1.60934  # mph -> km/h
    return raw_speed * 3.6  # m/s -> km/h


class OpenWeatherMapClient:
    """Talks to OpenWeatherMap's free 'Current Weather Data' endpoint."""

    def __init__(
        self,
        api_key: str,
        units: str,
        lat: float | None,
        lon: float | None,
        city: str | None,
    ) -> None:
        self.api_key = api_key
        self.units = units
        self.lat = lat
        self.lon = lon
        self.city = city

    def fetch(self) -> WeatherReading:
        params = {"appid": self.api_key, "units": self.units}
        if self.lat is not None and self.lon is not None:
            params["lat"] = self.lat
            params["lon"] = self.lon
        elif self.city:
            params["q"] = self.city
        else:
            raise ValueError(
                "No weather location configured - set WEATHER_LAT/WEATHER_LON "
                "or WEATHER_CITY in .env"
            )

        response = requests.get(OWM_URL, params=params, timeout=5)
        response.raise_for_status()
        data = response.json()

        return WeatherReading(
            temp=data["main"]["temp"],
            description=data["weather"][0]["description"],
            icon_code=data["weather"][0]["icon"],
            weather_main=data["weather"][0]["main"],
            clouds_pct=data.get("clouds", {}).get("all", 0),
            wind_speed_kmh=_wind_speed_to_kmh(data.get("wind", {}).get("speed", 0.0), self.units),
            fetched_at=time.monotonic(),
        )


class MockWeatherClient:
    """Placeholder weather so the rest of the app is fully testable before
    you have an OpenWeatherMap API key. Makes zero network calls."""

    _MOCK_TEMP_BY_UNITS = {"imperial": 72.0, "metric": 22.0, "standard": 295.0}

    def __init__(self, units: str = "imperial") -> None:
        self.units = units

    def fetch(self) -> WeatherReading:
        return WeatherReading(
            temp=self._MOCK_TEMP_BY_UNITS.get(self.units, 72.0),
            description="clear sky",
            icon_code="01d",
            weather_main="Clear",
            clouds_pct=5,
            wind_speed_kmh=14.0,
            fetched_at=time.monotonic(),
        )


def build_weather_client(settings) -> WeatherClient:
    """Returns the mock client whenever no API key is configured, so 'no key
    yet' is handled structurally instead of relying on callers to remember."""
    if not settings.weather_api_key:
        return MockWeatherClient(units=settings.weather_units)
    return OpenWeatherMapClient(
        api_key=settings.weather_api_key,
        units=settings.weather_units,
        lat=settings.weather_lat,
        lon=settings.weather_lon,
        city=settings.weather_city,
    )
