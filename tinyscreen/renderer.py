"""Renders the scrolling-sentence idle mode: one line of text scrolling
right-to-left across the full 64x64 canvas, looping seamlessly.

Two-step design, split so the (relatively expensive) text-layout work only
happens once per sentence, not once per frame:

1. `build_scroll_strip()` draws the whole sentence once onto a single wide
   image ("the strip") - as wide as the text itself, plus one screen-width
   of blank gap so the loop doesn't read as the same word instantly
   repeating.
2. `scroll_frame()` is called every animation frame and just crops a 64px
   window out of that pre-rendered strip at the current scroll position -
   cheap enough to call at animation frame rate.
"""

from __future__ import annotations

from PIL import Image, ImageDraw

from tinyscreen.fonts import get_font

CANVAS_SIZE = 64
TEXT_FONT_SIZE = 10
VERTICAL_FONT_SIZE = 8  # smaller than the marquee font - fewer forced mid-word wraps at 64px line width
VERTICAL_LINE_SPACING = 2

BG_COLOR = (0, 0, 0)
TEXT_COLOR = (255, 255, 255)

# Text color by weather category (tinyscreen.sentence.GeneratedSentence.category) -
# a muted palette matching each mood rather than plain white throughout.
CATEGORY_COLORS: dict[str, tuple[int, int, int]] = {
    "hot_sunny": (230, 180, 90),
    "hot_humid": (200, 130, 130),
    "mild_clear": (230, 220, 190),
    "mild_wet": (140, 160, 180),
    "cold_clear": (180, 210, 220),
    "cold_wet": (120, 140, 160),
    "snow": (220, 230, 235),
    "foggy": (160, 165, 170),
    "graphic_clear": (240, 240, 240),
    "changeable": (170, 150, 190),
}


def color_for_category(category: str) -> tuple[int, int, int]:
    return CATEGORY_COLORS.get(category, TEXT_COLOR)


def _crisp_measurer() -> ImageDraw.ImageDraw:
    measurer = ImageDraw.Draw(Image.new("L", (1, 1)))
    measurer.fontmode = "1"
    return measurer


def build_scroll_strip(text: str, font_path, color: tuple[int, int, int] = TEXT_COLOR) -> Image.Image:
    """Draw `text` once onto a strip image sized to fit it exactly, plus a
    trailing gap of blank space equal to one screen width. The gap is what
    makes the loop read as "text ... pause ... text again" instead of the
    end of the sentence smashing directly into its own start.
    """
    font = get_font(font_path, TEXT_FONT_SIZE)

    # Pillow anti-aliases text by default (soft gray edges) - fine at normal
    # sizes, but reads as blurry mush at the handful of pixels a tiny matrix
    # has to work with. "1" rasterizes glyphs as pure on/off pixels instead,
    # which is what a pixel font like Silkscreen is actually designed for.
    left, top, right, bottom = _crisp_measurer().textbbox((0, 0), text, font=font)
    text_width = right - left
    text_height = bottom - top

    gap = CANVAS_SIZE
    strip = Image.new("RGB", (text_width + gap, CANVAS_SIZE), BG_COLOR)
    draw = ImageDraw.Draw(strip)
    draw.fontmode = "1"

    baseline_y = (CANVAS_SIZE - text_height) // 2 - top
    draw.text((-left, baseline_y), text, font=font, fill=color)

    return strip


def scroll_frame(strip: Image.Image, offset_px: int) -> Image.Image:
    """Crop a CANVAS_SIZE-wide window out of `strip` starting at `offset_px`,
    wrapping around to the start of the strip when the window runs past its
    right edge - this is what makes the strip loop instead of running out.
    """
    strip_width = strip.width
    offset = offset_px % strip_width

    frame = Image.new("RGB", (CANVAS_SIZE, CANVAS_SIZE), BG_COLOR)
    x = 0
    remaining = CANVAS_SIZE
    while remaining > 0:
        chunk_width = min(remaining, strip_width - offset)
        chunk = strip.crop((offset, 0, offset + chunk_width, CANVAS_SIZE))
        frame.paste(chunk, (x, 0))
        x += chunk_width
        remaining -= chunk_width
        offset = 0  # any further chunks wrap to the strip's start

    return frame


def _wrap_text(text: str, font, max_width: int) -> list[str]:
    """Greedy word-wrap: add words to the current line until the next one
    would overflow max_width, then start a new line.

    A word that's wider than max_width all by itself (easy to hit on a 64px
    line - "disrespectful" alone is close to that at even a small font size)
    falls back to a hard, character-by-character wrap instead of being
    allowed to overflow past the canvas edge uncropped - with a trailing
    hyphen at the break, so it reads as "word continues" rather than a
    silently truncated/broken word.
    """
    measurer = _crisp_measurer()

    def width_of(s: str) -> int:
        return measurer.textbbox((0, 0), s, font=font)[2]

    lines: list[str] = []
    current = ""

    for word in text.split(" "):
        candidate = f"{current} {word}".strip()
        if width_of(candidate) <= max_width:
            current = candidate
            continue

        if current:
            lines.append(current)
            current = ""

        if width_of(word) <= max_width:
            current = word
            continue

        chunk = ""
        for ch in word:
            # Reserve room for a trailing "-" at every step, in case this
            # character is the one that forces a break.
            if width_of(chunk + ch + "-") <= max_width:
                chunk += ch
            else:
                lines.append(chunk + "-")
                chunk = ch
        current = chunk

    if current:
        lines.append(current)

    return lines


def build_vertical_scroll_strip(
    text: str, font_path, color: tuple[int, int, int] = TEXT_COLOR
) -> Image.Image:
    """Same idea as build_scroll_strip, rotated 90 degrees: word-wrap the
    sentence to the canvas width, stack the lines into a tall image, add a
    one-screen-height gap, and scroll that upward instead of sideways. Lets
    more of the sentence be on-screen and readable at once (several lines
    at a time instead of a handful of characters), at the cost of needing a
    beat to read each screenful before it moves on to the next.
    """
    font = get_font(font_path, VERTICAL_FONT_SIZE)
    lines = _wrap_text(text, font, CANVAS_SIZE)

    measurer = _crisp_measurer()
    line_height = measurer.textbbox((0, 0), "Ag", font=font)[3] + VERTICAL_LINE_SPACING

    gap = CANVAS_SIZE
    strip = Image.new("RGB", (CANVAS_SIZE, line_height * len(lines) + gap), BG_COLOR)
    draw = ImageDraw.Draw(strip)
    draw.fontmode = "1"

    for i, line in enumerate(lines):
        left, top, right, _bottom = draw.textbbox((0, 0), line, font=font)
        x = (CANVAS_SIZE - (right - left)) // 2 - left
        y = i * line_height - top
        draw.text((x, y), line, font=font, fill=color)

    return strip


def vertical_scroll_frame(strip: Image.Image, offset_px: int) -> Image.Image:
    """Vertical counterpart to scroll_frame: crops a CANVAS_SIZE-tall window
    out of `strip`, wrapping around the bottom edge back to the top."""
    strip_height = strip.height
    offset = offset_px % strip_height

    frame = Image.new("RGB", (CANVAS_SIZE, CANVAS_SIZE), BG_COLOR)
    y = 0
    remaining = CANVAS_SIZE
    while remaining > 0:
        chunk_height = min(remaining, strip_height - offset)
        chunk = strip.crop((0, offset, CANVAS_SIZE, offset + chunk_height))
        frame.paste(chunk, (0, y))
        y += chunk_height
        remaining -= chunk_height
        offset = 0

    return frame
