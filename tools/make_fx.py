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


def main() -> int:
    os.makedirs(FX_DIR, exist_ok=True)
    pygame.init()
    # The TARDIS roof-lamp glow (start and exit dematerialisation).
    save_png(radial_glow(11, (255, 236, 190)), "lamp_glow.png")
    pygame.quit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
