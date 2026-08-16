import math
import random
from pathlib import Path

from tinyscreen.config import Settings
from tinyscreen.renderer import CANVAS_SIZE
from tinyscreen.road_walk import (
    ARM_SWING_FACTOR,
    ARM_Y_OFFSET,
    compute_facing,
    compute_gait_pose,
    compute_heading,
    initial_road_walk_state,
    is_off_board,
    pick_walk_start_and_aim,
    render_road_walk_frame,
    step_position,
    step_road_walk,
)

FONT_PATH = Path(__file__).resolve().parent.parent / "assets" / "fonts" / "Silkscreen-Regular.ttf"


def _edges_of_point(point: tuple[float, float], size: float) -> set[str]:
    x, y = point
    edges = set()
    if math.isclose(y, 0):
        edges.add("top")
    if math.isclose(y, size):
        edges.add("bottom")
    if math.isclose(x, 0):
        edges.add("left")
    if math.isclose(x, size):
        edges.add("right")
    return edges


def test_pick_walk_start_and_aim_lands_on_the_board_boundary():
    rng = random.Random(0)
    for _ in range(20):
        start, aim = pick_walk_start_and_aim(rng, canvas_size=64)
        assert _edges_of_point(start, 64), f"start {start} isn't on any edge"
        assert _edges_of_point(aim, 64), f"aim {aim} isn't on any edge"


def test_pick_walk_start_and_aim_uses_a_different_edge_than_the_start():
    rng = random.Random(0)
    for _ in range(20):
        start, aim = pick_walk_start_and_aim(rng, canvas_size=64)
        assert _edges_of_point(start, 64).isdisjoint(_edges_of_point(aim, 64))


def test_compute_heading_at_zero_distance_is_the_base_heading():
    # Both sine terms are sin(0)=0 at distance_traveled=0, so heading should
    # equal base_heading exactly, before any wander is applied.
    assert compute_heading(1.234, 0.0, 0.6, 0.05, 0.2, 0.18) == 1.234


def test_compute_heading_matches_the_formula_at_nonzero_distance():
    base, distance, amp1, freq1, amp2, freq2 = 0.5, 10.0, 0.6, 0.05, 0.2, 0.18
    expected = base + amp1 * math.sin(freq1 * distance) + amp2 * math.sin(freq2 * distance)
    assert compute_heading(base, distance, amp1, freq1, amp2, freq2) == expected


def test_step_position_moves_along_heading_zero_purely_in_x():
    px, py, distance_moved = step_position(0.0, 0.0, heading=0.0, speed=10.0, dt=0.5)
    assert math.isclose(px, 5.0)
    assert math.isclose(py, 0.0, abs_tol=1e-9)
    assert math.isclose(distance_moved, 5.0)


def test_is_off_board_boundary_cases():
    assert is_off_board(-0.1, 10, canvas_size=64) is True
    assert is_off_board(64, 10, canvas_size=64) is True  # exactly at the edge counts as off
    assert is_off_board(0, 10, canvas_size=64) is False  # exactly 0 is still on
    assert is_off_board(32, 32, canvas_size=64) is False


def test_compute_facing_holds_previous_within_the_deadzone():
    assert compute_facing(1, 0.01, deadzone=0.05) == 1
    assert compute_facing(-1, -0.01, deadzone=0.05) == -1


def test_compute_facing_flips_once_past_the_deadzone():
    assert compute_facing(1, -0.2, deadzone=0.05) == -1
    assert compute_facing(-1, 0.2, deadzone=0.05) == 1


def test_compute_gait_pose_matches_the_reference_formulas():
    # Leg/torso/head constants are an exact, unscaled transcription of the
    # reference prototype's formulas. Arm reach (swing factor + y offset)
    # was deliberately tuned away from the reference afterward - the
    # literal reference values (0.6, 1.3) made the arms read as short and
    # stocky on real hardware - so those two are checked against
    # road_walk's own constants rather than hardcoded reference numbers.
    px, py, facing, gait_phase = 10.0, 20.0, 1, math.pi / 4
    pose = compute_gait_pose(px, py, facing, gait_phase)

    swing = math.sin(gait_phase) * facing
    hip_y, shoulder_y, head_y = py - 1.8, py - 3.2, py - 4.1
    left_foot_x, right_foot_x = px + swing * 0.85, px - swing * 0.85
    left_hand_x = px - swing * ARM_SWING_FACTOR
    right_hand_x = px + swing * ARM_SWING_FACTOR
    lean = facing * 0.12

    def assert_point_close(actual, expected):
        assert math.isclose(actual[0], expected[0], abs_tol=1e-9)
        assert math.isclose(actual[1], expected[1], abs_tol=1e-9)

    assert_point_close(pose["leg1"][0], (px, hip_y))
    assert_point_close(pose["leg1"][1], (left_foot_x, py))
    assert_point_close(pose["leg2"][0], (px, hip_y))
    assert_point_close(pose["leg2"][1], (right_foot_x, py))
    assert_point_close(pose["torso"][0], (px + lean, shoulder_y))
    assert_point_close(pose["torso"][1], (px, hip_y))
    assert_point_close(pose["arm1"][0], (px + lean, shoulder_y))
    assert_point_close(pose["arm1"][1], (left_hand_x, shoulder_y + ARM_Y_OFFSET))
    assert_point_close(pose["arm2"][0], (px + lean, shoulder_y))
    assert_point_close(pose["arm2"][1], (right_hand_x, shoulder_y + ARM_Y_OFFSET))
    assert_point_close(pose["head_center"], (px + lean, head_y))
    assert pose["head_radius"] == 0.6


def test_step_road_walk_starts_waiting():
    assert initial_road_walk_state()["phase"] == "waiting"


def test_step_road_walk_transitions_to_walking_after_the_interval():
    settings = Settings(road_walk_interval_seconds=1.0)
    rng = random.Random(0)
    state = initial_road_walk_state()

    state = step_road_walk(state, 0.5, settings, rng)
    assert state["phase"] == "waiting"

    state = step_road_walk(state, 0.5, settings, rng)
    assert state["phase"] == "walking"
    assert len(state["path"]) == 1  # just the starting point


def test_step_road_walk_path_grows_by_one_point_per_step_while_walking():
    settings = Settings(
        road_walk_interval_seconds=0.0,
        road_walk_min_walk_seconds=999.0,  # never let it exit mid-test
        road_walk_speed_px_per_sec=1.0,
        road_walk_wander_amp_1=0.0,
        road_walk_wander_amp_2=0.0,
    )
    rng = random.Random(1)
    state = step_road_walk(initial_road_walk_state(), 0.0, settings, rng)
    assert state["phase"] == "walking"

    path_length_before = len(state["path"])
    state = step_road_walk(state, 0.1, settings, rng)
    assert len(state["path"]) == path_length_before + 1


def test_step_road_walk_does_not_end_the_walk_before_min_walk_seconds_even_off_board():
    settings = Settings(
        road_walk_interval_seconds=0.0,
        road_walk_min_walk_seconds=10.0,
        road_walk_speed_px_per_sec=1000.0,  # guaranteed to leave the board in one step
        road_walk_wander_amp_1=0.0,
        road_walk_wander_amp_2=0.0,
    )
    rng = random.Random(2)
    state = step_road_walk(initial_road_walk_state(), 0.0, settings, rng)
    assert state["phase"] == "walking"

    state = step_road_walk(state, 1.0, settings, rng)  # elapsed_in_phase=1.0 < min_walk_seconds=10.0
    assert is_off_board(state["px"], state["py"])
    assert state["phase"] == "walking"  # still walking - too early to end despite being off board


def test_step_road_walk_enters_signature_after_min_walk_seconds_when_off_board():
    settings = Settings(
        road_walk_interval_seconds=0.0,
        road_walk_min_walk_seconds=0.5,
        road_walk_speed_px_per_sec=1000.0,
        road_walk_wander_amp_1=0.0,
        road_walk_wander_amp_2=0.0,
    )
    rng = random.Random(3)
    state = step_road_walk(initial_road_walk_state(), 0.0, settings, rng)
    assert state["phase"] == "walking"

    state = step_road_walk(state, 0.6, settings, rng)  # elapsed_in_phase=0.6 >= min_walk_seconds=0.5
    assert state["phase"] == "signature"
    assert state["elapsed_in_phase"] == 0.0
    assert state["fade_alpha"] == 1.0


def test_step_road_walk_signature_holds_until_signature_seconds_elapse():
    settings = Settings(road_walk_signature_seconds=1.0)
    rng = random.Random(6)
    state = {**initial_road_walk_state(), "phase": "signature", "elapsed_in_phase": 0.0, "fade_alpha": 1.0}

    state = step_road_walk(state, 0.5, settings, rng)
    assert state["phase"] == "signature"
    assert math.isclose(state["elapsed_in_phase"], 0.5)


def test_step_road_walk_signature_transitions_to_fading_after_signature_seconds():
    settings = Settings(road_walk_signature_seconds=1.0)
    rng = random.Random(7)
    state = {**initial_road_walk_state(), "phase": "signature", "elapsed_in_phase": 0.9, "fade_alpha": 1.0}

    state = step_road_walk(state, 0.2, settings, rng)  # elapsed_in_phase would reach 1.1 >= 1.0
    assert state["phase"] == "fading"
    assert state["elapsed_in_phase"] == 0.0
    assert state["fade_alpha"] == 1.0


def test_step_road_walk_fading_ramps_alpha_down_over_fade_seconds():
    settings = Settings(road_walk_fade_seconds=1.0)
    rng = random.Random(4)
    state = {
        **initial_road_walk_state(),
        "phase": "fading",
        "elapsed_in_phase": 0.0,
        "fade_alpha": 1.0,
        "path": [(1.0, 2.0), (3.0, 4.0)],
    }

    state = step_road_walk(state, 0.5, settings, rng)
    assert state["phase"] == "fading"
    assert math.isclose(state["fade_alpha"], 0.5)


def test_step_road_walk_returns_to_waiting_once_fade_completes():
    settings = Settings(road_walk_fade_seconds=1.0)
    rng = random.Random(5)
    state = {
        **initial_road_walk_state(),
        "phase": "fading",
        "elapsed_in_phase": 0.9,
        "fade_alpha": 0.1,
        "path": [(1.0, 2.0), (3.0, 4.0)],
    }

    state = step_road_walk(state, 0.2, settings, rng)  # elapsed_in_phase would reach 1.1 >= 1.0
    assert state["phase"] == "waiting"
    assert state["path"] == []


def test_render_road_walk_frame_returns_canvas_sized_rgb_image():
    frame = render_road_walk_frame(initial_road_walk_state(), FONT_PATH)
    assert frame.size == (CANVAS_SIZE, CANVAS_SIZE)
    assert frame.mode == "RGB"


def test_render_road_walk_frame_is_black_when_path_is_empty():
    frame = render_road_walk_frame(initial_road_walk_state(), FONT_PATH)
    assert set(frame.getdata()) == {(0, 0, 0)}


def test_render_road_walk_frame_draws_something_when_a_path_exists():
    state = {
        **initial_road_walk_state(),
        "phase": "walking",
        "path": [(10.0, 10.0), (30.0, 40.0), (50.0, 20.0)],
        "hue": 120.0,
        "fade_alpha": 1.0,
        "px": 50.0,
        "py": 20.0,
        "facing": 1,
        "gait_phase": 0.5,
    }
    frame = render_road_walk_frame(state, FONT_PATH)
    assert any(pixel != (0, 0, 0) for pixel in frame.getdata())


def test_render_road_walk_frame_draws_no_walker_during_signature():
    # The walker should be gone as soon as the walk ends - only the road
    # (and, separately, the signature text) should still be visible. The
    # walker is drawn at a fixed, un-faded white regardless of fade_alpha
    # (it's only ever drawn while phase=="walking", where alpha is always
    # 1.0 anyway) - using a fade_alpha < 1.0 here means the signature
    # text's own white comes out scaled (not exactly 255,255,255), so an
    # exact (255,255,255) pixel can only mean a leftover walker, not text.
    walking_state = {
        **initial_road_walk_state(),
        "phase": "walking",
        "path": [(10.0, 10.0), (30.0, 40.0)],
        "hue": 120.0,
        "fade_alpha": 1.0,
        "px": 30.0,
        "py": 40.0,
        "facing": 1,
        "gait_phase": 0.5,
    }
    signature_state = {**walking_state, "phase": "signature", "fade_alpha": 0.5}

    walking_pixels = set(render_road_walk_frame(walking_state, FONT_PATH).getdata())
    signature_pixels = set(render_road_walk_frame(signature_state, FONT_PATH).getdata())
    assert (255, 255, 255) in walking_pixels  # solid white walker while walking
    assert (255, 255, 255) not in signature_pixels  # no walker once signature starts


def test_render_road_walk_frame_draws_signature_text_with_no_road_present():
    # An empty path isolates the text from any road pixels, so this
    # confirms the text itself renders during "signature"/"fading" - not
    # just that *something* (e.g. leftover road) is on screen.
    for phase, fade_alpha in (("signature", 1.0), ("fading", 0.5)):
        state = {**initial_road_walk_state(), "phase": phase, "path": [], "fade_alpha": fade_alpha}
        frame = render_road_walk_frame(state, FONT_PATH)
        assert any(pixel != (0, 0, 0) for pixel in frame.getdata())


def test_render_road_walk_frame_draws_no_text_outside_signature_and_fading():
    for phase in ("waiting", "walking"):
        state = {
            **initial_road_walk_state(),
            "phase": phase,
            "path": [],
            "fade_alpha": 1.0,
            "px": -100.0,  # off-canvas, so a "walking" walker doesn't draw either
            "py": -100.0,
        }
        frame = render_road_walk_frame(state, FONT_PATH)
        assert set(frame.getdata()) == {(0, 0, 0)}
