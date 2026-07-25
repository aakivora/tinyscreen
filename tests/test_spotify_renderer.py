from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch

from PIL import Image

from tinyscreen.renderer import CANVAS_SIZE
from tinyscreen.spotify_renderer import build_ticker_strip, compose_now_playing_frame, download_album_art

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
