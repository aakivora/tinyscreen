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
from PIL import Image, ImageOps, ImageStat

from tinyscreen.renderer import CANVAS_SIZE, TEXT_COLOR, build_scroll_strip, scroll_frame

TICKER_HEIGHT = 16
# build_scroll_strip vertically centers text within a full CANVAS_SIZE-tall
# strip, which (measured directly against the actual font) leaves a 5px gap
# between the bottom of the glyphs and the canvas edge if the ticker band is
# cropped from dead-center. Shifting the crop window up by this many pixels
# tightens that to ~2px, sitting the text closer to the bottom edge.
TICKER_VERTICAL_SHIFT = 3

TICKER_CYCLE_SECONDS = 60.0  # how often the ticker scrolls through - see compute_ticker_offset
# Static readable pause before a track's *first* scroll - longer than the
# repeat hold below since this is most people's only chance to read the
# title before it starts moving.
TICKER_HOLD_SECONDS = 0.9
# Shorter pause before every scroll *after* the first for the same track -
# a full-length hold on every repeat read as an odd stutter once you'd
# already seen the title once, but dropping it to zero made the repeat
# scroll start moving too abruptly.
TICKER_REPEAT_HOLD_SECONDS = 0.2


def compute_ticker_offset(
    elapsed_seconds: float,
    strip_width: int,
    scroll_speed_px_per_sec: float,
    cycle_seconds: float = TICKER_CYCLE_SECONDS,
    hold_seconds: float = TICKER_HOLD_SECONDS,
    repeat_hold_seconds: float = TICKER_REPEAT_HOLD_SECONDS,
) -> int | None:
    """Hold the ticker static at its start (fully readable, offset 0) for
    `hold_seconds` before a track's first scroll, then scroll it through,
    then show nothing at all (just the album art, no text) for the rest of
    `cycle_seconds`, then repeat - holding for the shorter `repeat_hold_seconds`
    before each later scroll of the same track rather than `hold_seconds`
    again. A typical 2-4 minute track then shows the title/artist 2-4 times
    total instead of continuously - less visual clutter for something you're
    not actively trying to read start to finish, per request. The two
    separate hold lengths exist because a full-length hold on every repeat
    read as an odd stutter once you'd already seen the title once, but no
    hold at all on repeats made them start moving too abruptly.

    The hold exists because without it, a new track's ticker starts moving
    the instant it's built - on real hardware, by the time you actually
    see the switch happen (a few seconds of poll interval + album art
    download latency), the first frame you see may already be a few pixels
    into the scroll, cutting off the first letter or two before you ever
    read them.

    Returns None during the blank phase - compose_now_playing_frame skips
    drawing the ticker entirely when this is None, rather than holding it
    static on screen. (During either *hold* phase, offset 0 is returned
    instead - that's deliberately drawn, not blanked, since the point is to
    show the readable start of the text.)

    `cycle_seconds` is a *minimum* period, not a hard cutoff: if the text is
    long enough that a scroll takes longer than `cycle_seconds` (a long
    "Track - Artist" string at the default speed easily can), the scroll
    always runs to completion before going blank rather than being
    truncated partway through and snapping back to the start - confirmed as
    a bug in practice, where a long title would visibly cut off mid-scroll
    and restart from the beginning instead of finishing its pass.

    `strip_width` includes the trailing one-screen-width gap
    build_scroll_strip always adds after the text (see its docstring) - that
    gap exists so idle mode's continuous loop doesn't read as the sentence
    smashing into its own start, but it means "scroll until offset ==
    strip_width" runs a whole screen-width past the point the text has
    actually cleared the screen. Confirmed as a second bug in practice: the
    text would visibly finish exiting, then the loop's *next* copy of the
    text would start sliding back in from the right (scroll_frame's own
    wraparound), and only then get cut off mid-way through that
    reappearance - a visible "second roll" that stops partway through. The
    scroll instead stops as soon as the text itself (strip_width minus that
    trailing CANVAS_SIZE gap) has cleared, not the padded strip.
    """
    scroll_duration = max(strip_width - CANVAS_SIZE, 0) / scroll_speed_px_per_sec

    # The first cycle (hold_seconds + scroll_duration, then blank for
    # whatever's left of cycle_seconds) is handled separately from every
    # cycle after it, since it uses a different, longer hold - otherwise
    # the repeat hold would just stack on top of the first one instead of
    # replacing it.
    first_cycle_length = max(cycle_seconds, hold_seconds + scroll_duration)
    if elapsed_seconds < first_cycle_length:
        if elapsed_seconds < hold_seconds:
            return 0
        elapsed_in_scroll = elapsed_seconds - hold_seconds
        if elapsed_in_scroll < scroll_duration:
            return int(elapsed_in_scroll * scroll_speed_px_per_sec)
        return None

    # Every cycle after the first repeats on its own (shorter) period,
    # holding for repeat_hold_seconds instead of hold_seconds before each
    # scroll - re-basing elapsed time to "time since the first cycle ended"
    # keeps the repeat perfectly periodic instead of drifting.
    elapsed_since_first_cycle = elapsed_seconds - first_cycle_length
    period = max(cycle_seconds, repeat_hold_seconds + scroll_duration)
    elapsed_in_period = elapsed_since_first_cycle % period
    if elapsed_in_period < repeat_hold_seconds:
        return 0
    elapsed_in_scroll = elapsed_in_period - repeat_hold_seconds
    if elapsed_in_scroll < scroll_duration:
        return int(elapsed_in_scroll * scroll_speed_px_per_sec)
    return None


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


def pick_ticker_text_color(art_image: Image.Image) -> tuple[int, int, int]:
    """White text on a dark background, black text on a light one - checked
    against the average brightness of the album art specifically where the
    ticker sits (the bottom band), not the whole cover, since that's the
    only part the text actually overlaps. Call once per track change
    alongside build_ticker_strip, not per frame - the art doesn't change
    color mid-scroll, so there's no need to recompute this every frame.
    """
    fitted = _fit_album_art(art_image)
    bottom_band = fitted.crop((0, CANVAS_SIZE - TICKER_HEIGHT, CANVAS_SIZE, CANVAS_SIZE))
    brightness = ImageStat.Stat(bottom_band.convert("L")).mean[0]
    return (0, 0, 0) if brightness > 128 else TEXT_COLOR


def build_ticker_strip(track_name: str, artist_name: str, font_path) -> Image.Image:
    """Call once per track change - see compose_now_playing_frame for the
    cheap per-frame half of this split.

    Always drawn in TEXT_COLOR (white) regardless of what color the text
    will actually be displayed in - this strip only exists to answer "which
    pixels are glyphs", via a brightness threshold against its own black
    background. That threshold breaks if the glyphs themselves are drawn
    black (nothing to threshold - background and text are both 0), so the
    actual display color gets applied separately, at composite time -
    see compose_now_playing_frame's text_color argument.
    """
    return build_scroll_strip(f"{track_name} - {artist_name}", font_path, color=TEXT_COLOR)


def compose_now_playing_frame(
    art_image: Image.Image,
    ticker_strip: Image.Image,
    offset_px: int | None,
    text_color: tuple[int, int, int] = TEXT_COLOR,
) -> Image.Image:
    frame = _fit_album_art(art_image)

    # None means "blank phase" of the ticker cycle (see
    # compute_ticker_offset) - just the art, no text drawn at all.
    if offset_px is None:
        return frame

    # build_scroll_strip always vertically centers its text within a full
    # CANVAS_SIZE-tall strip - the same math as its own baseline_y - so this
    # is where that text actually lands, regardless of TICKER_HEIGHT.
    band_top = (CANVAS_SIZE - TICKER_HEIGHT) // 2 - TICKER_VERTICAL_SHIFT
    ticker_frame = scroll_frame(ticker_strip, offset_px)
    band = ticker_frame.crop((0, band_top, CANVAS_SIZE, band_top + TICKER_HEIGHT))

    # `band` is always white-on-black (see build_ticker_strip), so this
    # threshold reliably finds the glyph pixels regardless of what color
    # they'll actually be painted - a solid-color rect gets stamped through
    # that shape directly onto the art, no dimming behind it.
    text_mask = band.convert("L").point(lambda pixel: 255 if pixel > 40 else 0)
    colored_text = Image.new("RGB", (CANVAS_SIZE, TICKER_HEIGHT), text_color)
    frame.paste(colored_text, (0, CANVAS_SIZE - TICKER_HEIGHT), text_mask)

    return frame
