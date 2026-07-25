"""Hardware abstraction for the RGB LED matrix.

This is the only file in the project that knows whether it's talking to a real
LED panel or a software stand-in for one. Everywhere else in the app, code just
calls the generic `RGBMatrix` / `RGBMatrixOptions` API and has no idea (and
doesn't need to know) which backend is underneath.

Two backends, same API:

- `rgbmatrix` — the real Python bindings for hzeller/rpi-rgb-led-matrix. These
  are compiled from C++ source directly on the Raspberry Pi (they talk to GPIO
  pins, so they only make sense on real hardware) and are NOT something you
  `pip install` — they get built on the Pi when the hardware arrives.
- `RGBMatrixEmulator` — a pip-installable package that implements the exact
  same classes and method names, but draws to a window/browser tab on your
  Mac instead of physical LEDs. Because the API is identical, the rest of
  this codebase (rendering, layout, the main loop) runs completely unchanged
  against either one — swapping backends is a one-line environment variable
  change, not a code change.

Which one gets imported is controlled by `TINYSCREEN_DISPLAY_BACKEND`
(read via `settings.display_backend`), not by guessing the platform — that
keeps behavior predictable and easy to debug ("why is it using the emulator
on the Pi?" should never be a mystery caused by silent detection logic).
"""

from __future__ import annotations

from typing import Any, Protocol


class MatrixSettings(Protocol):
    """The subset of Settings that display.py cares about.

    Using a Protocol (structural typing) instead of importing the real
    Settings dataclass keeps this module decoupled from config.py — anything
    with these attributes works, including lightweight stand-ins for tests
    or smoke scripts.
    """

    display_backend: str
    rows: int
    cols: int
    chain_length: int
    parallel: int
    hardware_mapping: str
    brightness: int
    gpio_slowdown: int
    pwm_bits: int
    limit_refresh_rate_hz: int
    disable_hardware_pulsing: bool


def _import_matrix_classes(display_backend: str) -> tuple[Any, Any]:
    if display_backend == "hardware":
        # Only importable on a Raspberry Pi with rpi-rgb-led-matrix built
        # and installed from source. Deliberately not caught/wrapped here —
        # if this fails on the Pi, you want the real ImportError, not a
        # silently-swapped emulator.
        from rgbmatrix import RGBMatrix, RGBMatrixOptions
    elif display_backend == "emulator":
        from RGBMatrixEmulator import RGBMatrix, RGBMatrixOptions
    else:
        raise ValueError(
            f"Unknown TINYSCREEN_DISPLAY_BACKEND={display_backend!r}, "
            "expected 'emulator' or 'hardware'"
        )
    return RGBMatrix, RGBMatrixOptions


def build_matrix_options(settings: MatrixSettings) -> Any:
    """Translate our config into the library's RGBMatrixOptions object.

    Every field here is a physical/electrical detail of how the panel is
    wired up. On the emulator these are mostly ignored (there's no real GPIO
    to configure), but setting them correctly now means the exact same
    Settings object works unchanged once real hardware is plugged in.
    """
    _, RGBMatrixOptions = _import_matrix_classes(settings.display_backend)
    options = RGBMatrixOptions()

    # Physical pixel dimensions of ONE panel. For the 64x64 Adafruit panel
    # that's rows=64, cols=64.
    options.rows = settings.rows
    options.cols = settings.cols

    # LED panels can be daisy-chained (more panels wired in a row, extending
    # the display sideways) or run in parallel (multiple independent chains
    # from separate ports on the same controller board, stacking panels
    # vertically). We're driving a single panel, so both are 1 — these exist
    # so the same option object could later drive a bigger wall of panels
    # without any other code changing.
    options.chain_length = settings.chain_length
    options.parallel = settings.parallel

    # The GPIO pinout differs by which HAT/bonnet is wired to the Pi.
    # "adafruit-hat" matches the Adafruit RGB Matrix Bonnet's specific pin
    # layout. There's a separate "adafruit-hat-pwm" mapping for boards with
    # an extra hardware-pulse jumper soldered — that's a hardware wiring
    # decision to make once the panel is in hand, not something we need to
    # get right in software today.
    options.hardware_mapping = settings.hardware_mapping

    # 0-100. Lower brightness draws less power and reduces heat/glare; the
    # Pi Zero 2 W's power supply is one more reason not to default to 100.
    options.brightness = settings.brightness

    # The Pi drives the panel by rapidly toggling GPIO pins in software.
    # Faster Pi models can toggle pins quicker than some panels can reliably
    # read, causing visual corruption (flickering/wrong colors) — slowdown
    # inserts a small delay per toggle to compensate. It's a number you tune
    # by looking at the real panel once it's here (2 is a common starting
    # point); it has no effect at all on the emulator.
    options.gpio_slowdown = settings.gpio_slowdown

    # How many bits of PWM (pulse-width modulation) are used to fake color
    # depth on LEDs that are physically only "fully on" or "fully off".
    # More bits = smoother color gradients but a lower max refresh rate —
    # 11 is the library default and a reasonable middle ground.
    options.pwm_bits = settings.pwm_bits

    # Caps how often the panel redraws. Without a limit, refresh rate can
    # vary frame to frame in a way that shows up as visible brightness
    # flicker (PWM brightness is timing-sensitive). Capping it keeps
    # brightness perceptually stable.
    options.limit_refresh_rate_hz = settings.limit_refresh_rate_hz

    # The library can optionally use a hardware timer for pulse generation,
    # which is more precise but conflicts with the Pi's onboard audio
    # circuitry (they share hardware). Disabling it avoids that conflict at
    # the cost of slightly more potential flicker — irrelevant here since
    # this project has no audio output.
    options.disable_hardware_pulsing = settings.disable_hardware_pulsing

    return options


def create_matrix(settings: MatrixSettings) -> Any:
    """Construct the RGBMatrix instance for the configured backend."""
    RGBMatrix, _ = _import_matrix_classes(settings.display_backend)
    options = build_matrix_options(settings)
    return RGBMatrix(options=options)


def push_frame(matrix: Any, canvas: Any, image: Any) -> Any:
    """Draw a PIL Image to the panel and return the new off-screen canvas.

    LED matrices flicker if you draw directly to the buffer that's currently
    being displayed. The standard pattern (identical on both backends) is
    double-buffering: draw onto an off-screen canvas, then swap it in at the
    next vertical sync (`SwapOnVSync`) — the panel jumps to the new complete
    frame all at once instead of showing a partially-drawn one. The call
    returns the *previous* on-screen canvas, now free to draw the next frame
    into, which is why callers reassign their canvas variable from this
    return value.
    """
    canvas.SetImage(image.convert("RGB"))
    return matrix.SwapOnVSync(canvas)
