"""Alternate entry point: a static "press play to begin" screen instead of
main.py's full weather/Spotify app.

    uv run python main2.py
    uv run python main2.py --display-backend hardware --gpio-slowdown 4

Same hardware/display flags as main.py - see that file for details.
"""

from __future__ import annotations

import dataclasses

from main import build_parser
from tinyscreen.config import load_settings
from tinyscreen.press_to_begin import run


def main() -> None:
    args = build_parser().parse_args()
    settings = load_settings()

    overrides = {
        "display_backend": args.display_backend,
        "rows": args.rows,
        "cols": args.cols,
        "chain_length": args.chain_length,
        "parallel": args.parallel,
        "hardware_mapping": args.hardware_mapping,
        "brightness": args.brightness,
        "gpio_slowdown": args.gpio_slowdown,
        "pwm_bits": args.pwm_bits,
        "limit_refresh_rate_hz": args.limit_refresh_rate_hz,
        "disable_hardware_pulsing": args.disable_hardware_pulsing,
    }
    overrides = {key: value for key, value in overrides.items() if value is not None}
    settings = dataclasses.replace(settings, **overrides)

    run(settings)


if __name__ == "__main__":
    main()
