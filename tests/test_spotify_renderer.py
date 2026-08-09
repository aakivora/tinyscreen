from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch

from PIL import Image

from tinyscreen.renderer import CANVAS_SIZE
from tinyscreen.spotify_renderer import (
    build_ticker_strip,
    compose_now_playing_frame,
    compute_ticker_offset,
    download_album_art,
    pick_ticker_text_color,
)

FONT_PATH = Path(__file__).resolve().parent.parent / "assets" / "fonts" / "Silkscreen-Regular.ttf"


def test_build_ticker_strip_is_canvas_tall():
    strip = build_ticker_strip("Blinding Lights", "The Weeknd", FONT_PATH)
    assert strip.height == CANVAS_SIZE
    assert strip.width > CANVAS_SIZE


def test_compose_now_playing_frame_returns_canvas_sized_rgb_image():
    art = Image.new("RGB", (300, 300), (80, 40, 40))
    ticker = build_ticker_strip("Some Song", "Some Artist", FONT_PATH)

    frame = compose_now_playing_frame(art, ticker, offset_px=0)

    assert frame.size == (CANVAS_SIZE, CANVAS_SIZE)
    assert frame.mode == "RGB"


def test_compose_now_playing_frame_handles_non_square_art():
    art = Image.new("RGB", (1000, 50), (10, 10, 10))
    ticker = build_ticker_strip("Wide Art Test", "Artist", FONT_PATH)

    frame = compose_now_playing_frame(art, ticker, offset_px=25)

    assert frame.size == (CANVAS_SIZE, CANVAS_SIZE)


def test_pick_ticker_text_color_is_black_on_light_art():
    light_art = Image.new("RGB", (300, 300), (230, 210, 60))
    assert pick_ticker_text_color(light_art) == (0, 0, 0)


def test_pick_ticker_text_color_is_white_on_dark_art():
    dark_art = Image.new("RGB", (300, 300), (20, 25, 45))
    assert pick_ticker_text_color(dark_art) == (255, 255, 255)


def test_compose_now_playing_frame_black_text_is_actually_visible():
    # Regression test: an earlier version generated the ticker strip itself
    # in the target display color, which silently broke black text - the
    # mask threshold that finds "which pixels are glyphs" compared strip
    # brightness against the strip's own black background, so black-on-black
    # glyphs were indistinguishable from background and the mask found
    # nothing at all. Confirm black text actually produces black pixels
    # somewhere in the rendered frame, not just "doesn't crash".
    art = Image.new("RGB", (300, 300), (230, 210, 60))  # light art
    ticker = build_ticker_strip("Some Song", "Some Artist", FONT_PATH)

    frame = compose_now_playing_frame(art, ticker, offset_px=0, text_color=(0, 0, 0))

    assert (0, 0, 0) in set(frame.getdata())


def test_compute_ticker_offset_scrolls_at_the_start_of_the_cycle():
    # strip_width=200, speed=20px/s -> scroll_duration=10s, so 3s in should
    # be mid-scroll at 3*20=60px. hold_seconds=0 isolates pure scroll timing
    # from the separate hold-phase behavior, tested below.
    assert (
        compute_ticker_offset(
            3.0, strip_width=200, scroll_speed_px_per_sec=20.0, cycle_seconds=60.0, hold_seconds=0.0
        )
        == 60
    )


def test_compute_ticker_offset_is_none_after_the_scroll_finishes():
    # Same strip/speed as above (10s scroll), but 30s into a 60s cycle -
    # well past the scroll - should be the blank phase.
    assert (
        compute_ticker_offset(
            30.0, strip_width=200, scroll_speed_px_per_sec=20.0, cycle_seconds=60.0, hold_seconds=0.0
        )
        is None
    )


def test_compute_ticker_offset_lets_a_long_scroll_finish_past_the_cycle_length():
    # Regression test: strip_width=2000 at 20px/s takes 100s to fully
    # scroll - longer than the 60s cycle. The old implementation used
    # cycle_seconds as a hard cutoff, so at 65s in it would wrap
    # (65 % 60 = 5) and snap back to offset=100 - a visible jump backward
    # mid-scroll instead of finishing the pass. It should still be
    # mid-scroll, uninterrupted, at the "actual" offset for elapsed=65.
    assert (
        compute_ticker_offset(
            65.0, strip_width=2000, scroll_speed_px_per_sec=20.0, cycle_seconds=60.0, hold_seconds=0.0
        )
        == 1300
    )


def test_compute_ticker_offset_scrolls_again_each_new_cycle():
    # 63s elapsed on a 60s cycle wraps to 3s into cycle #2 - should scroll
    # again exactly like 3s did in cycle #1, not stay blank forever.
    assert (
        compute_ticker_offset(
            63.0, strip_width=200, scroll_speed_px_per_sec=20.0, cycle_seconds=60.0, hold_seconds=0.0
        )
        == 60
    )


def test_compute_ticker_offset_holds_at_zero_before_scrolling():
    # hold_seconds=2 -> anything before t=2 should be the static, fully
    # readable start of the text (offset 0), not already moving.
    assert (
        compute_ticker_offset(
            1.0, strip_width=200, scroll_speed_px_per_sec=20.0, cycle_seconds=60.0, hold_seconds=2.0
        )
        == 0
    )


def test_compute_ticker_offset_scrolls_after_the_hold_elapses():
    # hold_seconds=2, scroll_duration=10 (200/20) - at t=5 that's 3s into
    # the scroll phase (5 - 2), so offset should be 3*20=60, not measured
    # from t=0 directly.
    assert (
        compute_ticker_offset(
            5.0, strip_width=200, scroll_speed_px_per_sec=20.0, cycle_seconds=60.0, hold_seconds=2.0
        )
        == 60
    )


def test_compose_now_playing_frame_with_none_offset_draws_no_ticker():
    # offset_px=None is the ticker's blank phase - just the album art, no
    # text pixels at all (as opposed to holding the ticker static onscreen).
    art = Image.new("RGB", (300, 300), (230, 210, 60))
    ticker = build_ticker_strip("Some Song", "Some Artist", FONT_PATH)

    frame = compose_now_playing_frame(art, ticker, offset_px=None, text_color=(0, 0, 0))

    assert (0, 0, 0) not in set(frame.getdata())


def test_download_album_art_returns_rgb_image():
    source = Image.new("RGB", (50, 50), (200, 100, 50))
    buffer = BytesIO()
    source.save(buffer, format="PNG")

    response = MagicMock()
    response.raise_for_status.return_value = None
    response.content = buffer.getvalue()

    with patch("tinyscreen.spotify_renderer.requests.get", return_value=response) as mock_get:
        result = download_album_art("https://example.com/art.png")

    assert result.mode == "RGB"
    assert result.size == (50, 50)
    mock_get.assert_called_once()
