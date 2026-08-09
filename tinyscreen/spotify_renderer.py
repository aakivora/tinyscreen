"""Renders the Spotify now-playing frame: album art filling the full 64x64
canvas, with a scrolling "Track - Artist" ticker composited over the bottom
16px.

Two things confirmed empirically rather than assumed: a static single-line
text bar clips or truncates real song titles ("Blinding Lights" ran
off-canvas at a legible font size) - the ticker reuses tinyscreen.renderer's
existing build_scroll_strip/scroll_frame wholesale to fix that, no new
scrolling logic needed. And real album art needs plain LANCZOS resizing
with no pre-blur - see _fit_album_art's docstring for why that differs from
idle mode's art handling.
"""

from __future__ import annotations

from io import BytesIO

import requests
from PIL import Image, ImageOps

from tinyscreen.renderer import CANVAS_SIZE, TEXT_COLOR, build_scroll_strip, scroll_frame

TICKER_HEIGHT = 16
# build_scroll_strip vertically centers text within a full CANVAS_SIZE-tall
# strip, which (measured directly against the actual font) leaves a 5px gap
# between the bottom of the glyphs and the canvas edge if the ticker band is
# cropped from dead-center. Shifting the crop window up by this many pixels
# tightens that to ~2px, sitting the text closer to the bottom edge.
TICKER_VERTICAL_SHIFT = 3


def download_album_art(url: str) -> Image.Image:
    response = requests.get(url, timeout=10)
    response.raise_for_status()
    return Image.open(BytesIO(response.content)).convert("RGB")


def _fit_album_art(art_image: Image.Image) -> Image.Image:
    """Plain LANCZOS resize, deliberately with NO pre-blur - unlike
    tinyscreen.renderer._fit_art, which blurs idle-mode art before
    downsampling.

    That blur exists because idle mode's source images are photographs of
    physical paintings, with real canvas-weave/brushstroke texture that
    aliases into speckly noise when downsampled without it. Spotify album
    art doesn't have that texture - it's clean digital graphics/photography
    - so the same blur just destroys real detail instead of removing noise
    that was never there. Confirmed head-to-head against a real cover (Lady
    Gaga's "The Fame Monster"): the blurred version was an unreadable white
    blob, while plain LANCZOS (matching the tnarla/spotify-matrix reference
    project's own approach) rendered the text and art clearly.
    """
    return ImageOps.fit(art_image, (CANVAS_SIZE, CANVAS_SIZE), Image.LANCZOS, centering=(0.5, 0.5))


def build_ticker_strip(track_name: str, artist_name: str, font_path) -> Image.Image:
    """Call once per track change - see compose_now_playing_frame for the
    cheap per-frame half of this split."""
    return build_scroll_strip(f"{track_name} - {artist_name}", font_path, color=TEXT_COLOR)


def compose_now_playing_frame(
    art_image: Image.Image, ticker_strip: Image.Image, offset_px: int
) -> Image.Image:
    frame = _fit_album_art(art_image)

    # build_scroll_strip always vertically centers its text within a full
    # CANVAS_SIZE-tall strip - the same math as its own baseline_y - so this
    # is where that text actually lands, regardless of TICKER_HEIGHT.
    band_top = (CANVAS_SIZE - TICKER_HEIGHT) // 2 - TICKER_VERTICAL_SHIFT
    ticker_frame = scroll_frame(ticker_strip, offset_px)
    band = ticker_frame.crop((0, band_top, CANVAS_SIZE, band_top + TICKER_HEIGHT))

    # Paste only the ticker's text pixels (not its black background) directly
    # over the album art, no dimming - lets the full art show through behind
    # the text rather than sitting under a darkened bar.
    text_mask = band.convert("L").point(lambda pixel: 255 if pixel > 40 else 0)
    frame.paste(band, (0, CANVAS_SIZE - TICKER_HEIGHT), text_mask)

    return frame
