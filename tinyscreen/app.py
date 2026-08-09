"""The main render loop: idle-mode scrolling sentence, or Spotify now-playing
when something's actively playing.

The render loop itself only ever does cheap, local work (compute a scroll
offset, crop a pre-built strip, push a frame) - it never blocks on a network
call. Weather and Spotify polling both run on their own background threads,
each updating a small shared state dict under a lock; the render loop just
reads whatever's currently there. This matters because both APIs are
genuinely slow sometimes (a few hundred ms to a couple seconds), and earlier
versions of this loop called them directly inline - which meant every poll
(every 5s for Spotify) froze the on-panel scroll animation for the duration
of the HTTP request, a visible stutter that was very noticeable on real
hardware.

Runs at a fixed frame interval (not a once-a-second tick) since both modes
need smooth scroll animation. Scroll position in both modes is computed from
*elapsed wall-clock time*, not "add N pixels every frame" - that keeps
speed accurate even if a frame is delayed, instead of the animation
stuttering to catch up.

Idle-mode content keeps refreshing on its own schedule even while Spotify
mode is active, so falling back to idle is instant rather than needing to
"warm up" a sentence first.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime

from tinyscreen.config import Settings
from tinyscreen.display import create_matrix, push_frame
from tinyscreen.fonts import get_font
from tinyscreen.press_to_begin import build_press_to_begin_frame
from tinyscreen.renderer import (
    TEXT_FONT_SIZE,
    VERTICAL_FONT_SIZE,
    build_scroll_strip,
    build_vertical_scroll_strip,
    color_for_category,
    scroll_frame,
    vertical_scroll_frame,
)
from tinyscreen.sentence import generate_sentence
from tinyscreen.spotify_client import build_spotify_client, should_show_spotify
from tinyscreen.spotify_renderer import (
    build_ticker_strip,
    compose_now_playing_frame,
    compute_ticker_offset,
    download_album_art,
    pick_ticker_text_color,
)
from tinyscreen.weather import build_weather_client

logger = logging.getLogger("tinyscreen")

WEATHER_RETRY_SECONDS = 5.0  # only used when we have no weather at all yet


def run(settings: Settings) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    # Load (and lru_cache) both font sizes before touching the matrix
    # hardware. On real hardware, rgbmatrix's initialization locks memory
    # for jitter-free GPIO timing, which breaks subsequent font-file opens
    # in the same process (confirmed empirically: font loading alone works,
    # matrix init alone works, matrix-then-font reliably fails with "cannot
    # open resource"). Loading fonts first means they're already cached by
    # the time that happens, so nothing needs to touch the file afterward.
    get_font(settings.font_path, TEXT_FONT_SIZE)
    get_font(settings.font_path, VERTICAL_FONT_SIZE)

    matrix = create_matrix(settings)
    canvas = matrix.CreateFrameCanvas()
    weather_client = build_weather_client(settings)
    spotify_client = build_spotify_client(settings)

    if settings.idle_layout == "vertical":
        build_idle_strip, render_idle_frame = build_vertical_scroll_strip, vertical_scroll_frame
    else:
        build_idle_strip, render_idle_frame = build_scroll_strip, scroll_frame

    logger.info(
        "tiny-screen starting (backend=%s, idle_mode=%s, idle_layout=%s, spotify=%s)",
        settings.display_backend,
        settings.idle_mode,
        settings.idle_layout,
        "enabled" if spotify_client else "disabled",
    )

    # The static screen doesn't need weather at all - built once up front,
    # shown directly whenever idle mode is active, no polling thread.
    press_to_begin_frame = (
        build_press_to_begin_frame(settings.font_path) if settings.idle_mode == "press_to_begin" else None
    )

    state_lock = threading.Lock()
    stop_event = threading.Event()

    idle_state = {"strip": None, "strip_started_at": 0.0}
    spotify_state = {
        "current_now_playing": None,
        "is_playing": False,
        "last_playing_at": None,
        "art_image": None,
        "ticker_strip": None,
        "text_color": (255, 255, 255),
        "strip_started_at": 0.0,
    }

    def poll_weather() -> None:
        while not stop_event.is_set():
            try:
                weather = weather_client.fetch()
                generated = generate_sentence(weather, datetime.now())
                logger.info("New sentence [%s]: %s", generated.category, generated.text)
                color = color_for_category(generated.category)
                strip = build_idle_strip(generated.text, settings.font_path, color=color)
                with state_lock:
                    idle_state["strip"] = strip
                    idle_state["strip_started_at"] = time.monotonic()
                wait_seconds = settings.weather_poll_interval_seconds
            except Exception:
                logger.exception("Weather fetch / sentence generation failed")
                # Only retry quickly if we have nothing to show at all yet -
                # once there's a strip on screen, a transient failure just
                # means "try again next normal cycle" rather than hammering
                # the API.
                with state_lock:
                    have_strip = idle_state["strip"] is not None
                wait_seconds = settings.weather_poll_interval_seconds if have_strip else WEATHER_RETRY_SECONDS
            stop_event.wait(wait_seconds)

    def poll_spotify() -> None:
        while not stop_event.is_set():
            try:
                now_playing = spotify_client.get_currently_playing()
            except Exception:
                logger.exception("Spotify poll failed")
                now_playing = None

            with state_lock:
                previous = spotify_state["current_now_playing"]

            is_playing = now_playing is not None
            if is_playing:
                track_changed = previous is None or now_playing.track_id != previous.track_id
                if track_changed:
                    logger.info(
                        "Now playing: %s - %s", now_playing.track_name, now_playing.artist_name
                    )
                    try:
                        art_image = download_album_art(now_playing.album_art_url)
                        text_color = pick_ticker_text_color(art_image)
                        ticker_strip = build_ticker_strip(
                            now_playing.track_name, now_playing.artist_name, settings.font_path
                        )
                        with state_lock:
                            spotify_state["art_image"] = art_image
                            spotify_state["ticker_strip"] = ticker_strip
                            spotify_state["text_color"] = text_color
                            spotify_state["strip_started_at"] = time.monotonic()
                    except Exception:
                        logger.exception("Failed to download album art")
                        is_playing = False  # can't show Spotify mode without art

            with state_lock:
                spotify_state["current_now_playing"] = now_playing
                spotify_state["is_playing"] = is_playing
                if is_playing:
                    spotify_state["last_playing_at"] = time.monotonic()

            stop_event.wait(settings.spotify_poll_interval_seconds)

    if press_to_begin_frame is None:
        threading.Thread(target=poll_weather, daemon=True).start()
    if spotify_client is not None:
        threading.Thread(target=poll_spotify, daemon=True).start()

    current_mode = "idle"

    try:
        while True:
            with state_lock:
                idle_strip = idle_state["strip"]
                idle_strip_started_at = idle_state["strip_started_at"]
                spotify_is_playing = spotify_state["is_playing"]
                spotify_last_playing_at = spotify_state["last_playing_at"]
                spotify_art_image = spotify_state["art_image"]
                spotify_ticker_strip = spotify_state["ticker_strip"]
                spotify_text_color = spotify_state["text_color"]
                spotify_strip_started_at = spotify_state["strip_started_at"]

            monotonic_now = time.monotonic()

            show_spotify = (
                spotify_client is not None
                and spotify_art_image is not None
                and should_show_spotify(
                    spotify_is_playing,
                    spotify_last_playing_at,
                    monotonic_now,
                    settings.spotify_fallback_seconds,
                )
            )
            new_mode = "spotify" if show_spotify else "idle"
            if new_mode != current_mode:
                logger.info("Switching to %s mode", new_mode)
                current_mode = new_mode

            if show_spotify:
                elapsed = time.monotonic() - spotify_strip_started_at
                offset_px = compute_ticker_offset(
                    elapsed,
                    spotify_ticker_strip.width,
                    settings.scroll_speed_px_per_sec,
                    settings.spotify_ticker_cycle_seconds,
                    settings.spotify_ticker_hold_seconds,
                    settings.spotify_ticker_repeat_hold_seconds,
                )
                frame = compose_now_playing_frame(
                    spotify_art_image, spotify_ticker_strip, offset_px, text_color=spotify_text_color
                )
            elif press_to_begin_frame is not None:
                frame = press_to_begin_frame
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
        stop_event.set()
        matrix.Clear()
