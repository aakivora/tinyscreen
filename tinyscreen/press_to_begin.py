"""Alternate default/idle screen: a static "press play to begin" prompt, in
place of the full weather/Spotify sentence idle mode - run via main2.py
instead of main.py when you want this simpler screen instead.
"""

from __future__ import annotations

import logging
import time

from PIL import Image, ImageDraw

from tinyscreen.config import Settings
from tinyscreen.display import create_matrix, push_frame
from tinyscreen.fonts import get_font
from tinyscreen.renderer import BG_COLOR, CANVAS_SIZE, TEXT_COLOR, TEXT_FONT_SIZE

logger = logging.getLogger("tinyscreen")

LINE_SPACING = 6  # doubled from the original 3px, per request
ICON_SIZE = 10
TRIANGLE_WIDTH = 8
BAR_WIDTH = 2
BAR_GAP = 2  # gap between the two vertical pause bars
GROUP_GAP = 4  # gap between the play triangle and the pause bars


def _crisp_measurer() -> ImageDraw.ImageDraw:
    measurer = ImageDraw.Draw(Image.new("L", (1, 1)))
    measurer.fontmode = "1"
    return measurer


def _draw_play_icon(draw: ImageDraw.ImageDraw, center_x: int, center_y: int, size: int) -> None:
    """A play triangle followed by two vertical bars (like a play/pause
    media control glyph), centered as one group at (center_x, center_y)."""
    half = size // 2
    group_width = TRIANGLE_WIDTH + GROUP_GAP + BAR_WIDTH * 2 + BAR_GAP
    left = center_x - group_width // 2

    draw.polygon(
        [
            (left, center_y - half),
            (left, center_y + half),
            (left + TRIANGLE_WIDTH, center_y),
        ],
        fill=TEXT_COLOR,
    )

    bar1_left = left + TRIANGLE_WIDTH + GROUP_GAP
    draw.rectangle(
        (bar1_left, center_y - half, bar1_left + BAR_WIDTH - 1, center_y + half), fill=TEXT_COLOR
    )
    bar2_left = bar1_left + BAR_WIDTH + BAR_GAP
    draw.rectangle(
        (bar2_left, center_y - half, bar2_left + BAR_WIDTH - 1, center_y + half), fill=TEXT_COLOR
    )


def build_press_to_begin_frame(font_path) -> Image.Image:
    """Three lines, center-aligned both horizontally and as a block:
    "PRESS", a play-triangle icon, "TO BEGIN" - same font/size as the
    Spotify ticker (tinyscreen.renderer.TEXT_FONT_SIZE), per request.
    """
    font = get_font(font_path, TEXT_FONT_SIZE)
    measurer = _crisp_measurer()

    lines: list[str | None] = ["PRESS", None, "TO BEGIN"]  # None = play icon

    heights = []
    for line in lines:
        if line is None:
            heights.append(ICON_SIZE)
        else:
            bbox = measurer.textbbox((0, 0), line, font=font)
            heights.append(bbox[3] - bbox[1])

    total_height = sum(heights) + LINE_SPACING * (len(lines) - 1)
    y = (CANVAS_SIZE - total_height) // 2

    frame = Image.new("RGB", (CANVAS_SIZE, CANVAS_SIZE), BG_COLOR)
    draw = ImageDraw.Draw(frame)
    draw.fontmode = "1"

    for line, height in zip(lines, heights):
        if line is None:
            _draw_play_icon(draw, CANVAS_SIZE // 2, y + height // 2, ICON_SIZE)
        else:
            left, top, right, _bottom = measurer.textbbox((0, 0), line, font=font)
            x = (CANVAS_SIZE - (right - left)) // 2 - left
            draw.text((x, y - top), line, font=font, fill=TEXT_COLOR)
        y += height + LINE_SPACING

    return frame


def run(settings: Settings) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    # Same lesson as tinyscreen.app.run: load the font before touching the
    # matrix hardware - rgbmatrix's init breaks subsequent font-file opens
    # on real hardware (confirmed empirically during hardware bring-up).
    get_font(settings.font_path, TEXT_FONT_SIZE)

    matrix = create_matrix(settings)
    canvas = matrix.CreateFrameCanvas()

    logger.info("tiny-screen (press-to-begin) starting (backend=%s)", settings.display_backend)

    frame = build_press_to_begin_frame(settings.font_path)
    canvas = push_frame(matrix, canvas, frame)

    # Nothing animates, so there's no need to keep pushing frames - a single
    # swap is enough, the hardware (or emulator) keeps displaying it.
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Shutting down")
    finally:
        matrix.Clear()
