from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch

from PIL import Image

from tinyscreen.renderer import CANVAS_SIZE
from tinyscreen.spotify_renderer import (
    build_ticker_strip,
    compose_now_playing_frame,
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
