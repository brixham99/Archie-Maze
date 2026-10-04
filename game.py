#!/usr/bin/env python3
"""Archie's hedge maze — a small isometric maze in pygame.

Play:  python3 game.py
Test:  SDL_VIDEODRIVER=dummy python3 game.py --seed 1 --screenshot preview.png --frames 8

Left and right turn Archie. Up steps forward, down steps back.
The maze stays put; the camera scrolls so he stays centred.
"""

from __future__ import annotations

import argparse
import math
import os
import random
import sys
import time

# Headless runs (dummy video) need no audio device either. Normal runs use
# the real sound card; if the mixer cannot start, the game just stays silent.
if os.environ.get("SDL_VIDEODRIVER") == "dummy":
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import numpy as np
import pygame

# Classic 2:1 isometric projection. (tx, ty) is the top vertex of a tile.
#   screen_x = (col - row) * (TILE_W // 2)
#   screen_y = (col + row) * (TILE_H // 2)
TILE_W = 64
TILE_H = 32
HEDGE_H = 40
SPRITE_H = 74
MOVE_MS = 150
TURN_MS = 220
BUMP_MS = 110
WIN_W = 1100
WIN_H = 720
# The world (maze, dirt, Archie) is drawn to a smaller internal surface and
# scaled up to the window, so everything grows together. The HUD (hint,
# minimap, win panel) is drawn afterwards at full window resolution.
ZOOM = 2.0
ZOOM_SMOOTH = False  # True: smoothscale; False: nearest-neighbour scale
MAZE_SIZE = 41  # odd, so a perfect maze has a solid border
WALL, PATH, EXIT = 0, 1, 2

# Clockwise on the unrotated isometric screen: SE, SW, NW, NE.
DIR_SE = (1, 0)
DIR_SW = (0, 1)
DIR_NW = (-1, 0)
DIR_NE = (0, -1)
DIR_ORDER = (DIR_SE, DIR_SW, DIR_NW, DIR_NE)
FACING_SPRITE = {
    DIR_SE: "se",
    DIR_SW: "sw",
    DIR_NW: "nw",
    DIR_NE: "ne",
}

# One back-to-front pass. Archie is inserted when the tiles in front of him
# start, so a near hedge can cover his feet without being drawn twice.
BG_COLOUR = (34, 22, 14)
DIRT_EDGE = (68, 44, 26)
N_DIRT = 16
DIRT_SHADES = (0.90, 0.97, 1.03)

HERE = os.path.dirname(os.path.abspath(__file__))
SPRITE_FILES = {
    "se": os.path.join(HERE, "assets", "archie_se.png"),
    "sw": os.path.join(HERE, "assets", "archie_sw.png"),
    "nw": os.path.join(HERE, "assets", "archie_nw.png"),
    "ne": os.path.join(HERE, "assets", "archie_ne.png"),
    "n": os.path.join(HERE, "assets", "archie_n.png"),
    "e": os.path.join(HERE, "assets", "archie_e.png"),
    "w": os.path.join(HERE, "assets", "archie_w.png"),
}

DALEK_FILES = {k: os.path.join(HERE, "assets", f"dalek_{k}.png") for k in ("se", "sw", "ne", "nw")}
TARDIS_FILE = os.path.join(HERE, "assets", "tardis.png")

# --- Daleks, the TARDIS and the hedge disguise (pre-zoom pixels, ms) ---
DALEK_H = 86                 # Archie is SPRITE_H = 74
TARDIS_H = 124
NUM_DALEKS = 3
DALEK_STEP_MS = 260          # per cell, gliding; Archie takes MOVE_MS = 150
DALEK_TURN_MS = 160          # pause when a Dalek changes direction
DALEK_SIGHT = 8              # cells along the corridor it is facing
DALEK_TELEGRAPH_MS = 350     # eye-stalk glow before the shot
DALEK_MIN_START_DIST = 12    # path distance from Archie's start
DALEK_MIN_EXIT_DIST = 10     # path distance from the exit
LASER_MS = 450               # how long the beam stays on screen
DEATH_FADE_MS = 900          # Archie flickers, whites out and fades
DEATH_MSG_MS = 1000          # then the EXTERMINATED! panel
DEATH_FADE_LEVELS = 16
FLASH_MS = 200               # subtle translucent white flash on the shot
FLASH_ALPHA = 70             # of 255, at its peak
PUFF_LEVELS = 12
DISGUISE_MS = 4000
DISGUISE_COOLDOWN_MS = 3000
POOF_MS = 280
DISGUISE_SCALE = 0.86
# Gun tip and eye-stalk tip in the 160 px source images. SW/NW are exact
# mirror images of SE/NE, so their points are mirrored at load time.
DALEK_GUN_SRC = {"se": (95, 76), "ne": (103, 47)}
DALEK_EYE_SRC = {"se": (79, 30), "ne": (77, 5)}
DALEK_SPACING = (12, 10, 8, 6, 4, 2)  # wanted gap between Daleks, relaxed in turn
# The TARDIS that dropped Archie off dematerialises behind him at the start.
DEMAT_MS = 3600              # whole effect; the box is gone by about 3.3 s
DEMAT_PULSE_MS = 1000        # one fade pulse (and one wheeze-groan) per second
DEMAT_BACK = 0.32            # cells behind Archie's start spot, so he stands in front
DEMAT_LEVELS = 24            # pre-faded copies of the TARDIS (no set_alpha on RGBA)
TARDIS_LAMP_SRC = (59, 11)   # roof lamp in the 119x200 source image
DISGUISE_KEYS = (pygame.K_h, pygame.K_LSHIFT, pygame.K_RSHIFT)
MUTE_KEY = pygame.K_m

# --- Sound effects (assets/sounds, made by tools/make_sounds.py) ---
SOUND_DIR = os.path.join(HERE, "assets", "sounds")
SOUND_FILES = {
    "ow": "ow.wav",
    "exterminate": "exterminate.wav",
    "laser": "laser.wav",
    "step1": "step1.wav",
    "step2": "step2.wav",
    "step3": "step3.wav",
}
SOUND_FILES.update({"rustle": "rustle.wav", "cloak_on": "cloak_on.wav", "cloak_off": "cloak_off.wav",
                    "tardis_demat": "tardis_demat.wav"})
SOUND_VOLUME = {
    "ow": 0.38, "exterminate": 0.9, "laser": 0.7,
    "step1": 0.45, "step2": 0.45, "step3": 0.45,
    "rustle": 0.30, "cloak_on": 0.5, "cloak_off": 0.5,
    "tardis_demat": 0.6,
}
STEP_SOUNDS = ("step1", "step2", "step3")
OW_BUMPS = 3                 # "ow" on the 3rd hedge bump ...
OW_WINDOW_MS = 2000          # ... within 2 s; single bumps only rustle
OW_QUIET_MS = 2000           # after an "ow", bumps just rustle for a while
BUMP_COUNT_GAP_MS = 250      # held-key repeats count, but at most 4 a second
RUSTLE_GAP_MS = 450          # the soft rustle at most about twice a second
# Dalek proximity hum: one looping channel per Dalek, reserved so effects
# never steal it. Loud only when a Dalek is gliding close by; it fades out
# while the Dalek turns or stands still (aiming, firing, blocked).
HUM_FILE = "dalek_hum.wav"
HUM_MAX = 0.28               # channel volume when a Dalek is right next to Archie
HUM_FAR = 9.0                # silent at this effective distance (cells) ...
HUM_NEAR = 1.0               # ... full volume at this one or closer
HUM_PATH_WEIGHT = 0.65       # effective distance = 65% maze path + 35% straight line
HUM_FADE_OUT_MS = 80         # quick fade when a Dalek stops to turn (pause is 160 ms)
HUM_FADE_IN_MS = 110         # and back up as it glides off again
HUM_DIST_SMOOTH_MS = 100     # distance changes are smoothed too
HUM_PAN = 0.45               # subtle stereo: at most 45% off the far side
MIXER_FREQ = 22050
MIXER_BUFFER = 512           # ~23 ms at 22050 Hz: small, so sounds aren't laggy
RESTART_KEYS = (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_r, pygame.K_SPACE)

KEY_ACTIONS = {
    pygame.K_LEFT: ("turn", -1),
    pygame.K_a: ("turn", -1),
    pygame.K_RIGHT: ("turn", 1),
    pygame.K_d: ("turn", 1),
    pygame.K_UP: ("step", 1),
    pygame.K_w: ("step", 1),
    pygame.K_DOWN: ("step", -1),
    pygame.K_s: ("step", -1),
}


def ease(t: float) -> float:
    t = 0.0 if t < 0.0 else 1.0 if t > 1.0 else t
    return t * t * (3.0 - 2.0 * t)


def mix(colour, factor: float):
    return tuple(max(0, min(255, int(c * factor))) for c in colour)


def tile_origin(col: float, row: float):
    return (
        (col - row) * (TILE_W // 2),
        (col + row) * (TILE_H // 2),
    )


def diamond_points(tx: float, ty: float):
    hw = TILE_W // 2
    hh = TILE_H // 2
    return (
        (tx, ty - 1),
        (tx + hw + 1, ty + hh),
        (tx, ty + TILE_H + 1),
        (tx - hw - 1, ty + hh),
    )


def generate_maze(size: int, seed: int):
    """Perfect maze via iterative recursive backtracker.

    Odd cells are rooms; carving steps by two and opens the wall between.
    The border stays solid hedge. Start is (1, 1); the exit is the open
    cell at the opposite corner.
    """
    if size % 2 == 0 or size < 5:
        raise ValueError("maze size must be an odd integer >= 5")
    grid = [[WALL for _ in range(size)] for _ in range(size)]
    rng_state = seed & 0xFFFFFFFF

    def rnd() -> int:
        nonlocal rng_state
        rng_state = (rng_state * 1664525 + 1013904223) & 0xFFFFFFFF
        return rng_state

    def shuffled_dirs():
        dirs = [(2, 0), (-2, 0), (0, 2), (0, -2)]
        for i in range(3, 0, -1):
            j = rnd() % (i + 1)
            dirs[i], dirs[j] = dirs[j], dirs[i]
        return dirs

    grid[1][1] = PATH
    stack = [(1, 1)]
    while stack:
        col, row = stack[-1]
        carved = False
        for dc, dr in shuffled_dirs():
            nc, nr = col + dc, row + dr
            if 1 <= nc < size - 1 and 1 <= nr < size - 1 and grid[nr][nc] == WALL:
                grid[row + dr // 2][col + dc // 2] = PATH
                grid[nr][nc] = PATH
                stack.append((nc, nr))
                carved = True
                break
        if not carved:
            stack.pop()

    exit_c, exit_r = size - 2, size - 2
    grid[exit_r][exit_c] = EXIT
    return grid


def load_font(size: int, bold: bool = False) -> pygame.font.Font:
    try:
        font = pygame.font.SysFont("dejavusans", size, bold=bold)
        if font is not None:
            return font
    except (OSError, pygame.error):
        pass
    return pygame.font.Font(None, size)


def _tileable_noise(size: int, cells: int, rng: np.random.Generator) -> np.ndarray:
    grid = rng.random((cells, cells))
    ys = np.linspace(0, cells, size, endpoint=False)
    xs = np.linspace(0, cells, size, endpoint=False)
    x0 = np.floor(xs).astype(np.int32) % cells
    y0 = np.floor(ys).astype(np.int32) % cells
    xf = xs - np.floor(xs)
    yf = ys - np.floor(ys)
    xf = xf * xf * (3.0 - 2.0 * xf)
    yf = yf * yf * (3.0 - 2.0 * yf)
    x1 = (x0 + 1) % cells
    y1 = (y0 + 1) % cells
    g00 = grid[np.ix_(y0, x0)]
    g10 = grid[np.ix_(y0, x1)]
    g01 = grid[np.ix_(y1, x0)]
    g11 = grid[np.ix_(y1, x1)]
    top = g00 * (1.0 - xf)[None, :] + g10 * xf[None, :]
    bot = g01 * (1.0 - xf)[None, :] + g11 * xf[None, :]
    return top * (1.0 - yf)[:, None] + bot * yf[:, None]


def make_dirt_texture(size: int = 160) -> pygame.Surface:
    """One tileable mottled-soil texture: browns, clumps, pebbles, specks."""
    rng = np.random.default_rng(7)
    n1 = _tileable_noise(size, 6, rng)
    n2 = _tileable_noise(size, 14, rng)
    n3 = _tileable_noise(size, 28, rng)
    value = np.clip(0.52 * n1 + 0.30 * n2 + 0.18 * n3, 0.0, 1.0)
    dark = np.array([86, 56, 34], dtype=np.float32)
    mid = np.array([138, 94, 54], dtype=np.float32)
    light = np.array([172, 128, 76], dtype=np.float32)
    t = value[..., None]
    colour = dark * (1.0 - t) + mid * t
    peak = np.clip((value - 0.58) / 0.42, 0.0, 1.0)[..., None]
    colour = colour * (1.0 - 0.65 * peak) + light * (0.65 * peak)
    clump = _tileable_noise(size, 4, rng)
    damp = np.clip((clump - 0.55) / 0.45, 0.0, 1.0)[..., None]
    soil = np.array([58, 36, 22], dtype=np.float32)
    colour = colour * (1.0 - 0.45 * damp) + soil * (0.45 * damp)
    img = np.clip(colour, 0, 255).astype(np.uint8)
    for _ in range(220):
        x = int(rng.integers(0, size))
        y = int(rng.integers(0, size))
        if rng.random() < 0.55:
            tint = (
                int(rng.integers(108, 156)),
                int(rng.integers(102, 140)),
                int(rng.integers(88, 120)),
            )
            rad = 1 if rng.random() < 0.75 else 2
        else:
            tint = (
                int(rng.integers(70, 120)),
                int(rng.integers(46, 78)),
                int(rng.integers(28, 48)),
            )
            rad = 0
        for dy in range(-rad, rad + 1):
            for dx in range(-rad, rad + 1):
                if dx * dx + dy * dy > rad * rad:
                    continue
                img[(y + dy) % size, (x + dx) % size] = tint
    # Fine specks, wrapping so the texture still tiles.
    speck = rng.random((size, size))
    hi = speck > 0.992
    lo = (speck > 0.984) & ~hi
    img[hi] = np.array([186, 154, 110], dtype=np.uint8)
    img[lo] = np.array([64, 42, 28], dtype=np.uint8)
    surf = pygame.surfarray.make_surface(np.transpose(img, (1, 0, 2)))
    return surf.convert()


def _feet_anchor(image: pygame.Surface):
    rect = image.get_bounding_rect(min_alpha=16)
    band = max(4, rect.height // 8)
    xs = []
    y0 = max(rect.top, rect.bottom - band)
    for y in range(y0, rect.bottom):
        for x in range(rect.left, rect.right):
            if image.get_at((x, y)).a > 16:
                xs.append(x)
    ax = (sum(xs) / len(xs)) if xs else rect.centerx
    return ax, rect.bottom


def build_dirt_variants(texture: pygame.Surface):
    """Clip the dirt texture into diamond tiles with varied sample offsets."""
    tw, th = texture.get_size()
    sw, sh = 72, 40
    cx, cy = sw / 2, sh / 2
    hw = TILE_W // 2
    hh = TILE_H // 2
    raw = (
        (cx, cy - hh - 1),
        (cx + hw + 1, cy),
        (cx, cy + hh + 1),
        (cx - hw - 1, cy),
    )

    def grow(points, amount):
        out = []
        for x, y in points:
            dx, dy = x - cx, y - cy
            length = math.hypot(dx, dy) or 1.0
            out.append((x + dx / length * amount, y + dy / length * amount))
        return out

    fill_pts = grow(raw, 1.6)
    mask = pygame.Surface((sw, sh), pygame.SRCALPHA)
    pygame.draw.polygon(mask, (255, 255, 255, 255), fill_pts)
    variants = []
    for i in range(N_DIRT):
        ox = (i * 53 + 17) % tw
        oy = (i * 37 + 11) % th
        patch = pygame.Surface((sw + tw, sh + th))
        patch.blit(texture, (0, 0))
        patch.blit(texture, (tw, 0))
        patch.blit(texture, (0, th))
        patch.blit(texture, (tw, th))
        base = pygame.Surface((sw, sh), pygame.SRCALPHA)
        base.blit(patch, (-ox, -oy))
        base.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        pygame.draw.polygon(base, DIRT_EDGE, raw, 1)
        shades = []
        for factor in DIRT_SHADES:
            shaded = base.copy()
            level = max(0, min(255, int(round(factor * 255))))
            shaded.fill((level, level, level, 255), special_flags=pygame.BLEND_RGBA_MULT)
            shades.append(shaded.convert_alpha())
        variants.append(shades)
    return variants


N_HEDGE = 16
N_HEDGE_SHADES = 8
HEDGE_FOG_LO = 0.88  # same range as Game._fog
HEDGE_FOG_HI = 1.02
HEDGE_PAD_X = 6
HEDGE_PAD_TOP = 9
HEDGE_PAD_BOT = 4
HEDGE_SW = TILE_W + 2 * HEDGE_PAD_X
HEDGE_SH = HEDGE_PAD_TOP + HEDGE_H + TILE_H + HEDGE_PAD_BOT
HEDGE_OX = HEDGE_PAD_X + TILE_W // 2          # sprite x of the tile's top vertex
HEDGE_OY = HEDGE_PAD_TOP + HEDGE_H            # sprite y of the tile's top vertex
_SIDE = 32.0                                   # world units along one tile edge

# View-space normals (x right, y down, z toward the viewer) and the light.
_N_TOP = np.array([0.0, -0.866, 0.5])
_N_LEFT = np.array([-0.707, 0.354, 0.612])
_N_RIGHT = np.array([0.707, 0.354, 0.612])
_LIGHT = np.array([0.38, -0.72, 0.58])
_LIGHT = _LIGHT / np.linalg.norm(_LIGHT)


def _project(u, v, w):
    sx = HEDGE_OX + (u - v) * (TILE_W / 2) / _SIDE
    sy = HEDGE_OY + (u + v) * (TILE_H / 2) / _SIDE - w
    depth = 0.866 * (u + v) + 0.577 * w
    return sx, sy, depth


def _mounds(rng, count, amp):
    cu = rng.uniform(-4, _SIDE + 4, count)
    cv = rng.uniform(-4, _SIDE + 4, count)
    sig = rng.uniform(5.0, 10.0, count)
    a = rng.uniform(-0.4, 1.0, count) * amp

    def field(u, v):
        out = np.zeros_like(u)
        for i in range(count):
            out += a[i] * np.exp(-((u - cu[i]) ** 2 + (v - cv[i]) ** 2) / (2 * sig[i] ** 2))
        return out
    return field


def render_hedge_variant(index: int, seed: int = 4242) -> np.ndarray:
    """One leafy box-hedge block as an RGBA array (H, W, 4)."""
    rng = np.random.default_rng(seed + index * 7919)
    W, H = HEDGE_SW, HEDGE_SH
    # Per-variant tint: hue leans yellow or blue, brightness wobbles.
    warm = rng.uniform(-0.55, 0.55)
    bright = rng.uniform(0.955, 1.045)
    leaf_dark = np.array([34, 74, 30], dtype=np.float64)
    leaf_light = np.array([112, 166, 66], dtype=np.float64)
    leaf_dark += np.array([6, 2, -4]) * warm
    leaf_light += np.array([16, 6, -10]) * warm
    leaf_dark *= bright
    leaf_light *= bright

    top_bump = _mounds(rng, 5, 3.2)
    left_bump = _mounds(rng, 4, 1.8)
    right_bump = _mounds(rng, 4, 1.8)

    leaves = []  # (u, v, w, face, offset)

    def add(face, n):
        o = rng.uniform(-2.8, 1.6, n)
        if face == 0:     # top: plane w = HEDGE_H
            u = rng.uniform(-1.2, _SIDE + 1.2, n)
            v = rng.uniform(-1.2, _SIDE + 1.2, n)
            w = HEDGE_H + top_bump(u, v) + o
        elif face == 1:   # left (SW) face: plane v = SIDE
            u = rng.uniform(-0.8, _SIDE + 0.8, n)
            w = rng.uniform(-1.0, HEDGE_H + 0.5, n)
            v = _SIDE + left_bump(u, w) * 0.7 + o * 0.8
        else:             # right (SE) face: plane u = SIDE
            v = rng.uniform(-0.8, _SIDE + 0.8, n)
            w = rng.uniform(-1.0, HEDGE_H + 0.5, n)
            u = _SIDE + right_bump(v, w) * 0.7 + o * 0.8
        leaves.append((u, v, w, np.full(n, face), o))

    add(0, 330)
    add(1, 430)
    add(2, 430)
    u = np.concatenate([l[0] for l in leaves])
    v = np.concatenate([l[1] for l in leaves])
    w = np.concatenate([l[2] for l in leaves])
    face = np.concatenate([l[3] for l in leaves])
    off = np.concatenate([l[4] for l in leaves])
    n = u.size
    sx, sy, depth = _project(u, v, w)

    # Leaf ellipse shape.
    a = rng.uniform(1.7, 3.1, n)
    b = a * rng.uniform(0.45, 0.75, n)
    th = rng.uniform(0, math.pi, n)
    # Leaves on the side faces hang a little more vertically.
    side = face > 0
    th[side] = rng.normal(math.pi / 2, 0.6, side.sum())
    ct, st = np.cos(th), np.sin(th)

    R = 4
    dy, dx = np.mgrid[-R:R + 1, -R:R + 1]
    dx = dx.ravel()[None, :]
    dy = dy.ravel()[None, :]
    ix = np.floor(sx)[:, None].astype(np.int64) + dx
    iy = np.floor(sy)[:, None].astype(np.int64) + dy
    px = ix + 0.5 - sx[:, None]
    py = iy + 0.5 - sy[:, None]
    lx = px * ct[:, None] + py * st[:, None]
    ly = -px * st[:, None] + py * ct[:, None]
    d2 = (lx / a[:, None]) ** 2 + (ly / b[:, None]) ** 2
    inside = (d2 < 1.0) & (ix >= 0) & (ix < W) & (iy >= 0) & (iy < H)
    hz = np.sqrt(np.clip(1.0 - d2, 0.0, 1.0))
    # Ellipsoid normal in leaf space, rotated back to screen.
    gx = lx / a[:, None] ** 2
    gy = ly / b[:, None] ** 2
    nx = gx * ct[:, None] - gy * st[:, None]
    ny = gx * st[:, None] + gy * ct[:, None]
    nz = hz / b[:, None]
    face_n = np.stack([_N_TOP, _N_LEFT, _N_RIGHT])[face]          # (n, 3)
    nnorm = np.sqrt(nx * nx + ny * ny + nz * nz) + 1e-9
    k_leaf = 0.75
    Nx = face_n[:, 0:1] + k_leaf * nx / nnorm
    Ny = face_n[:, 1:2] + k_leaf * ny / nnorm
    Nz = face_n[:, 2:3] + k_leaf * nz / nnorm
    L = np.sqrt(Nx * Nx + Ny * Ny + Nz * Nz)
    ndl = (Nx * _LIGHT[0] + Ny * _LIGHT[1] + Nz * _LIGHT[2]) / L
    shade = 0.30 + 0.80 * np.clip(ndl, 0.0, 1.0)
    # Rim: the middle of each leaf a touch brighter, its edge darker.
    shade *= 0.80 + 0.20 * hz

    # Leaf colour.
    t = np.clip(rng.beta(2.2, 2.0, n), 0, 1)
    face_gain = np.where(face == 0, 1.04, np.where(face == 1, 0.70, 0.84))
    ao = 0.55 + 0.45 * np.clip((off + 2.8) / 4.4, 0, 1)
    ground = np.where(face > 0, 0.55 + 0.45 * np.clip(w / 16.0, 0, 1), 1.0)
    jitter = rng.uniform(0.9, 1.1, n)
    base = leaf_dark[None, :] * (1 - t[:, None]) + leaf_light[None, :] * t[:, None]
    # A few young, yellow-green leaves on top.
    young = (face == 0) & (rng.random(n) < 0.08)
    base[young] = base[young] * 0.6 + np.array([170, 196, 92]) * 0.4
    gain = (face_gain * ao * ground * jitter)[:, None] * shade
    cr = base[:, 0:1] * gain
    cg = base[:, 1:2] * gain
    cb = base[:, 2:3] * gain
    zd = depth[:, None] + hz * b[:, None] * 0.9

    # Resolve with a z-buffer: sort by depth, last write wins.
    m = inside.ravel()
    flat = (iy * W + ix).ravel()[m]
    zz = np.broadcast_to(zd, inside.shape).ravel()[m]
    rgb = np.stack([cr.ravel()[m], cg.ravel()[m], cb.ravel()[m]], axis=1)
    order = np.lexsort((zz, flat))
    flat_s = flat[order]
    last = np.ones(flat_s.size, dtype=bool)
    last[:-1] = flat_s[1:] != flat_s[:-1]
    pick = order[last]

    img = np.zeros((H * W, 4), dtype=np.float64)
    # Base: the dark interior of the hedge so gaps read as deep shade.
    yy, xx = np.mgrid[0:H, 0:W]
    xr = xx + 0.5 - HEDGE_OX
    yr = yy + 0.5 - HEDGE_OY
    # top plane
    su = (xr + 2 * (yr + HEDGE_H)) * _SIDE / TILE_W * 1.0
    sv = (-xr + 2 * (yr + HEDGE_H)) * _SIDE / TILE_W * 1.0
    top_in = (su >= 0) & (su <= _SIDE) & (sv >= 0) & (sv <= _SIDE)
    # left face v = SIDE: x = (u - SIDE) * 32/SIDE
    lu = xr * _SIDE / (TILE_W / 2) + _SIDE
    lw = (lu + _SIDE) * (TILE_H / 2) / _SIDE - yr
    left_in = (lu >= 0) & (lu <= _SIDE) & (lw >= 0) & (lw <= HEDGE_H)
    rv = _SIDE - xr * _SIDE / (TILE_W / 2)
    rw = (_SIDE + rv) * (TILE_H / 2) / _SIDE - yr
    right_in = (rv >= 0) & (rv <= _SIDE) & (rw >= 0) & (rw <= HEDGE_H)
    under = np.zeros((H, W, 3))
    under[left_in] = leaf_dark * 0.30
    under[right_in] = leaf_dark * 0.42
    under[top_in] = leaf_dark * 0.55
    base_mask = (top_in | left_in | right_in).ravel()
    img[base_mask, :3] = under.reshape(-1, 3)[base_mask]
    img[base_mask, 3] = 255
    img[flat[pick], 0] = rgb[pick, 0]
    img[flat[pick], 1] = rgb[pick, 1]
    img[flat[pick], 2] = rgb[pick, 2]
    img[flat[pick], 3] = 255
    return np.clip(img, 0, 255).astype(np.uint8).reshape(H, W, 4)


def _rgba_surface(arr):
    H, W, _ = arr.shape
    surf = pygame.Surface((W, H), pygame.SRCALPHA)
    pygame.surfarray.pixels3d(surf)[:] = np.transpose(arr[..., :3], (1, 0, 2))
    pygame.surfarray.pixels_alpha(surf)[:] = arr[..., 3].T
    return surf


def build_hedge_variants():
    """Pre-render the leafy hedge blocks, each in a few fog shades.

    Returns variants[v][shade] surfaces, blitted with the tile's top vertex
    at (HEDGE_OX, HEDGE_OY). Footprint and height match the old flat block.
    """
    variants = []
    levels = np.linspace(HEDGE_FOG_LO, HEDGE_FOG_HI, N_HEDGE_SHADES)
    for i in range(N_HEDGE):
        arr = render_hedge_variant(i)
        shades = []
        for k in levels:
            shaded = arr.copy()
            shaded[..., :3] = np.clip(arr[..., :3].astype(np.float32) * k, 0, 255).astype(np.uint8)
            shades.append(_rgba_surface(shaded).convert_alpha())
        variants.append(shades)
    return variants


def hedge_variant_grid(grid, seed: int):
    """Deterministic variant per hedge cell from a hash of (col, row, seed).

    A cell never repeats the variant of any already-chosen neighbour
    (W, N, NW, NE), so no two touching hedges are the same block.
    """
    size = len(grid)
    out = [[-1] * size for _ in range(size)]
    for row in range(size):
        for col in range(size):
            if grid[row][col] != WALL:
                continue
            h = (col * 73856093) ^ (row * 19349663) ^ (seed * 83492791)
            h = (h ^ (h >> 13)) * 0x5BD1E995 & 0xFFFFFFFF
            h ^= h >> 15
            v = h % N_HEDGE
            taken = set()
            for dc, dr in ((-1, 0), (0, -1), (-1, -1), (1, -1), (-2, 0), (0, -2)):
                c, r = col + dc, row + dr
                if 0 <= c < size and 0 <= r < size:
                    taken.add(out[r][c])
            while v in taken:
                v = (v + 7) % N_HEDGE
            out[row][col] = v
    return out


def _despill(image: pygame.Surface) -> pygame.Surface:
    """Remove the magenta matte fringe left round the cut-out sprites."""
    rgb = pygame.surfarray.pixels3d(image)
    alpha = pygame.surfarray.pixels_alpha(image)
    r = rgb[..., 0].astype(np.int16)
    g = rgb[..., 1].astype(np.int16)
    b = rgb[..., 2].astype(np.int16)
    spill = np.minimum(r, b) - g
    fix = (spill > 0) & (alpha > 0) & ((alpha < 255) | (spill > 30))
    sp = np.where(fix, spill, 0)
    rgb[..., 0] = np.clip(r - sp, 0, 255).astype(np.uint8)
    rgb[..., 2] = np.clip(b - sp, 0, 255).astype(np.uint8)
    del rgb, alpha
    return image


def _base_anchor(image: pygame.Surface):
    """Centre of an isometric base: midway between the lowest points of the
    leftmost and rightmost opaque columns in the bottom third."""
    a = pygame.surfarray.array_alpha(image) > 64
    w, h = a.shape
    y0 = int(h * 0.66)
    xs, ys = np.nonzero(a[:, y0:])
    left, right = xs.min(), xs.max()
    yl = ys[xs == left].max() + y0
    yr = ys[xs == right].max() + y0
    return (left + right + 1) / 2.0, (yl + yr + 1) / 2.0


def _load_scaled(path: str, height: int):
    src = pygame.image.load(path).convert_alpha()
    _despill(src)
    k = height / src.get_height()
    w = max(1, round(src.get_width() * k))
    return src, pygame.transform.smoothscale(src, (w, height)), k


def _alpha_scaled(image: pygame.Surface, k: float) -> pygame.Surface:
    """Copy of a per-pixel-alpha surface with its alpha multiplied by k."""
    out = image.copy()
    alpha = pygame.surfarray.pixels_alpha(out)
    alpha[:] = (pygame.surfarray.array_alpha(image).astype(np.float32) * k).astype(np.uint8)
    del alpha
    return out


def _faded_silhouettes(image: pygame.Surface, levels: int):
    """White silhouettes of a sprite: index 0 opaque, the last one invisible."""
    white = image.copy()
    rgb = pygame.surfarray.pixels3d(white)
    rgb[:] = 255
    del rgb
    return [_alpha_scaled(white, 1.0 - i / (levels - 1)) for i in range(levels)]


def _make_glow(radius: int, colour):
    """Additive radial glow (blit with BLEND_RGB_ADD)."""
    size = radius * 2 + 1
    yy, xx = np.mgrid[0:size, 0:size]
    d = np.sqrt((xx - radius) ** 2 + (yy - radius) ** 2) / radius
    fall = np.clip(1.0 - d, 0.0, 1.0) ** 1.6
    img = (fall[..., None] * np.array(colour, dtype=np.float64)[None, None, :]).clip(0, 255)
    return pygame.surfarray.make_surface(img.transpose(1, 0, 2).astype(np.uint8)).convert()


class Sounds:
    """Small, fail-safe wrapper round pygame.mixer.

    If the mixer cannot start or a file is missing, play() is a no-op, so the
    game runs silently instead of crashing. `requested` counts every event
    (handy for tests); `played` counts the ones actually sent to the mixer.
    """

    def __init__(self):
        self.ok = False
        self.muted = False
        self.sounds = {}
        self.requested = {}
        self.played = {}
        self.last_step = None
        self._rng = random.Random(4)
        self.hum = None
        self.hum_channels = []
        self.hum_levels = [(0.0, 0.0)] * NUM_DALEKS  # last (left, right) asked for
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(MIXER_FREQ, -16, 2, MIXER_BUFFER)
            self.ok = bool(pygame.mixer.get_init())
        except Exception:
            self.ok = False
        if not self.ok:
            return
        try:
            pygame.mixer.set_num_channels(16)
            pygame.mixer.set_reserved(NUM_DALEKS)
            self.hum_channels = [pygame.mixer.Channel(i) for i in range(NUM_DALEKS)]
        except Exception:
            self.hum_channels = []
        try:
            self.hum = pygame.mixer.Sound(os.path.join(SOUND_DIR, HUM_FILE))
        except Exception:
            self.hum = None
        for name, filename in SOUND_FILES.items():
            try:
                snd = pygame.mixer.Sound(os.path.join(SOUND_DIR, filename))
                snd.set_volume(SOUND_VOLUME.get(name, 0.8))
                self.sounds[name] = snd
            except Exception:
                pass  # missing or unreadable: that one stays silent

    def length_ms(self, name: str, default: float) -> float:
        snd = self.sounds.get(name)
        try:
            return snd.get_length() * 1000.0 if snd is not None else default
        except Exception:
            return default

    def play(self, name: str) -> bool:
        self.requested[name] = self.requested.get(name, 0) + 1
        if self.muted or not self.ok:
            return False
        snd = self.sounds.get(name)
        if snd is None:
            return False
        try:
            snd.play()
        except Exception:
            return False
        self.played[name] = self.played.get(name, 0) + 1
        return True

    def step(self) -> bool:
        """A soft footstep, never the same sample twice running."""
        choices = [n for n in STEP_SOUNDS if n != self.last_step]
        self.last_step = self._rng.choice(choices)
        return self.play(self.last_step)

    def set_hum(self, i: int, left: float, right: float, keep: bool):
        """Volume of Dalek i's looping hum. Stops the loop when it is silent
        and not wanted soon (far away, dead, won, muted)."""
        if self.muted:
            left = right = 0.0
            keep = False
        if i < len(self.hum_levels):
            self.hum_levels[i] = (left, right)
        if not self.ok or self.hum is None or i >= len(self.hum_channels):
            return
        ch = self.hum_channels[i]
        try:
            if left <= 0.0 and right <= 0.0 and not keep:
                if ch.get_busy():
                    ch.stop()
                return
            if not ch.get_busy():
                ch.set_volume(0.0, 0.0)
                ch.play(self.hum, loops=-1)
            ch.set_volume(left, right)
        except Exception:
            pass

    def stop_hums(self):
        self.hum_levels = [(0.0, 0.0)] * NUM_DALEKS
        for ch in self.hum_channels:
            try:
                ch.stop()
            except Exception:
                pass

    def stop_all(self):
        self.hum_levels = [(0.0, 0.0)] * NUM_DALEKS
        if not self.ok:
            return
        try:
            pygame.mixer.stop()
        except Exception:
            pass

    def toggle_mute(self):
        self.muted = not self.muted
        if self.muted:
            self.stop_all()


class Dalek:
    """Glides cell to cell along corridors; looks only the way it faces."""

    def __init__(self, col: int, row: int, facing, rng: random.Random):
        self.pos = [float(col), float(row)]
        self.target = (col, row)
        self.facing = facing
        self.prev_facing = facing
        self.turn_t0 = -1e9
        self.wait_until = 0.0
        self.state = "roam"  # roam, aim, fire
        self.fire_at = 0.0
        self.aim_t0 = 0.0
        self.fire_t0 = 0.0
        self.rng = rng
        self.feet = (0, 0)  # view-space feet, set while drawing
        self.glide = 0.0     # hum fade, 0..1: up while gliding, down when it stops
        self.near = 0.0      # smoothed closeness, 0..1
        self.hum_dist = 99.0  # effective distance used for the hum (cells)

    def cell(self):
        return int(round(self.pos[0])), int(round(self.pos[1]))

    def gliding(self, now: float) -> bool:
        return self.state == "roam" and now >= self.wait_until

    def face(self, direction, now: float) -> bool:
        if direction == self.facing:
            return False
        self.prev_facing = self.facing
        self.facing = direction
        self.turn_t0 = now
        return True

    def sprite_key(self, now: float) -> str:
        if now - self.turn_t0 < DALEK_TURN_MS / 2:
            return FACING_SPRITE[self.prev_facing]
        return FACING_SPRITE[self.facing]


class Game:
    def __init__(self, seed: int | None):
        self.sprites = {}
        self.anchors = {}
        for key, path in SPRITE_FILES.items():
            image = pygame.image.load(path).convert_alpha()
            h = image.get_height()
            if h != SPRITE_H:
                w = max(1, round(image.get_width() * SPRITE_H / h))
                image = pygame.transform.smoothscale(image, (w, SPRITE_H))
            self.sprites[key] = image
            self.anchors[key] = _feet_anchor(image)
        # White silhouettes for the death flicker, pre-faded. Built with numpy so
        # only Archie's own pixels turn white and the alpha is copied exactly
        # (no blend-mode fills or set_alpha on per-pixel-alpha surfaces, whose
        # behaviour differs between pygame builds and can whiten the whole rect).
        self.white = {key: _faded_silhouettes(image, DEATH_FADE_LEVELS) for key, image in self.sprites.items()}
        self.dalek_sprites = {}
        self.dalek_anchor = {}
        self.dalek_gun = {}
        self.dalek_eye = {}
        for key in ("se", "ne"):
            mirror = {"se": "sw", "ne": "nw"}[key]
            src, image, k = _load_scaled(DALEK_FILES[key], DALEK_H)
            sw = src.get_width()
            flipped = pygame.transform.flip(image, True, False)
            for name, img, flip in ((key, image, False), (mirror, flipped, True)):
                self.dalek_sprites[name] = img
                self.dalek_anchor[name] = _base_anchor(img)
                gx, gy = DALEK_GUN_SRC[key]
                ex, ey = DALEK_EYE_SRC[key]
                if flip:
                    gx, ex = sw - 1 - gx, sw - 1 - ex
                self.dalek_gun[name] = ((gx + 0.5) * k, (gy + 0.5) * k)
                self.dalek_eye[name] = ((ex + 0.5) * k, (ey + 0.5) * k)
        _src, self.tardis, tk = _load_scaled(TARDIS_FILE, TARDIS_H)
        self.tardis_anchor = _base_anchor(self.tardis)
        self.tardis_lamp = ((TARDIS_LAMP_SRC[0] + 0.5) * tk, (TARDIS_LAMP_SRC[1] + 0.5) * tk)
        self.dalek_shadow = pygame.Surface((50, 18), pygame.SRCALPHA)
        pygame.draw.ellipse(self.dalek_shadow, (30, 20, 10, 120), self.dalek_shadow.get_rect())
        self.tardis_shadow = pygame.Surface((76, 30), pygame.SRCALPHA)
        pygame.draw.ellipse(self.tardis_shadow, (24, 16, 8, 110), self.tardis_shadow.get_rect())
        # Dematerialisation: pre-faded TARDIS and shadow (alpha copied exactly,
        # scaled with numpy) and a lamp glow at a few brightness levels.
        self.demat_fades = [_alpha_scaled(self.tardis, i / (DEMAT_LEVELS - 1)) for i in range(DEMAT_LEVELS)]
        self.demat_shadows = [_alpha_scaled(self.tardis_shadow, i / (DEMAT_LEVELS - 1)) for i in range(DEMAT_LEVELS)]
        lamp = _make_glow(11, (255, 236, 190))
        self.demat_lamps = []
        for i in range(12):
            g = lamp.copy()
            v = int(255 * i / 11)
            g.fill((v, v, v), special_flags=pygame.BLEND_RGB_MULT)  # opaque surface: safe
            self.demat_lamps.append(g)
        self.scorch = pygame.Surface((34, 14), pygame.SRCALPHA)
        pygame.draw.ellipse(self.scorch, (20, 12, 6, 170), self.scorch.get_rect())
        pygame.draw.ellipse(self.scorch, (10, 6, 4, 200), self.scorch.get_rect().inflate(-14, -6))
        self.glow_eye = _make_glow(int(13 * ZOOM), (190, 235, 255))
        self.glow_hit = _make_glow(int(16 * ZOOM), (140, 200, 255))
        self.puffs = []  # puffs[size][alpha level], pre-faded
        for radius in (2, 3, 4, 5, 6):
            puff = pygame.Surface((radius * 2 + 2, radius * 2 + 2), pygame.SRCALPHA)
            pygame.draw.circle(puff, (214, 236, 190, 255), (radius + 1, radius + 1), radius)
            pygame.draw.circle(puff, (246, 252, 236, 255), (radius, radius), max(1, radius - 2))
            self.puffs.append([_alpha_scaled(puff, i / (PUFF_LEVELS - 1)) for i in range(PUFF_LEVELS)])
        # Full-window flash: a plain (no per-pixel alpha) surface, faded with
        # surface alpha, so it is a translucent wash and never a hard block.
        self.flash = pygame.Surface((WIN_W, WIN_H)).convert()
        self.flash.fill((255, 255, 255))
        self.disguise_cache = {}
        self.shadow = pygame.Surface((40, 16), pygame.SRCALPHA)
        pygame.draw.ellipse(self.shadow, (48, 30, 16, 110), self.shadow.get_rect())
        self.dirt = build_dirt_variants(make_dirt_texture())
        self.hedges = build_hedge_variants()
        self.view_w = max(1, int(round(WIN_W / ZOOM)))
        self.view_h = max(1, int(round(WIN_H / ZOOM)))
        self.view = pygame.Surface((self.view_w, self.view_h)).convert()
        self.font_hint = load_font(18)
        self.font_big = load_font(36, bold=True)
        self.font_small = load_font(20)
        self.font_shout = load_font(16, bold=True)
        self.font_hud = load_font(16)
        self.cam = (0.0, 0.0)
        self.archie_feet = (0, 0)
        self.sfx = Sounds()
        self.given_seed = seed
        self.reset(seed if seed is not None else (time.time_ns() & 0x7FFFFFFF))

    def reset(self, seed: int):
        self.sfx.stop_all()
        self.bump_times = []
        self.last_bump_t = -1e9
        self.rustle_t = -1e9
        self.ow_quiet_until = -1e9
        self.voice_until = -1e9
        self.hops_heard = 0
        self.seed = seed & 0x7FFFFFFF
        self.grid = generate_maze(MAZE_SIZE, self.seed)
        self.hedge_variant = hedge_variant_grid(self.grid, self.seed)
        self.col = 1
        self.row = 1
        self.src = (1, 1)
        self.dst = (1, 1)
        self.facing_index = 0
        self.facing = DIR_ORDER[0]
        self.turn_from = DIR_ORDER[0]
        self.turning = False
        self.turn_t0 = 0
        self.turn_sign = 0
        self.moving = False
        self.move_t0 = 0
        self.won = False
        self.wish = None
        self.queued = None
        self.bump_dir = None
        self.bump_t0 = 0
        self.last_now = None
        self.dead = False
        self.death_t0 = 0.0
        self.dead_pos = (1.0, 1.0)
        self.shooter = None
        self.disguised = False
        self.disguise_t0 = -1e9
        self.disguise_end_t = -1e9
        self.cooldown_until = 0.0
        self.disguise_pending = False
        self.exit_cell = (MAZE_SIZE - 2, MAZE_SIZE - 2)
        self.demat_t0 = None  # set on the first update, which also plays the sound
        self.demat_cell = (1, 1)
        self.demat_back = (-DIR_ORDER[0][0], -DIR_ORDER[0][1])  # behind his start facing
        self.daleks = []
        self._hum_from = None
        self._hum_dist = {}
        self._spawn_daleks()

    # ----- Daleks -------------------------------------------------------
    def _path_dist(self, start):
        dist = {start: 0}
        queue = [start]
        i = 0
        while i < len(queue):
            c, r = queue[i]
            i += 1
            for dc, dr in DIR_ORDER:
                n = (c + dc, r + dr)
                if n not in dist and self.is_open(*n):
                    dist[n] = dist[(c, r)] + 1
                    queue.append(n)
        return dist

    def _spawn_daleks(self):
        rng = random.Random((self.seed * 2654435761 + 12345) & 0xFFFFFFFF)
        from_start = self._path_dist((1, 1))
        from_exit = self._path_dist(self.exit_cell)
        # The full rule is >= 12 cells from the start and >= 10 from the exit;
        # a small maze that cannot fit them all relaxes those distances.
        cands = []
        for k in (1.0, 0.75, 0.5, 0.25, 0.0):
            cands = sorted(
                cell for cell, d in from_start.items()
                if d >= DALEK_MIN_START_DIST * k
                and from_exit.get(cell, 0) >= DALEK_MIN_EXIT_DIST * k
                and self.grid[cell[1]][cell[0]] == PATH
                and cell != (1, 1)
            )
            if len(cands) >= NUM_DALEKS:
                break
        chosen = []
        for _ in range(NUM_DALEKS):
            # Well apart if the maze allows it; relax the spacing step by step.
            pool = []
            for gap in DALEK_SPACING:
                pool = [c for c in cands if c not in chosen
                        and all(abs(c[0] - o[0]) + abs(c[1] - o[1]) >= gap for o in chosen)]
                if pool:
                    break
            pool = pool or [c for c in cands if c not in chosen]
            if not pool:
                break
            chosen.append(rng.choice(pool))
        self.daleks = []
        for i, (c, r) in enumerate(chosen):
            dirs = [d for d in DIR_ORDER if self.is_open(c + d[0], r + d[1])]
            facing = rng.choice(dirs) if dirs else DIR_SE
            self.daleks.append(Dalek(c, r, facing, random.Random(self.seed * 31 + i * 1009 + 7)))

    def _archie_cells(self):
        cells = {(self.col, self.row)}
        if self.moving:
            cells.add(self.dst)
        return cells

    def _dalek_cells(self, exclude=None):
        cells = set()
        for d in self.daleks:
            if d is exclude:
                continue
            cells.add(d.cell())
            cells.add(d.target)
        return cells

    def archie_exposed(self) -> bool:
        return not (self.disguised or self.dead or self.won)

    def _sees(self, d: Dalek) -> bool:
        if not self.archie_exposed():
            return False
        c, r = d.cell()
        dc, dr = d.facing
        archie = self._archie_cells()
        for k in range(1, DALEK_SIGHT + 1):
            cell = (c + dc * k, r + dr * k)
            if not self.is_open(*cell):
                return False
            if cell in archie:
                return True
        return False

    def _choose_next(self, d: Dalek, now: float) -> bool:
        """At a cell centre: pick the next cell. True if it can keep gliding."""
        c, r = d.cell()
        f = d.facing
        back = (-f[0], -f[1])
        others = self._dalek_cells(exclude=d)
        archie = self._archie_cells()
        exposed = self.archie_exposed()
        opts = []
        for dirn in DIR_ORDER:
            n = (c + dirn[0], r + dirn[1])
            if not self.is_open(*n) or n == self.exit_cell or n in others:
                continue
            if n in archie and not exposed:
                continue  # a hedge (or a corpse) is in the way: turn away
            opts.append(dirn)
        pool = [o for o in opts if o != back] or [o for o in opts if o == back]
        if not pool:
            d.wait_until = now + 250
            return False
        dirn = d.rng.choice(pool)
        n = (c + dirn[0], r + dirn[1])
        turned = d.face(dirn, now)
        if n in archie:
            # Bumped into Archie in the open: that counts as seeing him.
            d.state = "aim"
            d.aim_t0 = now
            d.fire_at = now + DALEK_TELEGRAPH_MS + (DALEK_TURN_MS if turned else 0)
            self._shout(now)
            return False
        d.target = n
        if turned:
            d.wait_until = now + DALEK_TURN_MS
            return False
        return True

    def _update_daleks(self, now: float, dt: float):
        for d in self.daleks:
            if d.state == "fire":
                continue
            if d.state == "aim":
                if not self._sees(d):
                    d.state = "roam"  # lost him (hedge, or he slipped away)
                elif now >= d.fire_at:
                    d.state = "fire"
                    d.fire_t0 = now
                    self._kill(now, d)
                continue
            if self._sees(d):
                d.state = "aim"
                d.aim_t0 = now
                d.fire_at = now + DALEK_TELEGRAPH_MS
                self._shout(now)
                continue
            if now < d.wait_until:
                continue
            move = dt / DALEK_STEP_MS
            for _ in range(4):
                tc, tr = d.target
                dx = tc - d.pos[0]
                dy = tr - d.pos[1]
                dist = abs(dx) + abs(dy)
                if dist <= move:
                    d.pos = [float(tc), float(tr)]
                    move -= dist
                    if not self._choose_next(d, now) or move <= 0:
                        break
                else:
                    if dx:
                        d.pos[0] += math.copysign(move, dx)
                    else:
                        d.pos[1] += math.copysign(move, dy)
                    break

    def _shout(self, now: float):
        """'Exterminate!' as the telegraph starts; one voice at a time."""
        if now < self.voice_until:
            return
        self.voice_until = now + self.sfx.length_ms("exterminate", 1600.0)
        self.sfx.play("exterminate")

    def _kill(self, now: float, shooter: Dalek):
        if self.dead or self.won:
            return
        self.sfx.play("laser")
        self.dead_pos = self.visual_pos(now)
        self.dead = True
        self.death_t0 = now
        self.shooter = shooter
        self.moving = False
        self.turning = False
        self.queued = None
        self.bump_dir = None
        self.disguise_pending = False

    # ----- Hedge disguise ----------------------------------------------
    def toggle_disguise(self, now: float):
        if self.dead or self.won:
            return
        if self.disguised:
            self._end_disguise(now)
            return
        if now < self.cooldown_until:
            return
        if self.busy():
            self.disguise_pending = True  # as soon as this hop lands
            self.queued = None
            return
        self._start_disguise(now)

    def _start_disguise(self, now: float):
        self.sfx.play("cloak_on")
        self.disguised = True
        self.disguise_t0 = now
        self.disguise_pending = False
        self.queued = None
        self.wish = None
        self.bump_dir = None

    def _end_disguise(self, now: float):
        self.sfx.play("cloak_off")
        self.disguised = False
        self.disguise_end_t = now
        self.cooldown_until = now + DISGUISE_COOLDOWN_MS

    # ----- Debug scenes for headless screenshots -------------------------
    def _straight_run(self, direction, length: int):
        """First run of length+1 open cells along direction whose inner cells
        are plain corridor (no side openings). Scans from the maze centre."""
        dc, dr = direction
        side = [d for d in DIR_ORDER if d not in (direction, (-dc, -dr))]
        mid = MAZE_SIZE // 2
        cells = sorted(
            ((c, r) for r in range(1, MAZE_SIZE - 1) for c in range(1, MAZE_SIZE - 1)),
            key=lambda p: abs(p[0] - mid) + abs(p[1] - mid),
        )
        for c, r in cells:
            run = [(c + dc * k, r + dr * k) for k in range(length + 1)]
            if not all(self.is_open(*p) and self.grid[p[1]][p[0]] == PATH for p in run):
                continue
            if any(self.is_open(p[0] + s[0], p[1] + s[1]) for p in run[1:-1] for s in side):
                continue
            return run
        return None

    def _place_archie(self, cell, facing):
        self.col, self.row = cell
        self.src = self.dst = cell
        self.facing_index = DIR_ORDER.index(facing)
        self.facing = self.turn_from = facing
        self.moving = self.turning = False

    def _park_other_daleks(self, keep):
        """Move the other Daleks well away so they do not join the scene."""
        far = sorted(
            (abs(c - self.col) + abs(r - self.row), c, r)
            for r in range(MAZE_SIZE) for c in range(MAZE_SIZE)
            if self.grid[r][c] == PATH
        )
        for i, d in enumerate(self.daleks):
            if d is keep:
                continue
            _, c, r = far[-1 - i * 3]
            d.pos = [float(c), float(r)]
            d.target = (c, r)

    def setup_scene(self, name: str, now: float = 0.0) -> float:
        """Arrange a scene and return how long (ms) to simulate before the shot."""
        self.last_now = now
        if name == "tardis_demat":
            # The start of a game: Archie on his start cell, the TARDIS behind him.
            self._park_other_daleks(None)
            self.demat_t0 = now
            self.sfx.play("tardis_demat")
            return 1500.0
        if name == "tardis":
            # Three path cells back from the TARDIS, facing along the way to it.
            dist = self._path_dist(self.exit_cell)
            cell = min((c for c, k in dist.items() if k == 3), default=self.exit_cell)
            facing = next(
                (d for d in DIR_ORDER if dist.get((cell[0] + d[0], cell[1] + d[1])) == 2),
                DIR_SE,
            )
            self._place_archie(cell, facing)
            self._park_other_daleks(None)
            return 0.0
        run = self._straight_run(DIR_SE, 4) or self._straight_run(DIR_SW, 4)
        if run is None:
            raise SystemExit("no straight corridor for the scene")
        fwd = (run[1][0] - run[0][0], run[1][1] - run[0][1])
        back = (-fwd[0], -fwd[1])
        d = self.daleks[0]
        if name == "dalek":
            # Archie behind, the Dalek gliding away from him towards the viewer.
            self._place_archie(run[0], fwd)
            d.pos = [float(run[2][0]), float(run[2][1])]
            d.target = run[3]
            d.facing = d.prev_facing = fwd
            self._park_other_daleks(d)
            return 120.0
        if name == "laser":
            self._place_archie(run[4], back)
            d.pos = [float(run[0][0]), float(run[0][1])]
            d.target = run[0]
            d.facing = d.prev_facing = fwd
            self._park_other_daleks(d)
            return DALEK_TELEGRAPH_MS + 260.0
        if name == "telegraph":
            self._place_archie(run[4], back)
            d.pos = [float(run[0][0]), float(run[0][1])]
            d.target = run[0]
            d.facing = d.prev_facing = fwd
            self._park_other_daleks(d)
            return DALEK_TELEGRAPH_MS * 0.8
        if name == "disguise":
            self._place_archie(run[3], back)
            self._start_disguise(now)
            d.pos = [float(run[0][0]), float(run[0][1])]
            d.target = run[1]
            d.facing = d.prev_facing = fwd
            self._park_other_daleks(d)
            return 620.0
        raise SystemExit(f"unknown scene {name!r}")

    def is_open(self, col: int, row: int) -> bool:
        if not (0 <= col < MAZE_SIZE and 0 <= row < MAZE_SIZE):
            return False
        return self.grid[row][col] != WALL

    def busy(self) -> bool:
        return self.moving or self.turning

    def pose(self, now: float) -> str:
        """At rest, the sprite for the facing he is actually pointing.

        A turn keeps the facing he started on, then settles on the new one.
        The extra side-on pictures do not belong in the middle. The maze does not spin.
        """
        if not self.turning:
            return FACING_SPRITE[self.facing]
        t = (now - self.turn_t0) / TURN_MS
        if t < 0.5:
            return FACING_SPRITE[self.turn_from]
        return FACING_SPRITE[self.facing]

    def _start_turn(self, sign: int, now: float):
        index = self.facing_index
        self.turn_from = DIR_ORDER[index]
        if sign > 0:
            index = (index + 1) % 4
        else:
            index = (index - 1) % 4
        self.facing_index = index
        self.facing = DIR_ORDER[index]
        self.turn_t0 = now
        self.turning = True
        self.turn_sign = sign
        self.bump_dir = None
        self.queued = None

    def _start_step(self, sign: int, now: float) -> bool:
        dc, dr = self.facing
        if sign < 0:
            dc, dr = -dc, -dr
        nc, nr = self.col + dc, self.row + dr
        if not self.is_open(nc, nr) or (nc, nr) in self._dalek_cells():
            if self.bump_dir != (dc, dr):
                self.bump_dir = (dc, dr)
                self.bump_t0 = now
                if not self.is_open(nc, nr):  # a hedge, not a Dalek's cell
                    self._hedge_bump(now)
            return False
        self.bump_dir = None
        self.queued = None
        self.src = (self.col, self.row)
        self.dst = (nc, nr)
        self.move_t0 = now
        self.moving = True
        self.hops_heard = 0
        return True

    def _hedge_bump(self, now: float):
        """Soft rustle per bump; a quiet 'ow' only on the 3rd bump in 2 s."""
        if now - self.last_bump_t < BUMP_COUNT_GAP_MS:
            return
        self.last_bump_t = now
        self.bump_times = [t for t in self.bump_times if now - t < OW_WINDOW_MS]
        self.bump_times.append(now)
        if len(self.bump_times) >= OW_BUMPS and now >= self.ow_quiet_until:
            self.bump_times = []
            self.ow_quiet_until = now + OW_QUIET_MS
            self.sfx.play("ow")
        elif now - self.rustle_t >= RUSTLE_GAP_MS:
            self.rustle_t = now
            self.sfx.play("rustle")

    def try_action(self, action, now: float) -> bool:
        if self.won or self.dead or self.disguised or self.disguise_pending:
            return False
        if self.busy():
            # One queued tap, same idea as the old queued step.
            self.queued = action
            return False
        kind, sign = action
        if kind == "turn":
            self._start_turn(sign, now)
            return True
        return self._start_step(sign, now)

    def _held(self, action, keys) -> bool:
        kind, sign = action
        if kind == "turn" and sign < 0:
            return keys[pygame.K_LEFT] or keys[pygame.K_a]
        if kind == "turn" and sign > 0:
            return keys[pygame.K_RIGHT] or keys[pygame.K_d]
        if kind == "step" and sign > 0:
            return keys[pygame.K_UP] or keys[pygame.K_w]
        if kind == "step" and sign < 0:
            return keys[pygame.K_DOWN] or keys[pygame.K_s]
        return False

    def desired_action(self, keys):
        turns = []
        if keys[pygame.K_LEFT] or keys[pygame.K_a]:
            turns.append(("turn", -1))
        if keys[pygame.K_RIGHT] or keys[pygame.K_d]:
            turns.append(("turn", 1))
        steps = []
        if keys[pygame.K_UP] or keys[pygame.K_w]:
            steps.append(("step", 1))
        if keys[pygame.K_DOWN] or keys[pygame.K_s]:
            steps.append(("step", -1))
        # A held turn finishes before a held step. They never share a frame.
        if turns:
            if self.wish in turns:
                return self.wish
            return turns[0]
        if steps:
            if self.wish in steps:
                return self.wish
            return steps[0]
        return None

    def on_key(self, key: int, now: float):
        if key in RESTART_KEYS and (self.won or (self.dead and now - self.death_t0 >= LASER_MS)):
            self.reset(time.time_ns() & 0x7FFFFFFF)
            return
        if key == MUTE_KEY:
            self.sfx.toggle_mute()
            return
        if key in DISGUISE_KEYS:
            self.toggle_disguise(now)
            return
        action = KEY_ACTIONS.get(key)
        if action is None or self.won or self.dead:
            return
        self.wish = action
        self.try_action(action, now)

    def hold_action(self, keys, now: float):
        if self.busy() or self.won or self.dead or self.disguised:
            return
        action = self.desired_action(keys)
        if action is None:
            return
        self.wish = action
        self.try_action(action, now)

    def nudge(self, now: float):
        """Headless test: step forward, or turn right if that cell is shut."""
        if self.busy() or self.won or self.dead or self.disguised:
            return
        dc, dr = self.facing
        if self.is_open(self.col + dc, self.row + dr):
            self.try_action(("step", 1), now)
        else:
            self.try_action(("turn", 1), now)

    def _fire_queued(self, now: float):
        queued = self.queued
        self.queued = None
        if queued is not None and not self.won:
            self.try_action(queued, now)

    def update(self, now: float):
        dt = 0.0 if self.last_now is None else max(0.0, min(100.0, now - self.last_now))
        self.last_now = now
        if self.demat_t0 is None:
            self.demat_t0 = now
            self.sfx.play("tardis_demat")
        if self.disguised and now - self.disguise_t0 >= DISGUISE_MS:
            self._end_disguise(now)
        if not self.dead:
            self._update_archie(now)
        if self.disguise_pending and not self.busy() and not self.dead and not self.won:
            self.disguise_pending = False
            if now >= self.cooldown_until:
                self._start_disguise(now)
        self._update_daleks(now, dt)
        self._update_hum(now, dt)

    # ----- Dalek proximity hum -------------------------------------------
    def _hum_distance(self, d: Dalek, archie_pos) -> float:
        """Blend of path distance through the maze (hedges block sound) and
        straight-line distance, in cells, from Archie to Dalek d."""
        here = (self.col, self.row)
        if self._hum_from != here:
            self._hum_from = here
            self._hum_dist = self._path_dist(here)
        straight = math.hypot(d.pos[0] - archie_pos[0], d.pos[1] - archie_pos[1])
        tx, ty = d.target
        dx, dy = tx - d.pos[0], ty - d.pos[1]
        frac = min(1.0, abs(dx) + abs(dy))  # how far it still has to go to its target
        to_t = self._hum_dist.get(d.target)
        src = (tx - int(math.copysign(1, dx)) if abs(dx) > 1e-6 else tx,
               ty - int(math.copysign(1, dy)) if abs(dy) > 1e-6 else ty)
        from_s = self._hum_dist.get(src, to_t) if frac > 1e-6 else to_t
        if to_t is None:
            to_t = from_s
        if to_t is None:
            path = straight * 3.0  # not reachable (should not happen in a perfect maze)
        else:
            path = to_t * (1.0 - frac) + from_s * frac
        return HUM_PATH_WEIGHT * path + (1.0 - HUM_PATH_WEIGHT) * straight

    def _update_hum(self, now: float, dt: float):
        active = not (self.dead or self.won or self.sfx.muted)
        k = 1.0 - math.exp(-dt / HUM_DIST_SMOOTH_MS) if dt > 0 else 1.0
        archie_pos = self.visual_pos(now)
        ax, ay = tile_origin(*archie_pos)
        for i, d in enumerate(self.daleks):
            dist = self._hum_distance(d, archie_pos)
            d.hum_dist = dist
            u = max(0.0, min(1.0, (HUM_FAR - dist) / (HUM_FAR - HUM_NEAR)))
            d.near += (u * u - d.near) * k
            if not active:
                d.glide = 0.0 if self.sfx.muted else max(0.0, d.glide - dt / HUM_FADE_OUT_MS)
            elif d.gliding(now):
                d.glide = min(1.0, d.glide + dt / HUM_FADE_IN_MS)
            else:
                d.glide = max(0.0, d.glide - dt / HUM_FADE_OUT_MS)
            vol = HUM_MAX * d.near * d.glide
            if vol < 0.002:
                vol = 0.0
            # Subtle stereo from where the Dalek is on screen, left or right of Archie.
            dx, _ = tile_origin(d.pos[0], d.pos[1])
            pan = max(-1.0, min(1.0, (dx - ax) / (self.view_w / 2))) * HUM_PAN
            left = vol * (1.0 - max(0.0, pan))
            right = vol * (1.0 + min(0.0, pan))
            keep = active and dist < HUM_FAR + 2.0
            self.sfx.set_hum(i, left, right, keep)

    def _update_archie(self, now: float):
        if self.turning:
            if now - self.turn_t0 >= TURN_MS:
                self.turning = False
                self._fire_queued(now)
            return
        if not self.moving:
            return
        # One soft footstep as each half-tile hop lands (two per tile).
        if self.hops_heard == 0 and now - self.move_t0 >= MOVE_MS / 2:
            self.hops_heard = 1
            self.sfx.step()
        if now - self.move_t0 >= MOVE_MS:
            if self.hops_heard < 2:
                self.hops_heard = 2
                self.sfx.step()
            self.col, self.row = self.dst
            self.moving = False
            if self.grid[self.row][self.col] == EXIT:
                self.won = True
                self.queued = None
                return
            self._fire_queued(now)

    def _step_u(self, now: float) -> float:
        """One cell, covered as two half-tile hops."""
        t = (now - self.move_t0) / MOVE_MS
        t = max(0.0, min(1.0, t))
        if t < 0.5:
            return ease(t / 0.5) * 0.5
        return 0.5 + ease((t - 0.5) / 0.5) * 0.5

    def visual_pos(self, now: float):
        if self.dead:
            return self.dead_pos
        if self.moving:
            u = self._step_u(now)
            sc, sr = self.src
            dc, dr = self.dst
            return sc + (dc - sc) * u, sr + (dr - sr) * u
        if self.bump_dir is not None:
            t = (now - self.bump_t0) / BUMP_MS
            if t < 1.0:
                amp = 0.18 * math.sin(math.pi * max(0.0, t))
                dc, dr = self.bump_dir
                return self.col + dc * amp, self.row + dr * amp
            self.bump_dir = None
        return float(self.col), float(self.row)

    def _visible_tiles(self, cam_x, cam_y):
        margin_x = TILE_W + 8
        margin_top = HEDGE_H + TILE_H
        margin_bottom = TILE_H * 2
        tiles = []
        for row in range(MAZE_SIZE):
            for col in range(MAZE_SIZE):
                wx, wy = tile_origin(col, row)
                sx = wx - cam_x
                sy = wy - cam_y
                if sx < -margin_x or sx > self.view_w + margin_x:
                    continue
                if sy > self.view_h + margin_bottom or sy < -margin_top:
                    continue
                tiles.append((float(row + col), col, row, int(round(sx)), int(round(sy))))
        tiles.sort()
        return tiles

    def draw(self, screen: pygame.Surface, now: float):
        view = self.view
        self._draw_world(view, now)
        if view.get_size() == screen.get_size():
            screen.blit(view, (0, 0))
        elif ZOOM_SMOOTH:
            pygame.transform.smoothscale(view, screen.get_size(), screen)
        else:
            pygame.transform.scale(view, screen.get_size(), screen)
        # Effects and HUD at full window resolution, on top of the scaled world.
        self._draw_effects(screen, now)
        self._draw_minimap(screen)
        self._draw_hint(screen)
        self._draw_disguise_hud(screen, now)
        if self.won:
            self._draw_panel(screen, "You reached the TARDIS!", "Press Enter to play again", (255, 244, 214))
        elif self.dead and now - self.death_t0 >= DEATH_MSG_MS:
            self._draw_panel(screen, "EXTERMINATED!", "Press Enter to try again", (255, 96, 72))

    def _draw_world(self, screen: pygame.Surface, now: float):
        screen.fill(BG_COLOUR)
        vcol, vrow = self.visual_pos(now)
        feet_x, feet_y = tile_origin(vcol, vrow)
        feet_y += TILE_H // 2
        # Feet sit near the centre; looking a little above them puts his body
        # just above centre. The maze scrolls; tiles are not yaw-rotated.
        cam_x = feet_x - self.view_w / 2
        cam_y = (feet_y - 46) - self.view_h / 2
        self.cam = (cam_x, cam_y)
        tiles = self._visible_tiles(cam_x, cam_y)

        feet_sx = int(round(feet_x - cam_x))
        feet_sy = int(round(feet_y - cam_y))
        if self.moving:
            t = max(0.0, min(1.0, (now - self.move_t0) / MOVE_MS))
            local = (t * 2.0) % 1.0 if t < 1.0 else 0.0
            feet_sy -= int(round(math.sin(local * math.pi) * 2))
        self.archie_feet = (feet_sx, feet_sy)
        # One pass, back to front. Archie, the Daleks and the TARDIS slot in
        # by depth (row + col) when the tiles in front of them start.
        char_depth = vrow + vcol
        entities = [(char_depth, 1, lambda: self._draw_archie(screen, feet_sx, feet_sy, now))]
        for d in self.daleks:
            entities.append((d.pos[0] + d.pos[1], 0, lambda d=d: self._draw_dalek(screen, d, now, cam_x, cam_y)))
        ec, er = self.exit_cell
        entities.append((float(ec + er), 2, lambda: self._draw_tardis(screen, cam_x, cam_y)))
        if self.demat_t0 is None or now - self.demat_t0 < DEMAT_MS:
            dc, dr = self.demat_cell
            # Drawn just before Archie when he is on the start cell (same depth,
            # lower priority), so he always stands in front of it.
            entities.append((float(dc + dr), 0.5, lambda: self._draw_demat(screen, now, cam_x, cam_y)))
        entities.sort(key=lambda e: (e[0], e[1]))
        k = 0
        for depth, col, row, tx, ty in tiles:
            while k < len(entities) and depth > entities[k][0] + 0.05:
                entities[k][2]()
                k += 1
            cell = self.grid[row][col]
            if cell == WALL:
                self._draw_hedge(screen, col, row, tx, ty)
            else:
                self._draw_dirt(screen, col, row, tx, ty)
        while k < len(entities):
            entities[k][2]()
            k += 1

    def _fog(self, colour, sy: int):
        # Slight aerial perspective: tiles higher on the screen are a touch darker.
        k = 0.88 + 0.14 * max(0.0, min(1.0, sy / self.view_h))
        return mix(colour, k)

    def _draw_dirt(self, screen, col, row, tx: int, ty: int):
        """Clipped dirt diamond in tile space. Not a rotated sprite."""
        variant = (col * 5 + row * 3 + (col ^ row)) % N_DIRT
        cy = ty + TILE_H // 2
        if cy < self.view_h * 0.33:
            shade = 0
        elif cy < self.view_h * 0.66:
            shade = 1
        else:
            shade = 2
        sprite = self.dirt[variant][shade]
        screen.blit(
            sprite,
            (tx - sprite.get_width() // 2, cy - sprite.get_height() // 2),
        )

    def _draw_hedge(self, screen, col: int, row: int, tx: int, ty: int):
        """Pre-rendered leafy block; same footprint and height as the tile."""
        k = max(0.0, min(1.0, ty / self.view_h))
        shade = int(round(k * (N_HEDGE_SHADES - 1)))
        sprite = self.hedges[self.hedge_variant[row][col]][shade]
        screen.blit(sprite, (tx - HEDGE_OX, ty - HEDGE_OY))

    def _draw_tardis(self, screen, cam_x: float, cam_y: float):
        """The TARDIS stands on the exit cell, anchored by the centre of its base."""
        ec, er = self.exit_cell
        fx, fy = tile_origin(ec, er)
        fx -= cam_x
        fy += TILE_H // 2 - cam_y
        img = self.tardis
        if fx < -img.get_width() or fx > self.view_w + img.get_width() or fy < -40 or fy > self.view_h + img.get_height():
            return
        ax, ay = self.tardis_anchor
        sh = self.tardis_shadow
        screen.blit(sh, (int(fx - sh.get_width() / 2), int(fy - sh.get_height() / 2 + 2)))
        screen.blit(img, (int(round(fx - ax)), int(round(fy - ay))))

    def demat_alpha(self, now: float):
        """(TARDIS opacity, lamp brightness), both 0..1, during the dematerialisation.

        Classic fade pulsing: one pulse per second (solid at 0, 1, 2 s, faintest
        at 0.5, 1.5, 2.5 s, as each wheeze-groan swells) inside an overall fade
        that reaches nothing at about 3.3 s. The roof lamp flashes throughout.
        """
        if self.demat_t0 is None:
            return 1.0, 0.0
        t = now - self.demat_t0
        if t < 0 or t >= DEMAT_MS:
            return 0.0, 0.0
        u = min(1.0, t / 3300.0)
        overall = 1.0 - u * u * (3.0 - 2.0 * u)
        pulse = 0.12 + 0.88 * (0.5 + 0.5 * math.cos(2 * math.pi * t / DEMAT_PULSE_MS)) ** 1.5
        alpha = overall * pulse
        flash = (0.5 + 0.5 * math.cos(2 * math.pi * t / 500.0)) ** 2
        lamp = flash * min(1.0, 0.25 + 1.2 * overall) * (1.0 if t < 3300 else 0.0)
        return alpha, lamp

    def _draw_demat(self, screen, now: float, cam_x: float, cam_y: float):
        alpha, lamp = self.demat_alpha(now)
        if alpha <= 0.0 and lamp <= 0.0:
            return
        dc, dr = self.demat_cell
        bc, br = self.demat_back
        fx, fy = tile_origin(dc + bc * DEMAT_BACK, dr + br * DEMAT_BACK)
        fx -= cam_x
        fy += TILE_H // 2 - cam_y
        img_w, img_h = self.tardis.get_size()
        if fx < -img_w or fx > self.view_w + img_w or fy < -40 or fy > self.view_h + img_h:
            return
        level = int(round(alpha * (DEMAT_LEVELS - 1)))
        ax, ay = self.tardis_anchor
        if level > 0:
            sh = self.demat_shadows[level]
            screen.blit(sh, (int(fx - sh.get_width() / 2), int(fy - sh.get_height() / 2 + 2)))
            screen.blit(self.demat_fades[level], (int(round(fx - ax)), int(round(fy - ay))))
        li = int(round(lamp * 11))
        if li > 0:
            g = self.demat_lamps[li]
            lx = fx - ax + self.tardis_lamp[0]
            ly = fy - ay + self.tardis_lamp[1]
            screen.blit(g, (int(lx - g.get_width() / 2), int(ly - g.get_height() / 2)),
                        special_flags=pygame.BLEND_RGB_ADD)

    def _draw_dalek(self, screen, d: Dalek, now: float, cam_x: float, cam_y: float):
        fx, fy = tile_origin(d.pos[0], d.pos[1])
        fx = int(round(fx - cam_x))
        fy = int(round(fy + TILE_H // 2 - cam_y))
        d.feet = (fx, fy)
        if fx < -80 or fx > self.view_w + 80 or fy < -20 or fy > self.view_h + DALEK_H + 20:
            return
        key = d.sprite_key(now)
        img = self.dalek_sprites[key]
        ax, ay = self.dalek_anchor[key]
        sh = self.dalek_shadow
        screen.blit(sh, (fx - sh.get_width() // 2, fy - sh.get_height() // 2 + 1))
        screen.blit(img, (int(round(fx - ax)), int(round(fy - ay))))

    def _dalek_point(self, d: Dalek, now: float, table):
        """A point on a Dalek sprite (gun or eye) in view coordinates."""
        key = d.sprite_key(now)
        ax, ay = self.dalek_anchor[key]
        px, py = table[key]
        return d.feet[0] - ax + px, d.feet[1] - ay + py

    def _disguise_sprite(self, scale: float, shade: int):
        variant = ((self.col * 7 + self.row * 13 + self.seed) * 2654435761 >> 7) % N_HEDGE
        base = self.hedges[variant][shade]
        key = (variant, shade, round(scale, 2))
        cached = self.disguise_cache.get(key)
        if cached is None:
            w = max(1, int(round(base.get_width() * scale)))
            h = max(1, int(round(base.get_height() * scale)))
            cached = pygame.transform.smoothscale(base, (w, h))
            if len(self.disguise_cache) > 64:
                self.disguise_cache.clear()
            self.disguise_cache[key] = cached
        return cached

    def _draw_poof(self, screen, fx: int, fy: int, t: float):
        """A little cloud of leaf-dust; t runs 0..1."""
        if not 0.0 <= t <= 1.0:
            return
        alpha = int(235 * (1.0 - t) ** 1.3)
        reach = 6 + 22 * ease(t)
        for i in range(12):
            ang = i * (math.tau / 12) + (i % 3) * 0.35
            r = reach * (0.75 + 0.25 * ((i * 7) % 5) / 4)
            px = fx + math.cos(ang) * r
            py = fy - 18 + math.sin(ang) * r * 0.6
            sizes = self.puffs[max(0, min(4, 4 - int(t * 4) + (i % 2) - 1))]
            puff = sizes[max(0, min(PUFF_LEVELS - 1, round(alpha / 255 * (PUFF_LEVELS - 1))))]
            screen.blit(puff, (int(px - puff.get_width() / 2), int(py - puff.get_height() / 2)))

    def _draw_archie(self, screen, feet_sx: int, feet_sy: int, now: float):
        key = self.pose(now)
        sprite = self.sprites[key]
        ax, ay = self.anchors[key]
        pos = (int(round(feet_sx - ax)), int(round(feet_sy - ay)))
        if self.dead:
            t = now - self.death_t0
            screen.blit(self.scorch, (feet_sx - self.scorch.get_width() // 2, feet_sy - 7))
            ghosts = self.white[key]
            if t < LASER_MS:
                screen.blit(ghosts[0] if int(t / 45) % 2 == 0 else sprite, pos)
            elif t < DEATH_FADE_MS:
                u = (t - LASER_MS) / (DEATH_FADE_MS - LASER_MS)
                level = max(0, min(len(ghosts) - 1, int(u * (len(ghosts) - 1) + 0.5)))
                screen.blit(ghosts[level], pos)
            return
        shade = int(round(max(0.0, min(1.0, (feet_sy - TILE_H // 2) / self.view_h)) * (N_HEDGE_SHADES - 1)))
        since_on = now - self.disguise_t0
        since_off = now - self.disguise_end_t
        if self.disguised:
            if since_on < POOF_MS:
                u = since_on / POOF_MS
                # ease-out with a little overshoot
                pop = 1.0 + 0.12 * math.sin(math.tau * (u - 0.5)) if u > 0.5 else 0.35 + 0.65 * ease(u * 2)
                scale = DISGUISE_SCALE * pop
            else:
                scale = DISGUISE_SCALE
            self._blit_disguise(screen, feet_sx, feet_sy, scale, shade)
            if since_on > POOF_MS * 0.7:
                self._draw_peek_eyes(screen, feet_sx, feet_sy, now)
            self._draw_poof(screen, feet_sx, feet_sy, since_on / POOF_MS)
            return
        screen.blit(self.shadow, (feet_sx - self.shadow.get_width() // 2, feet_sy - 6))
        screen.blit(sprite, pos)
        if since_off < POOF_MS:
            u = since_off / POOF_MS
            self._blit_disguise(screen, feet_sx, feet_sy, DISGUISE_SCALE * (1.0 - ease(u)), shade)
            self._draw_poof(screen, feet_sx, feet_sy, u)

    def _draw_peek_eyes(self, screen, fx: int, fy: int, now: float):
        """Two little eyes peeping over the hedge so the player can find him."""
        y = fy - 32
        if (now - self.disguise_t0) % 2600 > 2470:  # blink
            for ex in (fx - 7, fx + 2):
                pygame.draw.line(screen, (18, 36, 16), (ex, y + 2), (ex + 4, y + 2))
            return
        look = 2 if self.facing in (DIR_SE, DIR_NE) else 0
        for ex in (fx - 7, fx + 2):
            pygame.draw.rect(screen, (18, 36, 16), (ex - 1, y - 1, 7, 6))
            pygame.draw.rect(screen, (248, 248, 238), (ex, y, 5, 4))
            pygame.draw.rect(screen, (24, 20, 16), (ex + 1 + look // 2, y + 1, 2, 2))

    def _blit_disguise(self, screen, fx: int, fy: int, scale: float, shade: int):
        if scale < 0.05:
            return
        img = self._disguise_sprite(scale, shade)
        k = img.get_width() / HEDGE_SW
        # Ground-diamond centre of the hedge sprite sits on Archie's feet.
        screen.blit(img, (int(round(fx - HEDGE_OX * k)), int(round(fy - (HEDGE_OY + TILE_H // 2) * k))))

    def _to_window(self, x: float, y: float):
        return x * WIN_W / self.view_w, y * WIN_H / self.view_h

    def _draw_effects(self, screen, now: float):
        """Telegraph glow, shout, laser and flash, drawn at window resolution."""
        for d in self.daleks:
            if d.state == "aim":
                u = max(0.0, min(1.0, (now - d.aim_t0) / max(1.0, d.fire_at - d.aim_t0)))
                ex, ey = self._to_window(*self._dalek_point(d, now, self.dalek_eye))
                flick = 0.75 + 0.25 * math.sin(now * 0.06)
                g = self.glow_eye
                size = max(4, int(g.get_width() * (0.45 + 0.75 * u) * flick))
                glow = pygame.transform.scale(g, (size, size))
                screen.blit(glow, (int(ex - size / 2), int(ey - size / 2)), special_flags=pygame.BLEND_RGB_ADD)
                screen.blit(glow, (int(ex - size / 2), int(ey - size / 2)), special_flags=pygame.BLEND_RGB_ADD)
            if d.state == "aim" or (d.state == "fire" and now - d.fire_t0 < LASER_MS + 400):
                self._draw_shout(screen, d, now)
        if self.dead and self.shooter is not None:
            t = now - self.death_t0
            if t < LASER_MS:
                gx, gy = self._to_window(*self._dalek_point(self.shooter, now, self.dalek_gun))
                fx, fy = self.archie_feet
                tx, ty = self._to_window(fx, fy - 34)
                self._draw_laser(screen, (gx, gy), (tx, ty), now, t)
            if t < FLASH_MS:
                self.flash.set_alpha(int(FLASH_ALPHA * (1.0 - t / FLASH_MS) ** 2))
                screen.blit(self.flash, (0, 0))

    def _draw_shout(self, screen, d: Dalek, now: float):
        fx, fy = d.feet
        x, y = self._to_window(fx, fy - DALEK_H - 6)
        jig = int(math.sin(now * 0.05) * 1.5)
        text = "EXTERMINATE!"
        fg = self.font_shout.render(text, True, (255, 236, 120))
        bg = self.font_shout.render(text, True, (60, 10, 6))
        bx = int(x - fg.get_width() / 2) + jig
        by = int(y - fg.get_height())
        for ox, oy in ((-1, 0), (1, 0), (0, -1), (0, 1), (1, 1)):
            screen.blit(bg, (bx + ox, by + oy))
        screen.blit(fg, (bx, by))

    def _draw_laser(self, screen, start, end, now: float, t: float):
        rng = random.Random(int(now // 33))
        x0, y0 = start
        x1, y1 = end
        pad = 24
        left = int(min(x0, x1)) - pad
        top = int(min(y0, y1)) - pad
        w = int(abs(x1 - x0)) + pad * 2
        h = int(abs(y1 - y0)) + pad * 2
        layer = pygame.Surface((w, h))
        layer.fill((0, 0, 0))
        a = (x0 - left, y0 - top)
        b = (x1 - left, y1 - top)
        fade = 1.0 if t < LASER_MS * 0.6 else max(0.0, 1.0 - (t - LASER_MS * 0.6) / (LASER_MS * 0.4))
        j = rng.uniform(0.7, 1.25) * fade
        for width, colour in ((18, (20, 45, 110)), (10, (50, 110, 220)), (5, (150, 205, 255)), (2, (255, 255, 255))):
            wid = max(1, int(width * j))
            col = tuple(int(c * fade) for c in colour)
            pygame.draw.line(layer, col, a, b, wid)
        screen.blit(layer, (left, top), special_flags=pygame.BLEND_RGB_ADD)
        for (px, py), glow in (((x0, y0), self.glow_eye), ((x1, y1), self.glow_hit)):
            size = max(4, int(glow.get_width() * rng.uniform(0.8, 1.15) * fade))
            g = pygame.transform.scale(glow, (size, size))
            screen.blit(g, (int(px - size / 2), int(py - size / 2)), special_flags=pygame.BLEND_RGB_ADD)

    def _draw_disguise_hud(self, screen, now: float):
        if self.disguised:
            left = max(0.0, DISGUISE_MS - (now - self.disguise_t0))
            label = f"Hiding as a hedge  {left / 1000:.1f} s   (H to stop)"
            frac = left / DISGUISE_MS
            bar = (96, 196, 84)
        elif now < self.cooldown_until:
            left = self.cooldown_until - now
            label = f"Hedge disguise recharging  {left / 1000:.1f} s"
            frac = 1.0 - left / DISGUISE_COOLDOWN_MS
            bar = (150, 128, 84)
        else:
            label = "Hedge disguise ready  (H)"
            frac = 1.0
            bar = (96, 196, 84)
        text = self.font_hud.render(label, True, (240, 234, 214))
        pad_x, pad_y = 12, 8
        bw = max(text.get_width(), 220)
        box = pygame.Surface((bw + pad_x * 2, text.get_height() + pad_y * 2 + 10), pygame.SRCALPHA)
        box.fill((36, 24, 16, 190))
        pygame.draw.rect(box, (186, 160, 96, 200), box.get_rect(), 1)
        box.blit(text, (pad_x, pad_y))
        by = pad_y + text.get_height() + 4
        pygame.draw.rect(box, (20, 14, 10, 230), (pad_x, by, bw, 6))
        pygame.draw.rect(box, bar, (pad_x, by, int(bw * max(0.0, min(1.0, frac))), 6))
        screen.blit(box, (WIN_W - box.get_width() - 14, WIN_H - box.get_height() - 14))

    def _draw_minimap(self, screen):
        scale = 3
        pad = 6
        size = MAZE_SIZE * scale
        box = pygame.Surface((size + pad * 2, size + pad * 2), pygame.SRCALPHA)
        box.fill((36, 24, 16, 200))
        pygame.draw.rect(box, (186, 160, 96, 200), box.get_rect(), 1)
        for row in range(MAZE_SIZE):
            for col in range(MAZE_SIZE):
                cell = self.grid[row][col]
                if cell == WALL:
                    colour = (28, 72, 36)
                elif cell == EXIT:
                    colour = (142, 98, 56)
                else:
                    colour = (142, 98, 56)
                box.fill(colour, (pad + col * scale, pad + row * scale, scale, scale))
        ec, er = self.exit_cell
        pygame.draw.circle(box, (70, 130, 255), (pad + ec * scale + 1, pad + er * scale + 1), 3)
        for d in self.daleks:
            c, r = d.cell()
            pygame.draw.circle(box, (235, 40, 36), (pad + c * scale + 1, pad + r * scale + 1), 2)
        px = pad + int(self.col * scale)
        py = pad + int(self.row * scale)
        pygame.draw.rect(box, (255, 248, 230), (px, py, scale, scale))
        x = WIN_W - box.get_width() - 14
        screen.blit(box, (x, 14))

    def _draw_hint(self, screen):
        mute = "M to unmute" if self.sfx.muted else "M to mute"
        text = self.font_hint.render(
            f"Left and right to turn. Up to step forward. H to hide as a hedge. {mute}", True, (240, 234, 214)
        )
        pad_x, pad_y = 12, 8
        box = pygame.Surface((text.get_width() + pad_x * 2, text.get_height() + pad_y * 2), pygame.SRCALPHA)
        box.fill((36, 24, 16, 180))
        pygame.draw.rect(box, (186, 160, 96, 200), box.get_rect(), 1)
        x, y = 14, WIN_H - box.get_height() - 14
        screen.blit(box, (x, y))
        screen.blit(text, (x + pad_x, y + pad_y))

    def _draw_panel(self, screen, title_text: str, sub_text: str, title_colour):
        title = self.font_big.render(title_text, True, title_colour)
        sub = self.font_small.render(sub_text, True, (232, 214, 170))
        gap = 10
        width = max(title.get_width(), sub.get_width()) + 56
        height = title.get_height() + sub.get_height() + gap + 36
        panel = pygame.Surface((width, height), pygame.SRCALPHA)
        panel.fill((36, 24, 16, 255))
        pygame.draw.rect(panel, (212, 170, 90), panel.get_rect(), 2)
        panel.blit(title, ((width - title.get_width()) // 2, 16))
        panel.blit(sub, ((width - sub.get_width()) // 2, 16 + title.get_height() + gap))
        screen.blit(panel, ((WIN_W - width) // 2, (WIN_H - height) // 2))


def parse_args(argv):
    parser = argparse.ArgumentParser(description="Archie's isometric hedge maze")
    parser.add_argument("--seed", type=int, default=None, help="maze seed (default: time)")
    parser.add_argument("--screenshot", type=str, default=None, help="save a frame to this path and quit")
    parser.add_argument("--frames", type=int, default=None, help="after the first frame, simulate N movement frames")
    parser.add_argument("--scene", choices=("dalek", "laser", "telegraph", "disguise", "tardis", "tardis_demat"), default=None,
                        help="debug: arrange a scene, simulate it briefly, then screenshot")
    parser.add_argument("--scene-ms", type=float, default=None, help="debug: override the scene's simulated time")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        pygame.mixer.pre_init(MIXER_FREQ, -16, 2, MIXER_BUFFER)
    except Exception:
        pass
    pygame.init()
    pygame.display.set_caption("Archie's Hedge Maze")
    screen = pygame.display.set_mode((WIN_W, WIN_H))
    game = Game(args.seed)
    headless = args.screenshot is not None or args.frames is not None or args.scene is not None

    if not headless:
        clock = pygame.time.Clock()
        running = True
        while running:
            clock.tick(60)
            now = pygame.time.get_ticks()
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        running = False
                    else:
                        game.on_key(event.key, now)
            if not running:
                break
            game.hold_action(pygame.key.get_pressed(), now)
            game.update(now)
            game.draw(screen, now)
            pygame.display.flip()
        pygame.quit()
        return 0

    now = 0.0
    if args.scene:
        sim = game.setup_scene(args.scene, now)
        if args.scene_ms is not None:
            sim = args.scene_ms
        end = now + sim
        while now < end:
            now = min(end, now + 1000.0 / 60.0)
            game.update(now)
    game.draw(screen, now)
    pygame.display.flip()
    if args.scene and not args.frames:
        if args.screenshot:
            pygame.image.save(screen, args.screenshot)
        pygame.quit()
        return 0
    if args.screenshot:
        folder = os.path.dirname(os.path.abspath(args.screenshot))
        if folder:
            os.makedirs(folder, exist_ok=True)
        pygame.image.save(screen, args.screenshot)
    frames = args.frames or 0
    for _ in range(frames):
        now += 1000.0 / 60.0
        game.nudge(now)
        game.update(now)
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                return 0
        game.draw(screen, now)
        pygame.display.flip()
    pygame.quit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
