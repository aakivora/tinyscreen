from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from tinyscreen.weather import (
    MockWeatherClient,
    OpenWeatherMapClient,
    build_weather_client,
)


def test_mock_weather_client_makes_no_network_calls():
    with patch("tinyscreen.weather.requests.get") as mock_get:
        reading = MockWeatherClient().fetch()
        mock_get.assert_not_called()
    assert reading.temp == 72.0
    assert reading.icon_code == "01d"
    assert reading.weather_main == "Clear"
    assert reading.wind_speed_kmh > 0


def test_mock_weather_client_respects_units():
    assert MockWeatherClient(units="metric").fetch().temp == 22.0
    assert MockWeatherClient(units="imperial").fetch().temp == 72.0


def test_build_weather_client_falls_back_to_mock_without_api_key():
    settings = SimpleNamespace(
        weather_api_key=None,
        weather_units="imperial",
        weather_lat=None,
        weather_lon=None,
        weather_city=None,
    )
    assert isinstance(build_weather_client(settings), MockWeatherClient)


def test_build_weather_client_uses_real_client_with_api_key():
    settings = SimpleNamespace(
        weather_api_key="fake-key",
        weather_units="imperial",
        weather_lat=37.7,
        weather_lon=-122.4,
        weather_city=None,
    )
    assert isinstance(build_weather_client(settings), OpenWeatherMapClient)


def test_openweathermap_client_parses_response_shape():
    fake_response = MagicMock()
    fake_response.raise_for_status.return_value = None
    fake_response.json.return_value = {
        "main": {"temp": 81.3},
        "weather": [{"description": "scattered clouds", "main": "Clouds", "icon": "03d"}],
        "clouds": {"all": 40},
        "wind": {"speed": 5.0},
    }

    with patch("tinyscreen.weather.requests.get", return_value=fake_response) as mock_get:
        client = OpenWeatherMapClient(
            api_key="key", units="imperial", lat=37.7, lon=-122.4, city=None
        )
        reading = client.fetch()

    assert reading.temp == 81.3
    assert reading.description == "scattered clouds"
    assert reading.icon_code == "03d"
    assert reading.weather_main == "Clouds"
    assert reading.clouds_pct == 40
    # imperial units -> OWM reports wind in mph, converted to km/h.
    assert round(reading.wind_speed_kmh, 2) == round(5.0 * 1.60934, 2)

    _, kwargs = mock_get.call_args
    assert kwargs["params"]["lat"] == 37.7
    assert kwargs["params"]["lon"] == -122.4
    assert "q" not in kwargs["params"]


def test_openweathermap_client_converts_metric_wind_from_ms_to_kmh():
    fake_response = MagicMock()
    fake_response.raise_for_status.return_value = None
    fake_response.json.return_value = {
        "main": {"temp": 15.0},
        "weather": [{"description": "clear sky", "main": "Clear", "icon": "01d"}],
        "clouds": {"all": 0},
        "wind": {"speed": 10.0},
    }

    with patch("tinyscreen.weather.requests.get", return_value=fake_response):
        client = OpenWeatherMapClient(
            api_key="key", units="metric", lat=52.37, lon=4.9, city=None
        )
        reading = client.fetch()

    assert round(reading.wind_speed_kmh, 1) == 36.0  # 10 m/s * 3.6


def test_openweathermap_client_uses_city_when_no_lat_lon():
    fake_response = MagicMock()
    fake_response.raise_for_status.return_value = None
    fake_response.json.return_value = {
        "main": {"temp": 50.0},
        "weather": [{"description": "clear sky", "main": "Clear", "icon": "01d"}],
        "clouds": {"all": 0},
        "wind": {"speed": 2.0},
    }

    with patch("tinyscreen.weather.requests.get", return_value=fake_response) as mock_get:
        client = OpenWeatherMapClient(
            api_key="key", units="imperial", lat=None, lon=None, city="Seattle"
        )
        client.fetch()

    _, kwargs = mock_get.call_args
    assert kwargs["params"]["q"] == "Seattle"
    assert "lat" not in kwargs["params"]
