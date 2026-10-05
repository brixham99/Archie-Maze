#!/usr/bin/env python3
"""Generate the small effect sprites in assets/fx/ as PNG files.

The game loads them with pygame.image.load(...).convert_alpha(), exactly like
the Archie, Dalek and TARDIS sprites. Run from the repository root:

    python3 tools/make_fx.py
"""
import os
import sys

import numpy as np

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
import pygame  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FX_DIR = os.path.join(ROOT, "assets", "fx")


def radial_glow(radius: int, colour, strength: float = 1.0) -> np.ndarray:
    """(H, W, 4) uint8 RGBA: colour fading out from a whiter centre, alpha to 0 at the rim."""
    size = radius * 2 + 1
    yy, xx = np.mgrid[0:size, 0:size]
    d = np.sqrt((xx - radius) ** 2 + (yy - radius) ** 2) / max(1, radius)
    fall = np.clip(1.0 - d, 0.0, 1.0)
    core = fall ** 3
    rgb = np.array(colour, np.float64)[None, None, :] * (1 - core[..., None]) + 255.0 * core[..., None]
    out = np.zeros((size, size, 4), np.uint8)
    out[..., :3] = rgb.clip(0, 255).astype(np.uint8)
    out[..., 3] = (255.0 * strength * fall ** 1.6).clip(0, 255).astype(np.uint8)
    return out


def save_png(arr: np.ndarray, name: str):
    h, w, _ = arr.shape
    surf = pygame.image.frombuffer(np.ascontiguousarray(arr).tobytes(), (w, h), "RGBA")
    path = os.path.join(FX_DIR, name)
    pygame.image.save(surf, path)
    print("wrote", os.path.relpath(path, ROOT), f"{w}x{h}")


def chameleon_cloak():
    """Oval badge with a green gem and a charge slot along the bottom."""
    W, H = 48, 56
    yy, xx = np.mgrid[0:H, 0:W]
    cx, cy = W / 2, H / 2 - 2
    arr = np.zeros((H, W, 4), np.uint8)
    body = ((xx - cx) / 18) ** 2 + ((yy - cy) / 22) ** 2 <= 1.0
    rim = (((xx - cx) / 20) ** 2 + ((yy - cy) / 24) ** 2 <= 1.0) & ~body
    arr[rim] = (186, 150, 70, 255)
    arr[body] = (48, 58, 72, 255)
    inner = ((xx - cx) / 14) ** 2 + ((yy - cy) / 16) ** 2 <= 1.0
    arr[inner] = (36, 44, 56, 255)
    gem = (xx - cx) ** 2 + (yy - cy + 2) ** 2 <= 36
    arr[gem] = (70, 196, 110, 255)
    gem2 = (xx - cx) ** 2 + (yy - cy + 2) ** 2 <= 12
    arr[gem2] = (180, 255, 200, 255)
    arr[H - 10:H - 4, 10:W - 10] = (20, 14, 10, 255)
    arr[H - 9:H - 5, 11:W - 11] = (40, 120, 60, 255)
    for px, py in ((cx - 12, cy - 14), (cx + 12, cy - 14), (cx - 12, cy + 12), (cx + 12, cy + 12)):
        arr[(xx - px) ** 2 + (yy - py) ** 2 <= 4] = (212, 180, 90, 255)
    return arr


def main() -> int:
    os.makedirs(FX_DIR, exist_ok=True)
    pygame.init()
    # The TARDIS roof-lamp glow (start and exit dematerialisation).
    save_png(radial_glow(11, (255, 236, 190)), "lamp_glow.png")
    save_png(chameleon_cloak(), "chameleon_cloak.png")
    pygame.quit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
