"""Loads the small pixel font used for the time/date/weather text.

64x64 pixels isn't much room for text, so a regular font renders as blurry
antialiased mush at the sizes we need. Silkscreen (bundled in
assets/fonts/) is designed specifically for tiny displays like this one -
its glyphs are drawn on a coarse pixel grid so they stay crisp even at
single-digit pixel heights.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PIL import ImageFont


@lru_cache(maxsize=None)
def get_font(font_path: Path, size: int) -> ImageFont.FreeTypeFont:
    """Load (and cache) the font at a given pixel size.

    PIL doesn't let you resize a loaded font in place - each size needs its
    own ImageFont instance - so we cache per (path, size) pair to avoid
    re-reading the font file every frame.
    """
    return ImageFont.truetype(str(font_path), size)
