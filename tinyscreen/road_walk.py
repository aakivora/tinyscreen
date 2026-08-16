"""The "we make the road by walking" idle mode: a tiny stick figure wanders
a curved, randomized path from one edge of the board to another every
`road_walk_interval_seconds`, leaving a glowing road (dim road-bed + bright
dashed centerline) behind it, then the whole road fades to black until the
next walk.

Deliberately takes a `dt` (seconds-per-step) argument everywhere instead of
reading time.monotonic() anywhere in this module - every other animation in
this app (idle scroll offset, Spotify ticker) computes "elapsed since some
started_at timestamp," which keeps advancing in real time no matter which
mode is actually on screen. This mode needs the opposite: the walk must
*pause* while Spotify (or another idle mode) is being shown and resume
exactly where it left off, not skip ahead or lose progress off-screen.
app.py's render loop already runs at a fixed cadence and only calls
step_road_walk() on frames where this mode is actually the one rendering -
passing that fixed frame interval as dt gives the pause-for-free, and as a
side effect makes every function here testable with plain floats, no clock
mocking needed at all.

State is a plain dict (matching app.py's existing idle_state/spotify_state
convention) moving through four phases: "waiting" (board dark, timer
counting up to the next walk) -> "walking" (the walk itself, sampling one
path point per frame) -> "signature" (walker gone, road holds solid, the
"WE MAKE THE ROAD BY WALKING" text flashes on top of it) -> "fading" (road
and text dim to black together) -> back to "waiting". The timer for the
next walk only starts once "fading" completes, so a slow walk's fade-out
never overlaps the next walk starting.
"""

from __future__ import annotations

import colorsys
import math
import random
from typing import Any

from PIL import Image, ImageDraw

from tinyscreen.fonts import get_font
from tinyscreen.renderer import CANVAS_SIZE

# --- walker body proportions, in "grid units" (== native board pixels) ---
# Exact formulas and constants as specified against a reference prototype -
# not derived/guessed. Total figure height (head top to feet) is
# HEAD_Y_OFFSET + HEAD_RADIUS =~ 4.7 grid units, confirmed against the
# reference as "~7% of board height" (4.7/64 =~ 7.3%) - a small figure by
# design, legible without dominating the board.
HIP_Y_OFFSET = 1.8
SHOULDER_Y_OFFSET = 3.2
HEAD_Y_OFFSET = 4.1
HEAD_RADIUS = 0.6
LEG_SWING_FACTOR = 0.85
ARM_SWING_FACTOR = 0.6
ARM_Y_OFFSET = 1.3  # hand y = shoulderY + this
LEAN_FACTOR = 0.12  # forward lean of shoulder/head, in x
LIMB_WIDTH = 0.42  # legs + torso stroke width
ARM_WIDTH = 0.3
GAIT_PHASE_PER_PIXEL = 1.0  # gaitPhase += distance_moved * this - ties stride to distance, not wall-clock time
WALKER_COLOR = (255, 255, 255)

# Scales the walker up at DRAW time only (around its own px,py anchor) -
# compute_gait_pose() itself stays an unscaled, exact transcription of the
# reference formulas above. Confirmed on real hardware that the literal
# reference proportions were too small to read as a stick figure at all
# (limbs collapsing to sub-pixel-wide antialiased smudges) - this is a
# separate, purely visual tuning knob for legibility, not a correction to
# the reference math itself.
WALKER_RENDER_SCALE = 2.2

# --- road/centerline rendering, in grid units - exact values from the
# reference prototype (HSLA road-bed/centerline + dash pattern) ---
ROAD_BED_SATURATION = 0.55
ROAD_BED_LIGHTNESS = 0.24
ROAD_BED_WIDTH_GU = 0.9
CENTERLINE_SATURATION = 0.85
CENTERLINE_LIGHTNESS = 0.62
CENTERLINE_WIDTH_GU = 0.16
CENTERLINE_DASH_ON_GU = 0.45
CENTERLINE_DASH_OFF_GU = 0.4

# Working canvas is this many times CANVAS_SIZE, drawn with normal PIL
# lines/ellipses (no native antialiasing), then LANCZOS-downsampled to
# native resolution - the same "supersample then downsample" trick used
# nowhere else in this codebase yet, needed here because grid-unit stroke
# widths like 0.16 are sub-pixel at native resolution and would either
# vanish or look jagged without it.
SUPERSAMPLE = 4

# Facing (-1/1) is derived from a smoothed (EMA) horizontal-velocity sign
# rather than the raw per-frame value, so a path that dips briefly near-
# vertical doesn't flicker the sprite left/right every frame. Tuned by
# feel, not specified - deadzone sized to the ~0.3px-per-frame dx a typical
# walk speed produces.
FACING_EMA_ALPHA = 0.15
FACING_DEADZONE = 0.03

# --- "signature" phase: the road holds solid once the walker exits, then
# this text flashes on top of it before both fade to black together ---
SIGNATURE_LINES = ("WE MAKE", "THE ROAD", "BY WALKING")
SIGNATURE_FONT_SIZE = 6  # ~6-7% of CANVAS_SIZE per line, per spec
SIGNATURE_LINE_SPACING = 1
SIGNATURE_TEXT_COLOR = (255, 255, 255)
SIGNATURE_OUTLINE_COLOR = (0, 0, 0)
SIGNATURE_STROKE_WIDTH = 1  # dark outline behind each line, for legibility over bright road sections

EDGES = ("top", "right", "bottom", "left")


def _point_on_edge(edge: str, t: float, canvas_size: float) -> tuple[float, float]:
    if edge == "top":
        return (t, 0.0)
    if edge == "bottom":
        return (t, canvas_size)
    if edge == "left":
        return (0.0, t)
    if edge == "right":
        return (canvas_size, t)
    raise ValueError(f"Unknown edge: {edge!r}")


def pick_walk_start_and_aim(
    rng: random.Random, canvas_size: float = CANVAS_SIZE
) -> tuple[tuple[float, float], tuple[float, float]]:
    """Start on a random point on a random edge; aim at a random point on
    one of the *other three* edges - so a walk can exit an adjacent or
    opposite side, not just straight across."""
    start_edge = rng.choice(EDGES)
    aim_edge = rng.choice([edge for edge in EDGES if edge != start_edge])
    start = _point_on_edge(start_edge, rng.uniform(0, canvas_size), canvas_size)
    aim = _point_on_edge(aim_edge, rng.uniform(0, canvas_size), canvas_size)
    return start, aim


def compute_heading(
    base_heading: float,
    distance_traveled: float,
    amp1: float,
    freq1: float,
    amp2: float,
    freq2: float,
) -> float:
    """The aim heading oscillated by two overlaid sine waves - a broad
    sweep plus a finer wobble - reading as an organic curve rather than
    jittery zigzag steps. Driven by distance traveled, not elapsed time, so
    tuning walk speed later doesn't also change how "wavy" the path looks."""
    return (
        base_heading
        + amp1 * math.sin(freq1 * distance_traveled)
        + amp2 * math.sin(freq2 * distance_traveled)
    )


def step_position(px: float, py: float, heading: float, speed: float, dt: float) -> tuple[float, float, float]:
    distance_moved = speed * dt
    new_px = px + math.cos(heading) * distance_moved
    new_py = py + math.sin(heading) * distance_moved
    return new_px, new_py, distance_moved


def is_off_board(px: float, py: float, canvas_size: float = CANVAS_SIZE) -> bool:
    return px < 0 or px >= canvas_size or py < 0 or py >= canvas_size


def compute_facing(prev_facing: int, dx_ema: float, deadzone: float = FACING_DEADZONE) -> int:
    if dx_ema > deadzone:
        return 1
    if dx_ema < -deadzone:
        return -1
    return prev_facing


def compute_gait_pose(px: float, py: float, facing: int, gait_phase: float) -> dict[str, Any]:
    """One frame's worth of stick-figure body-part coordinates, in board
    (grid-unit) space - exact formulas from the reference prototype, not
    reinterpreted. `(px, py)` is the walker's feet/ground position (also
    what's sampled into the road path); the body extends upward from there.
    """
    hip_y = py - HIP_Y_OFFSET
    shoulder_y = py - SHOULDER_Y_OFFSET
    head_y = py - HEAD_Y_OFFSET

    swing = math.sin(gait_phase) * facing
    left_foot_x = px + swing * LEG_SWING_FACTOR
    right_foot_x = px - swing * LEG_SWING_FACTOR
    left_hand_x = px - swing * ARM_SWING_FACTOR
    right_hand_x = px + swing * ARM_SWING_FACTOR
    lean = facing * LEAN_FACTOR

    return {
        "leg1": ((px, hip_y), (left_foot_x, py)),
        "leg2": ((px, hip_y), (right_foot_x, py)),
        "torso": ((px + lean, shoulder_y), (px, hip_y)),
        "arm1": ((px + lean, shoulder_y), (left_hand_x, shoulder_y + ARM_Y_OFFSET)),
        "arm2": ((px + lean, shoulder_y), (right_hand_x, shoulder_y + ARM_Y_OFFSET)),
        "head_center": (px + lean, head_y),
        "head_radius": HEAD_RADIUS,
    }


def initial_road_walk_state() -> dict[str, Any]:
    """The "waiting" (board dark) state - used both to seed app.py's
    initial state and as what step_road_walk resets to once a fade
    completes."""
    return {
        "phase": "waiting",
        "elapsed_in_phase": 0.0,
        "path": [],
        "hue": 0.0,
        "px": 0.0,
        "py": 0.0,
        "distance_traveled": 0.0,
        "heading": 0.0,
        "aim_heading": 0.0,
        "facing": 1,
        "dx_ema": 0.0,
        "gait_phase": 0.0,
        "fade_alpha": 0.0,
    }


def _start_new_walk(rng: random.Random) -> dict[str, Any]:
    start, aim = pick_walk_start_and_aim(rng)
    aim_heading = math.atan2(aim[1] - start[1], aim[0] - start[0])
    return {
        "phase": "walking",
        "elapsed_in_phase": 0.0,
        "path": [start],
        "hue": rng.uniform(0, 360),
        "px": start[0],
        "py": start[1],
        "distance_traveled": 0.0,
        "heading": aim_heading,
        "aim_heading": aim_heading,
        "facing": 1 if math.cos(aim_heading) >= 0 else -1,
        "dx_ema": 0.0,
        "gait_phase": 0.0,
        "fade_alpha": 1.0,
    }


def step_road_walk(state: dict[str, Any], dt: float, settings: Any, rng: random.Random) -> dict[str, Any]:
    """Advances the state machine by one frame's worth of `dt` seconds.
    Called only on frames where road_walk is actually the mode being
    rendered - see the module docstring for why that's what makes the
    "pause while hidden" behavior work."""
    phase = state["phase"]

    if phase == "waiting":
        elapsed = state["elapsed_in_phase"] + dt
        if elapsed >= settings.road_walk_interval_seconds:
            return _start_new_walk(rng)
        return {**state, "elapsed_in_phase": elapsed}

    if phase == "walking":
        heading = compute_heading(
            state["aim_heading"],
            state["distance_traveled"],
            settings.road_walk_wander_amp_1,
            settings.road_walk_wander_freq_1,
            settings.road_walk_wander_amp_2,
            settings.road_walk_wander_freq_2,
        )
        new_px, new_py, distance_moved = step_position(
            state["px"], state["py"], heading, settings.road_walk_speed_px_per_sec, dt
        )
        dx_ema = FACING_EMA_ALPHA * (new_px - state["px"]) + (1 - FACING_EMA_ALPHA) * state["dx_ema"]
        elapsed_in_phase = state["elapsed_in_phase"] + dt

        new_state = {
            **state,
            "px": new_px,
            "py": new_py,
            "heading": heading,
            "distance_traveled": state["distance_traveled"] + distance_moved,
            "dx_ema": dx_ema,
            "facing": compute_facing(state["facing"], dx_ema),
            "gait_phase": state["gait_phase"] + distance_moved * GAIT_PHASE_PER_PIXEL,
            "elapsed_in_phase": elapsed_in_phase,
            "path": [*state["path"], (new_px, new_py)],
            "fade_alpha": 1.0,
        }

        if is_off_board(new_px, new_py) and elapsed_in_phase >= settings.road_walk_min_walk_seconds:
            new_state["phase"] = "signature"
            new_state["elapsed_in_phase"] = 0.0

        return new_state

    if phase == "signature":
        elapsed = state["elapsed_in_phase"] + dt
        if elapsed >= settings.road_walk_signature_seconds:
            return {**state, "phase": "fading", "elapsed_in_phase": 0.0, "fade_alpha": 1.0}
        return {**state, "elapsed_in_phase": elapsed}

    if phase == "fading":
        elapsed = state["elapsed_in_phase"] + dt
        fade_seconds = settings.road_walk_fade_seconds
        if fade_seconds <= 0 or elapsed >= fade_seconds:
            return initial_road_walk_state()
        return {**state, "elapsed_in_phase": elapsed, "fade_alpha": 1.0 - elapsed / fade_seconds}

    raise ValueError(f"Unknown road_walk phase: {phase!r}")


def _hsl_color(hue_degrees: float, saturation: float, lightness: float, brightness_scale: float) -> tuple[int, int, int]:
    """The board's background is always solid black and nothing else
    shares this layer, so scaling the RGB by `brightness_scale` (the fade
    alpha) directly is equivalent to real alpha-compositing over black -
    simpler than building an actual RGBA layer and compositing it."""
    hue = (hue_degrees % 360) / 360.0
    red, green, blue = colorsys.hls_to_rgb(hue, lightness, saturation)
    scale = 255 * max(0.0, min(1.0, brightness_scale))
    return (round(red * scale), round(green * scale), round(blue * scale))


def _draw_round_cap(draw: ImageDraw.ImageDraw, center: tuple[float, float], radius: float, color) -> None:
    x, y = center
    draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=color)


def _draw_stroked_polyline(
    draw: ImageDraw.ImageDraw, points: list[tuple[float, float]], width: float, color
) -> None:
    if len(points) < 2:
        return
    draw.line(points, fill=color, width=max(1, round(width)), joint="curve")
    radius = width / 2
    _draw_round_cap(draw, points[0], radius, color)
    _draw_round_cap(draw, points[-1], radius, color)


def _draw_dashed_polyline(
    draw: ImageDraw.ImageDraw,
    path_gu: list[tuple[float, float]],
    dash_on_gu: float,
    dash_off_gu: float,
    width_gu: float,
    color,
    supersample: int,
) -> None:
    """Hand-rolled dashing: PIL's ImageDraw.line has no native dash
    support. Walks the path's cumulative arc length (in grid units, so the
    dash pattern's spacing doesn't depend on the supersample factor) and
    only draws the "on" sub-segments. Each frame-to-frame path segment is
    treated as fully on or fully off based on the dash phase at its start
    rather than precisely split at the exact on/off boundary - segments are
    short enough (well under one dash length at typical walk speed) that
    this reads as a clean dash at the board's actual pixel scale."""
    if len(path_gu) < 2:
        return
    period = dash_on_gu + dash_off_gu
    width_px = max(1, round(width_gu * supersample))
    radius_px = width_px / 2
    cumulative = 0.0
    for (x0, y0), (x1, y1) in zip(path_gu, path_gu[1:]):
        segment_length = math.hypot(x1 - x0, y1 - y0)
        if segment_length > 0 and (cumulative % period) < dash_on_gu:
            start = (x0 * supersample, y0 * supersample)
            end = (x1 * supersample, y1 * supersample)
            draw.line([start, end], fill=color, width=width_px)
            _draw_round_cap(draw, start, radius_px, color)
            _draw_round_cap(draw, end, radius_px, color)
        cumulative += segment_length


def _scale_point_around(point: tuple[float, float], anchor: tuple[float, float], scale: float) -> tuple[float, float]:
    return (anchor[0] + (point[0] - anchor[0]) * scale, anchor[1] + (point[1] - anchor[1]) * scale)


def _draw_signature_text(frame: Image.Image, font_path, brightness_scale: float) -> None:
    """The "WE MAKE / THE ROAD / BY WALKING" flash - drawn directly at
    native resolution (no supersampling, same reasoning as the walker:
    Silkscreen is designed to stay crisp at exactly this pixel count, see
    tinyscreen/fonts.py). A stroke_width outline keeps it legible over
    bright road sections without needing a separate shadow layer."""
    font = get_font(font_path, SIGNATURE_FONT_SIZE)
    draw = ImageDraw.Draw(frame)
    draw.fontmode = "1"

    boxes = [draw.textbbox((0, 0), line, font=font) for line in SIGNATURE_LINES]
    line_heights = [bottom - top for _, top, _, bottom in boxes]
    total_height = sum(line_heights) + SIGNATURE_LINE_SPACING * (len(SIGNATURE_LINES) - 1)

    fill = tuple(round(channel * max(0.0, min(1.0, brightness_scale))) for channel in SIGNATURE_TEXT_COLOR)

    y = (CANVAS_SIZE - total_height) // 2
    for line, (left, top, right, _bottom), line_height in zip(SIGNATURE_LINES, boxes, line_heights):
        x = (CANVAS_SIZE - (right - left)) // 2 - left
        draw.text(
            (x, y - top),
            line,
            font=font,
            fill=fill,
            stroke_width=SIGNATURE_STROKE_WIDTH,
            stroke_fill=SIGNATURE_OUTLINE_COLOR,
        )
        y += line_height + SIGNATURE_LINE_SPACING


def render_road_walk_frame(state: dict[str, Any], font_path) -> Image.Image:
    # The road is drawn supersampled then LANCZOS-downsampled - the soft
    # antialiasing is exactly what a "glowing" road wants. The walker is
    # drawn separately, directly at native resolution with no downsampling
    # at all - confirmed on real hardware that going through the same
    # blur pipeline made a figure this small unreadable as a stick figure
    # (a handful of already-thin limbs all going soft and merging into a
    # blob) rather than a road, the same "antialiasing reads as mush at
    # this pixel count" lesson this codebase already learned for text (see
    # renderer.py's build_scroll_strip docstring).
    working_size = CANVAS_SIZE * SUPERSAMPLE
    road_canvas = Image.new("RGB", (working_size, working_size), (0, 0, 0))
    road_draw = ImageDraw.Draw(road_canvas)

    path = state["path"]
    fade_alpha = state["fade_alpha"]

    if len(path) >= 2 and fade_alpha > 0:
        scaled_path = [(x * SUPERSAMPLE, y * SUPERSAMPLE) for x, y in path]
        road_color = _hsl_color(state["hue"], ROAD_BED_SATURATION, ROAD_BED_LIGHTNESS, fade_alpha)
        _draw_stroked_polyline(road_draw, scaled_path, ROAD_BED_WIDTH_GU * SUPERSAMPLE, road_color)

        centerline_color = _hsl_color(state["hue"], CENTERLINE_SATURATION, CENTERLINE_LIGHTNESS, fade_alpha)
        _draw_dashed_polyline(
            road_draw, path, CENTERLINE_DASH_ON_GU, CENTERLINE_DASH_OFF_GU, CENTERLINE_WIDTH_GU, centerline_color, SUPERSAMPLE
        )

    frame = road_canvas.resize((CANVAS_SIZE, CANVAS_SIZE), Image.LANCZOS)

    if state["phase"] == "walking":
        anchor = (state["px"], state["py"])
        pose = compute_gait_pose(state["px"], state["py"], state["facing"], state["gait_phase"])
        frame_draw = ImageDraw.Draw(frame)

        def scaled(point: tuple[float, float]) -> tuple[float, float]:
            return _scale_point_around(point, anchor, WALKER_RENDER_SCALE)

        for part, width in (("leg1", LIMB_WIDTH), ("leg2", LIMB_WIDTH), ("torso", LIMB_WIDTH), ("arm1", ARM_WIDTH), ("arm2", ARM_WIDTH)):
            start, end = pose[part]
            _draw_stroked_polyline(frame_draw, [scaled(start), scaled(end)], width * WALKER_RENDER_SCALE, WALKER_COLOR)

        head_center = scaled(pose["head_center"])
        head_radius = pose["head_radius"] * WALKER_RENDER_SCALE
        frame_draw.ellipse(
            (
                head_center[0] - head_radius,
                head_center[1] - head_radius,
                head_center[0] + head_radius,
                head_center[1] + head_radius,
            ),
            fill=WALKER_COLOR,
        )

    if state["phase"] in ("signature", "fading"):
        _draw_signature_text(frame, font_path, fade_alpha)

    return frame
