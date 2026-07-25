from pathlib import Path

from tinyscreen.renderer import (
    CANVAS_SIZE,
    CATEGORY_COLORS,
    TEXT_COLOR,
    build_scroll_strip,
    build_vertical_scroll_strip,
    color_for_category,
    scroll_frame,
    vertical_scroll_frame,
)

FONT_PATH = Path(__file__).resolve().parent.parent / "assets" / "fonts" / "Silkscreen-Regular.ttf"


def test_build_scroll_strip_is_canvas_tall_and_wider_than_canvas():
    strip = build_scroll_strip("Hello, tiny screen!", FONT_PATH)
    assert strip.height == CANVAS_SIZE
    assert strip.width > CANVAS_SIZE
    assert strip.mode == "RGB"


def test_build_scroll_strip_includes_one_screen_width_gap():
    # The strip is text width + one CANVAS_SIZE gap (see renderer.py docstring)
    # - a single-character string makes the text-width contribution small
    # and predictable enough to bound the gap's presence.
    strip = build_scroll_strip("a", FONT_PATH)
    assert strip.width >= CANVAS_SIZE


def test_scroll_frame_returns_canvas_sized_image():
    strip = build_scroll_strip("Some scrolling text", FONT_PATH)
    frame = scroll_frame(strip, offset_px=0)
    assert frame.size == (CANVAS_SIZE, CANVAS_SIZE)
    assert frame.mode == "RGB"


def test_scroll_frame_wraps_around_the_strip():
    strip = build_scroll_strip("Wraparound test", FONT_PATH)
    # An offset that lands a canvas-width away from the strip's end forces
    # the wraparound branch (pasting a chunk from the strip's start).
    offset_at_wrap = strip.width - CANVAS_SIZE // 2
    frame = scroll_frame(strip, offset_px=offset_at_wrap)
    assert frame.size == (CANVAS_SIZE, CANVAS_SIZE)


def test_scroll_frame_offset_wraps_modulo_strip_width():
    strip = build_scroll_strip("Modulo test", FONT_PATH)
    frame_a = scroll_frame(strip, offset_px=5)
    frame_b = scroll_frame(strip, offset_px=5 + strip.width)
    assert list(frame_a.getdata()) == list(frame_b.getdata())


def test_build_vertical_scroll_strip_is_canvas_wide_and_wraps_long_text():
    long_sentence = (
        "22 and bright afternoon in AMS. Feels like a Hockney painting. "
        "The wind is mild, if a little disrespectful. Word of the day: polderen."
    )
    strip = build_vertical_scroll_strip(long_sentence, FONT_PATH)
    assert strip.width == CANVAS_SIZE
    # A sentence this long can't fit on one screen-height of lines - the
    # wrap should produce enough lines to push the strip well past a single
    # canvas height (line height plus the trailing one-screen gap).
    assert strip.height > CANVAS_SIZE * 2


def test_vertical_scroll_frame_returns_canvas_sized_image():
    strip = build_vertical_scroll_strip("Some wrapped text for testing", FONT_PATH)
    frame = vertical_scroll_frame(strip, offset_px=0)
    assert frame.size == (CANVAS_SIZE, CANVAS_SIZE)


def test_vertical_scroll_frame_offset_wraps_modulo_strip_height():
    strip = build_vertical_scroll_strip("Modulo test for vertical scrolling", FONT_PATH)
    frame_a = vertical_scroll_frame(strip, offset_px=5)
    frame_b = vertical_scroll_frame(strip, offset_px=5 + strip.height)
    assert list(frame_a.getdata()) == list(frame_b.getdata())


# --- category colors -----------------------------------------------------


def test_color_for_category_matches_the_requested_palette():
    assert color_for_category("hot_sunny") == (230, 180, 90)
    assert color_for_category("snow") == (220, 230, 235)
    assert color_for_category("changeable") == (170, 150, 190)


def test_color_for_category_falls_back_to_default_text_color_for_unknown():
    assert color_for_category("not-a-real-category") == TEXT_COLOR


def test_build_scroll_strip_draws_text_in_the_requested_color():
    color = CATEGORY_COLORS["hot_sunny"]
    strip = build_scroll_strip("Hi", FONT_PATH, color=color)
    assert color in set(strip.getdata())
    assert TEXT_COLOR not in set(strip.getdata())


def test_build_vertical_scroll_strip_draws_text_in_the_requested_color():
    color = CATEGORY_COLORS["cold_wet"]
    strip = build_vertical_scroll_strip("Hi there", FONT_PATH, color=color)
    assert color in set(strip.getdata())
    assert TEXT_COLOR not in set(strip.getdata())
