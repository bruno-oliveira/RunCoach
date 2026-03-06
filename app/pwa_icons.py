"""PWA icon generator — pure stdlib, no external dependencies.

Generates PNG icons for the PWA manifest and apple-touch-icon.
Icons are a cobalt-blue square with white "RC" monogram.
"""

import logging
import os
import struct
import zlib

logger = logging.getLogger(__name__)

# Brand colors
_BG = (29, 78, 216)    # #1D4ED8 — cobalt blue
_FG = (255, 255, 255)  # white

# Pixel-art glyphs (6 cols × 7 rows, 1 = foreground)
_GLYPH_R = [
    [1, 1, 1, 1, 0, 0],
    [1, 0, 0, 0, 1, 0],
    [1, 0, 0, 0, 1, 0],
    [1, 1, 1, 1, 0, 0],
    [1, 0, 1, 0, 0, 0],
    [1, 0, 0, 1, 0, 0],
    [1, 0, 0, 0, 1, 0],
]

_GLYPH_C = [
    [0, 1, 1, 1, 1, 0],
    [1, 0, 0, 0, 0, 1],
    [1, 0, 0, 0, 0, 0],
    [1, 0, 0, 0, 0, 0],
    [1, 0, 0, 0, 0, 0],
    [1, 0, 0, 0, 0, 1],
    [0, 1, 1, 1, 1, 0],
]

_GLYPH_COLS = 6
_GLYPH_ROWS = 7


def _make_png(size: int) -> bytes:
    """Return raw PNG bytes for a square icon of the given pixel size."""
    # Scale so the combined "RC" text fills ~60% of the icon width.
    # Combined width = 2 * COLS + 1 (gap) = 13 units.
    scale = max(1, size * 60 // (100 * 13))

    letter_w = _GLYPH_COLS * scale
    letter_h = _GLYPH_ROWS * scale
    gap = scale
    total_w = letter_w + gap + letter_w

    x_r = (size - total_w) // 2
    x_c = x_r + letter_w + gap
    y0 = (size - letter_h) // 2

    # Build pixel grid (list of rows, each row a list of (r,g,b))
    grid = [[_BG] * size for _ in range(size)]

    def _draw(glyph: list, x_off: int) -> None:
        for row_i, bits in enumerate(glyph):
            for col_i, bit in enumerate(bits):
                if not bit:
                    continue
                for dy in range(scale):
                    for dx in range(scale):
                        px = x_off + col_i * scale + dx
                        py = y0 + row_i * scale + dy
                        if 0 <= px < size and 0 <= py < size:
                            grid[py][px] = _FG

    _draw(_GLYPH_R, x_r)
    _draw(_GLYPH_C, x_c)

    # Encode as raw RGB PNG (filter type 0 = None on every row)
    raw = b"".join(
        b"\x00" + b"".join(bytes(p) for p in row)
        for row in grid
    )

    def _chunk(tag: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(tag + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)

    ihdr = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", ihdr)
        + _chunk(b"IDAT", zlib.compress(raw, 6))
        + _chunk(b"IEND", b"")
    )


def generate_pwa_icons(static_dir: str) -> None:
    """Generate PWA PNG icon files under ``{static_dir}/icons/`` if absent."""
    icons_dir = os.path.join(static_dir, "icons")
    os.makedirs(icons_dir, exist_ok=True)

    targets = {
        "icon-192.png": 192,
        "icon-512.png": 512,
        "apple-touch-icon.png": 180,
    }

    for filename, size in targets.items():
        path = os.path.join(icons_dir, filename)
        if not os.path.exists(path):
            try:
                with open(path, "wb") as fh:
                    fh.write(_make_png(size))
                logger.info("Generated PWA icon: %s (%dpx)", filename, size)
            except OSError as exc:
                logger.warning("Could not write PWA icon %s: %s", filename, exc)
