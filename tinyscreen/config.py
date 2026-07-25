"""Central configuration: everything else in the app reads a Settings object
instead of touching os.environ directly, so there's one place that knows
about env var names and defaults.

Two kinds of settings live here, deliberately mixed the same way the
tnarla/spotify-matrix reference project does it:

- Secrets and per-deployment values (API keys, location) come from a
  gitignored `.env` file, loaded with python-dotenv.
- Hardware/display tuning values (brightness, gpio_slowdown, ...) have
  sensible defaults here but are meant to be overridden via command-line
  flags in main.py — those are the ones you'll actually want to tweak
  on the fly once real hardware is plugged in and you're adjusting for
  flicker/brightness by eye.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - dotenv is a normal dependency, but
    # this mirrors the reference project's pattern of not hard-failing if
    # it's ever missing (e.g. a minimal hardware install).
    def load_dotenv(*args, **kwargs) -> None:
        return None


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _env_str(name: str, default: str) -> str:
    return os.environ.get(name, default)


def _env_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    return int(value) if value else default


def _env_float(name: str, default: float) -> float:
    value = os.environ.get(name)
    return float(value) if value else default


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_optional_float(name: str) -> float | None:
    value = os.environ.get(name)
    return float(value) if value else None


@dataclass
class Settings:
    # Which RGBMatrix backend to import - see tinyscreen/display.py.
    display_backend: str = "emulator"

    # Matrix/panel hardware options. Field-by-field explanations live in
    # tinyscreen/display.py, which is where these actually get used.
    rows: int = 64
    cols: int = 64
    chain_length: int = 1
    parallel: int = 1
    hardware_mapping: str = "adafruit-hat"
    brightness: int = 65
    gpio_slowdown: int = 2
    pwm_bits: int = 11
    limit_refresh_rate_hz: int = 120
    disable_hardware_pulsing: bool = False

    # Weather (OpenWeatherMap). weather_api_key is None until you sign up -
    # tinyscreen/weather.py falls back to mock data whenever it's unset.
    weather_api_key: str | None = None
    weather_units: str = "imperial"  # imperial=F, metric=C, standard=Kelvin
    weather_lat: float | None = None
    weather_lon: float | None = None
    weather_city: str | None = None
    # Also controls how often the idle-mode sentence regenerates - each
    # regeneration requires a fresh weather reading anyway.
    weather_poll_interval_seconds: int = 900  # 15 minutes

    # Idle-mode scrolling text.
    idle_layout: str = "horizontal"  # "horizontal" (marquee) or "vertical" (credits-style)
    scroll_speed_px_per_sec: float = 20.0
    frame_interval_seconds: float = 0.04  # ~25fps

    # Spotify. spotify_client_id/secret are None until you register an app -
    # tinyscreen/spotify_client.py's build_spotify_client() returns None
    # (idle mode only, no polling) whenever they're unset, the same
    # "degrades gracefully without secrets" pattern build_weather_client()
    # already uses.
    spotify_client_id: str | None = None
    spotify_client_secret: str | None = None
    # 8901, not 8888 - the RGBMatrixEmulator browser view already owns 8888
    # (see emulator_config.json), and this needs its own port free during
    # the one-time login even while the emulator's running.
    spotify_redirect_uri: str = "http://127.0.0.1:8901/callback"
    spotify_token_cache_path: Path = PROJECT_ROOT / ".cache" / "spotify_token.json"
    spotify_poll_interval_seconds: float = 5.0
    spotify_fallback_seconds: float = 90.0  # how long to stay in Spotify mode after playback stops

    # Rendering.
    font_path: Path = PROJECT_ROOT / "assets" / "fonts" / "Silkscreen-Regular.ttf"


def load_settings(env_file: Path | None = None) -> Settings:
    """Load .env (if present) and build a Settings object from the
    environment, falling back to defaults for anything unset."""
    load_dotenv(dotenv_path=env_file or (PROJECT_ROOT / ".env"))

    return Settings(
        display_backend=_env_str("TINYSCREEN_DISPLAY_BACKEND", "emulator"),
        rows=_env_int("MATRIX_ROWS", 64),
        cols=_env_int("MATRIX_COLS", 64),
        chain_length=_env_int("MATRIX_CHAIN_LENGTH", 1),
        parallel=_env_int("MATRIX_PARALLEL", 1),
        hardware_mapping=_env_str("MATRIX_HARDWARE_MAPPING", "adafruit-hat"),
        brightness=_env_int("MATRIX_BRIGHTNESS", 65),
        gpio_slowdown=_env_int("MATRIX_GPIO_SLOWDOWN", 2),
        pwm_bits=_env_int("MATRIX_PWM_BITS", 11),
        limit_refresh_rate_hz=_env_int("MATRIX_LIMIT_REFRESH_RATE_HZ", 120),
        disable_hardware_pulsing=_env_bool("MATRIX_DISABLE_HARDWARE_PULSING", False),
        weather_api_key=os.environ.get("OPENWEATHERMAP_API_KEY") or None,
        weather_units=_env_str("WEATHER_UNITS", "imperial"),
        weather_lat=_env_optional_float("WEATHER_LAT"),
        weather_lon=_env_optional_float("WEATHER_LON"),
        weather_city=os.environ.get("WEATHER_CITY") or None,
        weather_poll_interval_seconds=_env_int("WEATHER_POLL_INTERVAL_SECONDS", 900),
        idle_layout=_env_str("IDLE_LAYOUT", "horizontal"),
        scroll_speed_px_per_sec=_env_float("SCROLL_SPEED_PX_PER_SEC", 20.0),
        frame_interval_seconds=_env_float("FRAME_INTERVAL_SECONDS", 0.04),
        spotify_client_id=os.environ.get("SPOTIFY_CLIENT_ID") or None,
        spotify_client_secret=os.environ.get("SPOTIFY_CLIENT_SECRET") or None,
        spotify_redirect_uri=_env_str("SPOTIFY_REDIRECT_URI", "http://127.0.0.1:8901/callback"),
        spotify_token_cache_path=Path(
            _env_str("SPOTIFY_TOKEN_CACHE_PATH", str(PROJECT_ROOT / ".cache" / "spotify_token.json"))
        ),
        spotify_poll_interval_seconds=_env_float("SPOTIFY_POLL_INTERVAL_SECONDS", 5.0),
        spotify_fallback_seconds=_env_float("SPOTIFY_FALLBACK_SECONDS", 90.0),
        font_path=Path(
            _env_str(
                "FONT_PATH", str(PROJECT_ROOT / "assets" / "fonts" / "Silkscreen-Regular.ttf")
            )
        ),
    )
