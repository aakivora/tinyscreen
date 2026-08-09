from pathlib import Path

from tinyscreen.press_to_begin import build_press_to_begin_frame
from tinyscreen.renderer import BG_COLOR, CANVAS_SIZE, TEXT_COLOR

FONT_PATH = Path(__file__).resolve().parent.parent / "assets" / "fonts" / "Silkscreen-Regular.ttf"


def test_build_press_to_begin_frame_is_canvas_sized_rgb():
    frame = build_press_to_begin_frame(FONT_PATH)
    assert frame.size == (CANVAS_SIZE, CANVAS_SIZE)
    assert frame.mode == "RGB"


def test_build_press_to_begin_frame_draws_something():
    frame = build_press_to_begin_frame(FONT_PATH)
    pixels = set(frame.getdata())
    assert TEXT_COLOR in pixels
    assert BG_COLOR in pixels
