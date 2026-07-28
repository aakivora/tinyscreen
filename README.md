# tiny-screen

A "smart display" for a Raspberry Pi Zero W driving an Adafruit 64x64 RGB LED matrix panel. Built and fully tested against a software emulator ([RGBMatrixEmulator](https://github.com/ty-porter/RGBMatrixEmulator)) before any hardware existed — the same code runs unmodified on the real panel once it's plugged in, by flipping one environment variable.

Inspired by [mewtru's "How to Build a Tiny Screen for Spotify"](https://www.youtube.com/watch?v=Imc0zfjhUTw) and [tnarla/spotify-matrix](https://github.com/tnarla/spotify-matrix), extended with a generated weather/art idle mode and full Spotify OAuth + auto mode-switching.

## What it does

Two modes, switching automatically:

- **Idle mode**: a generated sentence — current weather + time of day mapped to a mood, matched with a painter and a color palette, plus a wind observation and a rotating Dutch word of the day — scrolling continuously (vertical "credits" style by default, horizontal marquee also available).
- **Spotify mode**: when something's actively playing on your Spotify account, the display switches to the track's album art with a scrolling "Track - Artist" ticker. Falls back to idle mode automatically after playback stops for a while.

## Status

Software is complete and verified in the emulator. Hardware bring-up is in progress: the Pi is flashed, networked, and has `rgbmatrix` built from source; the bonnet is soldered and attached next, followed by the first real-hardware test (tuning `gpio_slowdown`/`brightness` in `tinyscreen/display.py` as needed).

## Requirements

- Python 3.12+ (this project uses [uv](https://docs.astral.sh/uv/) to manage that automatically — you don't need Python 3.12 installed system-wide)
- A [free OpenWeatherMap API key](https://openweathermap.org/api) (optional — idle mode runs on mock weather data without one)
- A [Spotify Developer app](https://developer.spotify.com/dashboard) (optional — the app runs idle-mode-only without one)
- On real hardware: an Adafruit RGB Matrix Bonnet + 64x64 panel, and the [rpi-rgb-led-matrix](https://github.com/hzeller/rpi-rgb-led-matrix) library built from source on the Pi (not pip-installable — see `tinyscreen/display.py`)

## Setup

```bash
# Install uv if you don't have it (single binary, no sudo, doesn't touch system Python)
curl -LsSf https://astral.sh/uv/install.sh | sh

# On your dev machine (Mac/etc.), running against the software emulator:
uv sync --extra emulator

# On real Raspberry Pi hardware, running against the real rgbmatrix library
# (built separately from source - see "Requirements" above), skip the
# `emulator` extra entirely:
uv sync

cp .env.example .env
```

`RGBMatrixEmulator` is deliberately an optional extra, not a base dependency — it's only needed for the software emulator, and its `numpy` dependency can be slow or impractical to build from source on constrained hardware like the original Pi Zero's ARMv6 chip. Plain `uv sync` skips it entirely, which is what you want on real hardware.

Edit `.env` with your weather/Spotify credentials (see comments in the file — everything is optional and degrades gracefully without it). At minimum, `TINYSCREEN_DISPLAY_BACKEND=emulator` should already be set so it runs against the software emulator (on real hardware, set this to `hardware` instead).

### Idle-mode art

The idle mode's Rothko-inspired color palette references a local image collection:

```bash
uv run python scripts/seed_art.py
```

One-time scrape of WikiArt's Mark Rothko catalog into `assets/art/` (gitignored — regenerate locally, don't commit it).

### Spotify (optional)

1. Create an app at the [Spotify Developer Dashboard](https://developer.spotify.com/dashboard).
2. Add `http://127.0.0.1:8901/callback` as a Redirect URI in that app's settings (must match exactly).
3. Copy the Client ID/Secret into `.env` (`SPOTIFY_CLIENT_ID`, `SPOTIFY_CLIENT_SECRET`).
4. Run the one-time OAuth login:
   ```bash
   uv run python scripts/spotify_login.py
   ```
   Opens your browser to authorize; caches a token locally so the main app never needs a browser again.

## Running

```bash
uv run python main.py
```

Against the emulator (the default), this opens a browser tab at `localhost:8888` showing the scaled 64x64 canvas. Command-line flags override hardware/display settings without editing files — see `uv run python main.py --help`.

## Testing

```bash
uv run pytest
```

Pure-logic pieces (weather parsing, sentence generation, Spotify response parsing, mode-switching timing, frame composition) are unit tested. Visual/animation behavior is verified by hand against the emulator.

## Project layout

```
tinyscreen/
├── config.py            # .env + defaults -> Settings dataclass
├── display.py            # hardware abstraction (real rgbmatrix vs. RGBMatrixEmulator)
├── fonts.py               # Silkscreen pixel font loader
├── renderer.py            # idle-mode scrolling text rendering
├── weather.py              # OpenWeatherMap client + mock fallback
├── sentence.py             # weather -> mood -> artist -> sentence generation logic
├── spotify_auth.py         # Spotify OAuth token exchange/refresh/cache
├── spotify_client.py       # currently-playing polling + mode-switch timing
├── spotify_renderer.py     # album art + scrolling ticker rendering
└── app.py                  # main loop: idle/Spotify mode switching, animation
scripts/
├── seed_art.py             # one-time WikiArt scrape for idle-mode art
└── spotify_login.py        # one-time interactive Spotify OAuth setup
assets/
├── fonts/                  # Silkscreen (SIL OFL) pixel font
└── art/                    # generated by seed_art.py, gitignored
tests/                      # pytest suite for all the pure-logic modules above
```

## Configuration reference

Everything is set via `.env` (see `.env.example` for the full list with defaults/comments). Key ones:

| Variable | Default | Purpose |
|---|---|---|
| `TINYSCREEN_DISPLAY_BACKEND` | `emulator` | `emulator` or `hardware` |
| `OPENWEATHERMAP_API_KEY` | _(blank = mock data)_ | Weather for idle mode |
| `WEATHER_LAT` / `WEATHER_LON` / `WEATHER_CITY` | Amsterdam | Location for weather + sentence |
| `WEATHER_POLL_INTERVAL_SECONDS` | `900` (15 min) | How often weather/sentence refreshes |
| `IDLE_LAYOUT` | `vertical` | `vertical` (credits-style) or `horizontal` (marquee) |
| `SPOTIFY_CLIENT_ID` / `SPOTIFY_CLIENT_SECRET` | _(blank = disabled)_ | Spotify now-playing |
| `SPOTIFY_POLL_INTERVAL_SECONDS` | `5` | How often Spotify is polled |
| `SPOTIFY_FALLBACK_SECONDS` | `90` | How long to stay in Spotify mode after playback stops |

## Roadmap

- Deploy to real hardware once it arrives (tune `gpio_slowdown`/`brightness` in `tinyscreen/display.py`)
- Stretch goal: render Spotify album art as a slowly-rotating circular "vinyl record"
