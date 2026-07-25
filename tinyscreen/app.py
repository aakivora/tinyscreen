"""The main render loop: idle-mode scrolling sentence, or Spotify now-playing
when something's actively playing.

Runs at a fixed frame interval (not a once-a-second tick) since both modes
need smooth scroll animation. Scroll position in both modes is computed from
*elapsed wall-clock time*, not "add N pixels every frame" - that keeps
speed accurate even if a frame is delayed (e.g. by an HTTP call), instead of
the animation stuttering to catch up.

Content refresh happens on its own, much-slower cadence per mode
(settings.weather_poll_interval_seconds, settings.spotify_poll_interval_seconds)
- both because their APIs don't need/want polling every frame, and because
changing content mid-scroll would be a jarring visual glitch.

Idle-mode content keeps refreshing on its own schedule even while Spotify
mode is active, so falling back to idle is instant rather than needing to
"warm up" a sentence first.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime

from tinyscreen.config import Settings
from tinyscreen.display import create_matrix, push_frame
from tinyscreen.renderer import (
    build_scroll_strip,
    build_vertical_scroll_strip,
    color_for_category,
    scroll_frame,
    vertical_scroll_frame,
)
from tinyscreen.sentence import generate_sentence
from tinyscreen.spotify_client import NowPlaying, build_spotify_client, should_show_spotify
from tinyscreen.spotify_renderer import build_ticker_strip, compose_now_playing_frame, download_album_art
from tinyscreen.weather import WeatherReading, build_weather_client

logger = logging.getLogger("tinyscreen")

WEATHER_RETRY_SECONDS = 5.0  # only used when we have no weather at all yet


def run(settings: Settings) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    matrix = create_matrix(settings)
    canvas = matrix.CreateFrameCanvas()
    weather_client = build_weather_client(settings)
    spotify_client = build_spotify_client(settings)

    if settings.idle_layout == "vertical":
        build_idle_strip, render_idle_frame = build_vertical_scroll_strip, vertical_scroll_frame
    else:
        build_idle_strip, render_idle_frame = build_scroll_strip, scroll_frame

    logger.info(
        "tiny-screen starting (backend=%s, idle_layout=%s, spotify=%s)",
        settings.display_backend,
        settings.idle_layout,
        "enabled" if spotify_client else "disabled",
    )

    # Idle-mode state.
    weather: WeatherReading | None = None
    last_weather_poll = 0.0
    idle_strip = None
    idle_strip_started_at = 0.0

    # Spotify-mode state.
    last_spotify_poll = 0.0
    last_playing_at: float | None = None
    current_now_playing: NowPlaying | None = None
    spotify_art_image = None
    spotify_ticker_strip = None
    spotify_strip_started_at = 0.0
    current_mode = "idle"

    try:
        while True:
            now = datetime.now()
            monotonic_now = time.monotonic()

            # --- idle-mode content refresh (always runs, any mode) ---
            elapsed_since_weather_poll = monotonic_now - last_weather_poll
            if weather is None or elapsed_since_weather_poll >= settings.weather_poll_interval_seconds:
                try:
                    weather = weather_client.fetch()
                    last_weather_poll = time.monotonic()
                    generated = generate_sentence(weather, now)
                    logger.info("New sentence [%s]: %s", generated.category, generated.text)
                    color = color_for_category(generated.category)
                    idle_strip = build_idle_strip(generated.text, settings.font_path, color=color)
                    idle_strip_started_at = time.monotonic()
                except Exception:
                    logger.exception("Weather fetch / sentence generation failed")
                    if idle_strip is None:
                        # Nothing to show at all yet - wait and retry rather
                        # than crash on a transient network hiccup.
                        time.sleep(WEATHER_RETRY_SECONDS)
                        continue

            # --- spotify polling ---
            is_playing = current_now_playing is not None
            if spotify_client is not None:
                elapsed_since_spotify_poll = monotonic_now - last_spotify_poll
                if elapsed_since_spotify_poll >= settings.spotify_poll_interval_seconds:
                    last_spotify_poll = time.monotonic()
                    try:
                        now_playing = spotify_client.get_currently_playing()
                    except Exception:
                        logger.exception("Spotify poll failed")
                        now_playing = None

                    is_playing = now_playing is not None
                    if is_playing:
                        last_playing_at = time.monotonic()
                        track_changed = (
                            current_now_playing is None
                            or now_playing.track_id != current_now_playing.track_id
                        )
                        if track_changed:
                            logger.info(
                                "Now playing: %s - %s", now_playing.track_name, now_playing.artist_name
                            )
                            try:
                                spotify_art_image = download_album_art(now_playing.album_art_url)
                                spotify_ticker_strip = build_ticker_strip(
                                    now_playing.track_name, now_playing.artist_name, settings.font_path
                                )
                                spotify_strip_started_at = time.monotonic()
                            except Exception:
                                logger.exception("Failed to download album art")
                                is_playing = False  # can't show Spotify mode without art
                    current_now_playing = now_playing

            # --- mode decision ---
            show_spotify = (
                spotify_client is not None
                and spotify_art_image is not None
                and should_show_spotify(
                    is_playing, last_playing_at, monotonic_now, settings.spotify_fallback_seconds
                )
            )
            new_mode = "spotify" if show_spotify else "idle"
            if new_mode != current_mode:
                logger.info("Switching to %s mode", new_mode)
                current_mode = new_mode

            if show_spotify:
                offset_px = int(
                    (time.monotonic() - spotify_strip_started_at) * settings.scroll_speed_px_per_sec
                )
                frame = compose_now_playing_frame(spotify_art_image, spotify_ticker_strip, offset_px)
            else:
                if idle_strip is None:
                    time.sleep(settings.frame_interval_seconds)
                    continue
                offset_px = int(
                    (time.monotonic() - idle_strip_started_at) * settings.scroll_speed_px_per_sec
                )
                frame = render_idle_frame(idle_strip, offset_px)

            canvas = push_frame(matrix, canvas, frame)
            time.sleep(settings.frame_interval_seconds)
    except KeyboardInterrupt:
        logger.info("Shutting down")
    finally:
        matrix.Clear()
