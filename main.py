"""Entry point.

    uv run python main.py                      # runs against the emulator
    uv run python main.py --display-backend hardware --gpio-slowdown 4

.env supplies secrets/location (see .env.example); these flags let you
override the matrix/display hardware options without editing files -
exactly the ones you'll want to tune live once real hardware is connected.
"""

from __future__ import annotations

import argparse
import dataclasses

from tinyscreen.app import run
from tinyscreen.config import load_settings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="tiny-screen: scrolling weather/art sentence display"
    )
    parser.add_argument("--display-backend", choices=["emulator", "hardware"], default=None)
    parser.add_argument("--rows", type=int, default=None)
    parser.add_argument("--cols", type=int, default=None)
    parser.add_argument("--chain-length", type=int, default=None)
    parser.add_argument("--parallel", type=int, default=None)
    parser.add_argument("--hardware-mapping", default=None)
    parser.add_argument("--brightness", type=int, default=None)
    parser.add_argument("--gpio-slowdown", type=int, default=None)
    parser.add_argument("--pwm-bits", type=int, default=None)
    parser.add_argument("--limit-refresh-rate-hz", type=int, default=None)
    parser.add_argument(
        "--disable-hardware-pulsing",
        action="store_true",
        default=None,
        help="Avoid Pi onboard-audio conflict at the cost of more possible flicker.",
    )
    return parser


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
