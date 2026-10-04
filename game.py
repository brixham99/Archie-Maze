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
LAMP_GLOW_FILE = os.path.join(HERE, "assets", "fx", "lamp_glow.png")  # tools/make_fx.py

# --- Daleks, the TARDIS and the hedge disguise (pre-zoom pixels, ms) ---
DALEK_H = 86                 # Archie is SPRITE_H = 74
TARDIS_H = 124
NUM_DALEKS = 3               # on level 1; each level adds two more ...
DALEKS_PER_LEVEL = 2
MAX_DALEKS = 15              # ... up to this many (the 41x41 maze stays fair)
DALEK_STEP_MS = 260          # per cell, gliding; Archie takes MOVE_MS = 150
DALEK_TURN_MS = 160          # pause when a Dalek changes direction
DALEK_SIGHT = 8              # cells along the corridor it is facing
DALEK_TELEGRAPH_MS = 350     # eye-stalk glow before the shot
DALEK_MIN_START_DIST = 12    # path distance from Archie's start
DALEK_MIN_EXIT_DIST = 10     # path distance from the exit
LASER_MS = 450               # how long the beam stays on screen
LASER_WIDTHS = (7, 5, 3, 1)  # px at window resolution: solid lines, widest first
LASER_COLOURS = ((30, 70, 190), (70, 140, 250), (160, 210, 255), (255, 255, 255))
LASER_HOT = ((40, 95, 225), (110, 175, 255), (200, 232, 255), (255, 255, 255))  # flicker frames
LASER_TIP_GLOW = ((70, 140, 250), (170, 220, 255), (255, 255, 255))  # solid circles, outside in
LASER_HIT_GLOW = ((60, 120, 235), (160, 210, 255), (255, 255, 255))
EYE_GLOW = ((80, 160, 250), (180, 228, 255), (255, 255, 255))
DEATH_FADE_MS = 900          # Archie flickers, whites out and fades
DEATH_MSG_MS = 1000          # then the EXTERMINATED! panel
DEATH_FADE_LEVELS = 16
# (No full-window flash on the shot. The beam and its glows are solid draw
# calls; everything is drawn into an opaque back buffer, never with alpha
# straight onto the window surface - see Game.draw.)
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
DEMAT_WAIT_MS = 5000         # it stands solid for 5 s before it starts to go
DEMAT_MS = 3600              # effect length with our own sound; the box is gone 300 ms before the end
DEMAT_MIN_MS = 3000          # with a user-supplied sound, the fade follows its length ...
DEMAT_MAX_MS = 15000         # ... clamped to 3-15 s
DEMAT_END_GAP_MS = 300       # the box has fully faded this long before the effect ends
DEMAT_PULSE_MS = 1000        # one fade pulse (and one wheeze-groan) per second (longer for long clips)
DEMAT_LEVELS = 24            # pre-faded copies of the TARDIS (no set_alpha on RGBA)
TARDIS_LAMP_SRC = (59, 11)   # roof lamp in the 119x200 source image
DISGUISE_KEYS = (pygame.K_h, pygame.K_LSHIFT, pygame.K_RSHIFT)
MUTE_KEY = pygame.K_m

# --- Reaching the TARDIS: Archie goes in, it dematerialises, next level ---
EXIT_WALK_MS = 500           # Archie walks on from his corridor into the TARDIS ...
EXIT_FADE_FROM = 0.3         # ... fading out from 30% of the way ...
EXIT_FADE_TO = 0.9           # ... to gone at 90% (normal depth order: hedges and the box hide him)
EXIT_DEMAT_AT = 900          # then the TARDIS dematerialises (same as the start)
EXIT_CARD_GAP_MS = 250       # short pause once it has gone
CARD_FADE_MS = 450           # fade to black, the new maze is made ...
CARD_HOLD_MS = 1000          # ... "Level N" on black ...
LEVEL_BANNER_MS = 2600       # "Level N" banner at the start of a level
COMPLETE_TEXT = "Level complete!"
COMPLETE_SIZE = 40           # plain white text with a soft drop shadow, window resolution
COMPLETE_Y = 0.2             # its top, as a fraction of the window height (clear of the TARDIS)
COMPLETE_FADE_IN_MS = 300
COMPLETE_FADE_OUT_MS = 400

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
# Optional user-supplied TARDIS sound (not included, git-ignored). The first of
# these that pygame can load replaces our synthesised tardis_demat.wav.
TARDIS_REAL_FILES = ("tardis_real.wav", "tardis_real.ogg", "tardis_real.mp3")
TARDIS_REAL_VOLUME = 0.7
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
HUM_CHANNELS = 4             # reserved hum channels, given to the loudest Daleks
HUM_MAX = 0.5                # channel volume when a Dalek is right next to Archie
HUM_FAR = 25.0               # silent at this effective distance (cells) ...
HUM_NEAR = 1.0               # ... full volume at this one or closer
HUM_CURVE = 1.0              # volume = closeness ** 1.0 (linear): faint but clear far off, louder up close
HUM_STOP_DIST = 28.0         # beyond this (and silent) its channel is stopped
HUM_PATH_WEIGHT = 0.0        # 0: straight-line distance only; heard through hedges, any route
HUM_SUM_MAX = 0.8            # several Daleks at once: all hums scale down so their sum stays below this
HUM_GAIN_SMOOTH_MS = 250     # (that scaling changes smoothly)
HUM_SWAP_MS = 120            # a channel crossfades to a louder Dalek over this long ...
HUM_SWAP_MARGIN = 1.3        # ... once the newcomer is this much louder than the quietest one
HUM_FADE_OUT_MS = 80         # quick fade when a Dalek stops to turn (pause is 160 ms)
HUM_FADE_IN_MS = 110         # and back up as it glides off again
HUM_EXIT_FADE_MS = 1000      # gentle fade as the Daleks freeze when Archie reaches the TARDIS
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


def daleks_for_level(level: int) -> int:
    """3 on level 1, two more each level, capped at MAX_DALEKS."""
    return min(MAX_DALEKS, NUM_DALEKS + DALEKS_PER_LEVEL * (max(1, level) - 1))


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
    mask = _new_rgba((sw, sh))
    pygame.draw.polygon(mask, (255, 255, 255, 255), fill_pts)
    mask_alpha = pygame.surfarray.array_alpha(mask)
    variants = []
    for i in range(N_DIRT):
        ox = (i * 53 + 17) % tw
        oy = (i * 37 + 11) % th
        patch = pygame.Surface((sw + tw, sh + th))
        patch.blit(texture, (0, 0))
        patch.blit(texture, (tw, 0))
        patch.blit(texture, (0, th))
        patch.blit(texture, (tw, th))
        base = _new_rgba((sw, sh))
        base.blit(patch, (-ox, -oy))
        # The diamond's alpha copied in directly (no blend-mode blits).
        alpha = pygame.surfarray.pixels_alpha(base)
        alpha[:] = mask_alpha
        del alpha
        pygame.draw.polygon(base, DIRT_EDGE, raw, 1)
        shades = []
        for factor in DIRT_SHADES:
            shaded = base.copy()
            rgb = pygame.surfarray.pixels3d(shaded)
            rgb[:] = np.clip(rgb.astype(np.float32) * factor, 0, 255).astype(np.uint8)
            del rgb
            shades.append(_finish_rgba(shaded))
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


def _new_rgba(size) -> pygame.Surface:
    """A blank per-pixel-alpha surface: 32-bit, explicitly cleared to fully
    transparent (never relying on how new memory is initialised)."""
    surf = pygame.Surface((max(1, int(size[0])), max(1, int(size[1]))), pygame.SRCALPHA, 32)
    surf.fill((0, 0, 0, 0))
    return surf


def _finish_rgba(surf: pygame.Surface) -> pygame.Surface:
    """Converted to the display's per-pixel-alpha format (the same path the
    sprites take from image.load().convert_alpha()), so blits behave the same
    on every pygame/SDL build. Before a display exists it is left as it is."""
    if pygame.display.get_init() and pygame.display.get_surface() is not None:
        return surf.convert_alpha()
    return surf


def _rgba_from_array(arr) -> pygame.Surface:
    """Surface from an explicit (H, W, 4) uint8 RGBA array: every pixel's alpha
    is written by us, then converted like the sprites."""
    arr = np.ascontiguousarray(arr, dtype=np.uint8)
    H, W, _ = arr.shape
    surf = pygame.image.frombuffer(arr.tobytes(), (W, H), "RGBA")
    return _finish_rgba(surf) if pygame.display.get_surface() is not None else surf.copy()


def _rgba_surface(arr):
    return _rgba_from_array(arr)


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
    return src, _finish_rgba(pygame.transform.smoothscale(src, (w, height))), k


def _alpha_scaled(image: pygame.Surface, k: float) -> pygame.Surface:
    """Copy of a per-pixel-alpha surface with its alpha multiplied by k."""
    out = image.copy()
    alpha = pygame.surfarray.pixels_alpha(out)
    alpha[:] = (pygame.surfarray.array_alpha(image).astype(np.float32) * k).astype(np.uint8)
    del alpha
    return out


def _shadowed_text_fades(font: pygame.font.Font, text: str, levels: int):
    """Plain white text with a soft dark drop shadow, composited once into a
    per-pixel-alpha surface; returns pre-faded copies, index 0 invisible and
    the last one solid. Drawn straight onto the window: no scaling, no wobble."""
    glyphs = font.render(text, True, (255, 255, 255))
    w, h = glyphs.get_size()
    pad, off = 4, 2
    W, H = w + pad * 2, h + pad * 2
    a_text = np.zeros((W, H), np.float32)
    a_text[pad:pad + w, pad:pad + h] = pygame.surfarray.array_alpha(glyphs) / 255.0
    # Shadow: the glyph alpha, offset down-right and softened with a 3x3 box blur.
    a_sh = np.zeros((W, H), np.float32)
    a_sh[pad + off:pad + off + w, pad + off:pad + off + h] = pygame.surfarray.array_alpha(glyphs)[:W - pad - off, :H - pad - off] / 255.0
    p = np.pad(a_sh, 1)
    a_sh = sum(p[1 + dx:1 + dx + W, 1 + dy:1 + dy + H] for dx in (-1, 0, 1) for dy in (-1, 0, 1)) / 9.0
    a_sh *= 0.7
    a_out = a_text + a_sh * (1.0 - a_text)
    lum = np.where(a_out > 0, 255.0 * a_text / np.maximum(a_out, 1e-6), 0.0)
    arr = np.zeros((H, W, 4), np.uint8)
    arr[..., :3] = np.clip(lum, 0, 255).astype(np.uint8).T[:, :, None]
    arr[..., 3] = np.clip(a_out * 255.0 + 0.5, 0, 255).astype(np.uint8).T
    out = _rgba_from_array(arr)
    return [_alpha_scaled(out, i / (levels - 1)) for i in range(levels)]


def _faded_silhouettes(image: pygame.Surface, levels: int):
    """White silhouettes of a sprite: index 0 opaque, the last one invisible."""
    white = image.copy()
    rgb = pygame.surfarray.pixels3d(white)
    rgb[:] = 255
    del rgb
    return [_alpha_scaled(white, 1.0 - i / (levels - 1)) for i in range(levels)]


def _make_glow(radius: int, colour, strength: float = 1.0) -> pygame.Surface:
    """Soft radial glow as a per-pixel-alpha sprite, blitted normally (no blend
    flags): colour fading out from a whiter centre, alpha falling to 0."""
    size = radius * 2 + 1
    yy, xx = np.mgrid[0:size, 0:size]
    d = np.sqrt((xx - radius) ** 2 + (yy - radius) ** 2) / max(1, radius)
    fall = np.clip(1.0 - d, 0.0, 1.0)
    core = fall ** 3
    rgb = np.array(colour, dtype=np.float64)[None, None, :] * (1 - core[..., None]) + 255.0 * core[..., None]
    arr = np.zeros((size, size, 4), np.uint8)  # (row, col, RGBA)
    arr[..., :3] = rgb.clip(0, 255).astype(np.uint8)
    arr[..., 3] = (255.0 * strength * fall ** 1.6).clip(0, 255).astype(np.uint8)
    return _rgba_from_array(arr)


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
        self.hum_levels = [(0.0, 0.0)] * HUM_CHANNELS  # last (left, right) per hum channel
        self.demat_source = "tardis_demat.wav"       # or the user's tardis_real.* file
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
            pygame.mixer.set_reserved(HUM_CHANNELS)
            self.hum_channels = [pygame.mixer.Channel(i) for i in range(HUM_CHANNELS)]
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
        for filename in TARDIS_REAL_FILES:
            path = os.path.join(SOUND_DIR, filename)
            if not os.path.exists(path):
                continue
            try:
                snd = pygame.mixer.Sound(path)
                if snd.get_length() <= 0.0:
                    continue
                snd.set_volume(TARDIS_REAL_VOLUME)
                self.sounds["tardis_demat"] = snd
                self.demat_source = filename
                break
            except Exception:
                continue  # unreadable (e.g. no mp3 support): try the next, else ours

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
        self.hum_levels = [(0.0, 0.0)] * HUM_CHANNELS
        for ch in self.hum_channels:
            try:
                ch.stop()
            except Exception:
                pass

    def stop_all(self):
        self.hum_levels = [(0.0, 0.0)] * HUM_CHANNELS
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
        self.hum_lr = (0.0, 0.0)  # (left, right) volume it wants
        self.hum_vol = 0.0

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
    def __init__(self, seed: int | None, level: int = 1):
        self.sprites = {}
        self.anchors = {}
        for key, path in SPRITE_FILES.items():
            image = pygame.image.load(path).convert_alpha()
            h = image.get_height()
            if h != SPRITE_H:
                w = max(1, round(image.get_width() * SPRITE_H / h))
                image = _finish_rgba(pygame.transform.smoothscale(image, (w, SPRITE_H)))
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
            flipped = _finish_rgba(pygame.transform.flip(image, True, False))
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
        self.tardis_k = tk
        self.tardis_anchor = _base_anchor(self.tardis)
        self.tardis_lamp = ((TARDIS_LAMP_SRC[0] + 0.5) * tk, (TARDIS_LAMP_SRC[1] + 0.5) * tk)
        self.dalek_shadow = _new_rgba((50, 18))
        pygame.draw.ellipse(self.dalek_shadow, (30, 20, 10, 120), self.dalek_shadow.get_rect())
        self.dalek_shadow = _finish_rgba(self.dalek_shadow)
        self.tardis_shadow = _new_rgba((76, 30))
        pygame.draw.ellipse(self.tardis_shadow, (24, 16, 8, 110), self.tardis_shadow.get_rect())
        self.tardis_shadow = _finish_rgba(self.tardis_shadow)
        # Dematerialisation: pre-faded TARDIS and shadow (alpha copied exactly,
        # scaled with numpy) and a lamp glow at a few brightness levels.
        self.demat_fades = [_alpha_scaled(self.tardis, i / (DEMAT_LEVELS - 1)) for i in range(DEMAT_LEVELS)]
        self.demat_shadows = [_alpha_scaled(self.tardis_shadow, i / (DEMAT_LEVELS - 1)) for i in range(DEMAT_LEVELS)]
        if os.path.exists(LAMP_GLOW_FILE):
            lamp = pygame.image.load(LAMP_GLOW_FILE).convert_alpha()
        else:  # (run tools/make_fx.py to write it)
            lamp = _make_glow(11, (255, 236, 190))
        self.demat_lamps = [_alpha_scaled(lamp, i / 11) for i in range(12)]
        self.scorch = _new_rgba((34, 14))
        pygame.draw.ellipse(self.scorch, (20, 12, 6, 170), self.scorch.get_rect())
        pygame.draw.ellipse(self.scorch, (10, 6, 4, 200), self.scorch.get_rect().inflate(-14, -6))
        self.scorch = _finish_rgba(self.scorch)
        self.puffs = []  # puffs[size][alpha level], pre-faded
        for radius in (2, 3, 4, 5, 6):
            puff = _new_rgba((radius * 2 + 2, radius * 2 + 2))
            pygame.draw.circle(puff, (214, 236, 190, 255), (radius + 1, radius + 1), radius)
            pygame.draw.circle(puff, (246, 252, 236, 255), (radius, radius), max(1, radius - 2))
            puff = _finish_rgba(puff)
            self.puffs.append([_alpha_scaled(puff, i / (PUFF_LEVELS - 1)) for i in range(PUFF_LEVELS)])
        self.disguise_cache = {}
        self.shadow = _new_rgba((40, 16))
        pygame.draw.ellipse(self.shadow, (48, 30, 16, 110), self.shadow.get_rect())
        self.shadow = _finish_rgba(self.shadow)
        self.dirt = build_dirt_variants(make_dirt_texture())
        self.hedges = build_hedge_variants()
        self.view_w = max(1, int(round(WIN_W / ZOOM)))
        self.view_h = max(1, int(round(WIN_H / ZOOM)))
        self.view = pygame.Surface((self.view_w, self.view_h)).convert()
        self.frame = None  # opaque window-sized back buffer, made on the first draw
        self.font_hint = load_font(18)
        self.font_big = load_font(36, bold=True)
        self.font_small = load_font(20)
        self.font_shout = load_font(16, bold=True)
        self.font_hud = load_font(16)
        self.cam = (0.0, 0.0)
        self.archie_feet = (0, 0)
        self.sfx = Sounds()
        self.given_seed = seed
        self.level = max(1, int(level))
        # Full-window fade for the level card: a per-pixel-alpha surface filled
        # with translucent black (same kind of blit as the HUD boxes).
        self.fader = _finish_rgba(_new_rgba((WIN_W, WIN_H)))  # filled with RGBA each frame
        self.complete_fades = _shadowed_text_fades(load_font(COMPLETE_SIZE, bold=True), COMPLETE_TEXT, 16)
        self.archie_fades = {}    # (sprite key, level) -> faded copy, for walking into the TARDIS
        self.hum_gain = 1.0
        self.card_t0 = None       # level card running (survives reset)
        self.card_switched = False
        self.hum_assign = [None] * HUM_CHANNELS
        self.hum_ch_gain = [0.0] * HUM_CHANNELS
        self.hum_releasing = [False] * HUM_CHANNELS
        self.reset(seed if seed is not None else (time.time_ns() & 0x7FFFFFFF))

    def reset(self, seed: int, banner: bool = True):
        """A new maze for self.level (level 1 after a death, or the next level)."""
        self.sfx.stop_all()
        self.hum_assign = [None] * HUM_CHANNELS
        self.hum_ch_gain = [0.0] * HUM_CHANNELS
        self.hum_releasing = [False] * HUM_CHANNELS
        self.num_daleks = daleks_for_level(self.level)
        self.banner = banner      # show the "Level N" banner as it starts
        self.exit_t0 = None       # Archie heading into the exit TARDIS
        self.exit_from = None
        self.exit_facing = DIR_SE
        self.exit_steps = 0
        self.exit_demat_t0 = None
        self.bump_times = []
        self.last_bump_t = -1e9
        self.rustle_t = -1e9
        self.ow_quiet_until = -1e9
        self.voice_until = -1e9
        self.hops_heard = 0
        self.seed = seed & 0x7FFFFFFF
        self.grid = generate_maze(MAZE_SIZE, self.seed)
        self.hedge_variant = hedge_variant_grid(self.grid, self.seed)
        # The TARDIS that brought him stands on (1, 1); Archie starts one cell
        # forward along the open path, facing on into the maze, away from it.
        self.demat_cell = (1, 1)
        start_dir = next(d for d in DIR_ORDER if self.is_open(1 + d[0], 1 + d[1]))
        self.start_cell = (1 + start_dir[0], 1 + start_dir[1])
        self.col, self.row = self.start_cell
        self.src = self.dst = self.start_cell
        self.facing_index = DIR_ORDER.index(start_dir)
        self.facing = start_dir
        self.turn_from = start_dir
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
        self.dead_pos = (float(self.col), float(self.row))
        self.shooter = None
        self.disguised = False
        self.disguise_t0 = -1e9
        self.disguise_end_t = -1e9
        self.cooldown_until = 0.0
        self.disguise_pending = False
        self.exit_cell = (MAZE_SIZE - 2, MAZE_SIZE - 2)
        self.start_t0 = None  # game time of the first update
        self.demat_t0 = None  # when the dematerialisation (and its sound) starts
        if self.sfx.demat_source != "tardis_demat.wav":
            real = self.sfx.length_ms("tardis_demat", DEMAT_MS)
            self.demat_len = max(DEMAT_MIN_MS, min(DEMAT_MAX_MS, real))
        else:
            self.demat_len = DEMAT_MS
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
        from_start = self._path_dist(self.start_cell)
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
                and cell not in (self.start_cell, self.demat_cell)
            )
            if len(cands) >= self.num_daleks:
                break
        chosen = []
        for _ in range(self.num_daleks):
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
            if (not self.is_open(*n) or n == self.exit_cell or n in others
                    or (n == self.demat_cell and self.start_tardis_up(now))):
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
        if name == "tardis_exit":
            # Archie next to the exit, stepping into the TARDIS. --scene-ms
            # counts from that step: he walks in (0.5 s), demat from 0.9 s, then the card.
            ec, er = self.exit_cell
            for dirn in DIR_ORDER:
                c, r = ec - dirn[0], er - dirn[1]
                if self.is_open(c, r):
                    self._place_archie((c, r), dirn)
                    break
            self._park_other_daleks(None)
            self.start_t0 = now - DEMAT_WAIT_MS - self.demat_len - 1000  # start TARDIS long gone
            self.demat_t0 = self.start_t0 + DEMAT_WAIT_MS
            self.banner = False
            self._start_step(1, now)
            return 300.0
        if name == "tardis_demat":
            # The start of a level: the TARDIS on (1, 1), Archie one cell in front of it.
            self._park_other_daleks(None)
            self.start_t0 = now
            self.demat_t0 = None
            return DEMAT_WAIT_MS + 1500.0  # --scene-ms counts from the start of the game
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
        if (not self.is_open(nc, nr) or (nc, nr) in self._dalek_cells()
                or ((nc, nr) == self.demat_cell and self.start_tardis_up(now))):
            if self.bump_dir != (dc, dr):
                self.bump_dir = (dc, dr)
                self.bump_t0 = now
                if not self.is_open(nc, nr):  # a hedge, not a Dalek's cell
                    self._hedge_bump(now)
            return False
        self.bump_dir = None
        self.queued = None
        if (nc, nr) == self.exit_cell:
            self._begin_exit(now)
            return True
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
        if key == MUTE_KEY:
            self.sfx.toggle_mute()
            return
        if self.card_t0 is not None:
            return  # the level card is showing
        if key in RESTART_KEYS and self.dead and now - self.death_t0 >= LASER_MS:
            self.level = 1  # start again from level 1 in a new maze
            self.reset(time.time_ns() & 0x7FFFFFFF)
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
        if self.busy() or self.won or self.dead or self.disguised or self.card_t0 is not None:
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
        if self.card_t0 is not None:
            t = now - self.card_t0
            if not self.card_switched and t >= CARD_FADE_MS:
                self._next_level()
            if t < 2 * CARD_FADE_MS + CARD_HOLD_MS:
                self._update_hum(now, dt)
                return  # everything waits until the card has faded
            self.card_t0 = None
            self.last_now = now
        if self.won:
            self._update_exit(now)
            self._update_hum(now, dt)
            return  # Daleks freeze while Archie leaves
        if self.start_t0 is None:
            self.start_t0 = now
        if self.demat_t0 is None and now - self.start_t0 >= DEMAT_WAIT_MS:
            self.demat_t0 = self.start_t0 + DEMAT_WAIT_MS
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

    # ----- Reaching the TARDIS --------------------------------------------
    def _begin_exit(self, now: float):
        """Input locks and the Daleks freeze; Archie walks on into the TARDIS."""
        if self.won or self.dead:
            return
        self.won = True
        self.exit_t0 = now
        self.exit_from = (self.col, self.row)
        self.exit_facing = self.facing
        self.exit_steps = 0
        self.moving = self.turning = False
        self.queued = None
        self.wish = None
        self.bump_dir = None
        self.disguise_pending = False

    def _update_exit(self, now: float):
        if self.exit_t0 is None:
            return
        t = now - self.exit_t0
        # Two soft footsteps as he walks in.
        if self.exit_steps < 2 and t >= EXIT_WALK_MS * (0.25 + 0.4 * self.exit_steps):
            self.exit_steps += 1
            self.sfx.step()
        if self.exit_demat_t0 is None and t >= EXIT_DEMAT_AT:
            self.exit_demat_t0 = self.exit_t0 + EXIT_DEMAT_AT
            self.sfx.play("tardis_demat")
        if (self.exit_demat_t0 is not None and self.card_t0 is None
                and now - self.exit_demat_t0 >= self.demat_len + EXIT_CARD_GAP_MS):
            self.card_t0 = now
            self.card_switched = False

    def _next_level(self):
        """Under the black card: the next level gets a brand-new maze."""
        self.card_switched = True
        self.level += 1
        self.reset(time.time_ns() & 0x7FFFFFFF, banner=False)

    def start_tardis_up(self, now: float) -> bool:
        """The TARDIS that brought Archie still stands on its cell (solid for
        5 s, then dematerialising); nobody walks into it meanwhile."""
        return self.demat_t0 is None or now - self.demat_t0 < self.demat_len

    def exit_walk_u(self, now: float) -> float:
        """0..1 along Archie's walk from his corridor into the exit TARDIS."""
        if self.exit_t0 is None:
            return 0.0
        return max(0.0, min(1.0, (now - self.exit_t0) / EXIT_WALK_MS))

    def exit_fade(self, now: float) -> float:
        """Archie's opacity as he walks into the TARDIS (1 = solid)."""
        u = self.exit_walk_u(now)
        return max(0.0, min(1.0, 1.0 - (u - EXIT_FADE_FROM) / (EXIT_FADE_TO - EXIT_FADE_FROM)))

    # ----- Dalek proximity hum -------------------------------------------
    def _hum_distance(self, d: Dalek, archie_pos) -> float:
        """Distance in cells from Archie to Dalek d for its hum: the straight
        line (hedges do not muffle it), optionally blended with the path
        distance through the maze when HUM_PATH_WEIGHT > 0."""
        straight = math.hypot(d.pos[0] - archie_pos[0], d.pos[1] - archie_pos[1])
        if HUM_PATH_WEIGHT <= 0.0:
            return straight
        here = (self.col, self.row)
        if self._hum_from != here:
            self._hum_from = here
            self._hum_dist = self._path_dist(here)
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
        active = not (self.dead or self.won or self.sfx.muted or self.card_t0 is not None)
        k = 1.0 - math.exp(-dt / HUM_DIST_SMOOTH_MS) if dt > 0 else 1.0
        archie_pos = self.visual_pos(now)
        ax, ay = tile_origin(*archie_pos)
        for i, d in enumerate(self.daleks):
            dist = self._hum_distance(d, archie_pos)
            d.hum_dist = dist
            u = max(0.0, min(1.0, (HUM_FAR - dist) / (HUM_FAR - HUM_NEAR)))
            d.near += (u ** HUM_CURVE - d.near) * k
            if not active:
                fade_ms = HUM_EXIT_FADE_MS if self.won else HUM_FADE_OUT_MS
                d.glide = 0.0 if self.sfx.muted else max(0.0, d.glide - dt / fade_ms)
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
            d.hum_lr = (vol * (1.0 - max(0.0, pan)), vol * (1.0 + min(0.0, pan)))
            d.hum_vol = vol
        # HUM_CHANNELS reserved channels carry the loudest audible Daleks. When
        # a louder Dalek (by HUM_SWAP_MARGIN) is left out, the quietest channel
        # fades out over HUM_SWAP_MS and the newcomer fades in on it, so the
        # volume never jumps.
        assign, gains, releasing = self.hum_assign, self.hum_ch_gain, self.hum_releasing
        step = dt / HUM_SWAP_MS if dt > 0 else 1.0
        for ci, d in enumerate(assign):
            if d is not None and (d not in self.daleks or d.hum_vol <= 0.0):
                assign[ci], gains[ci], releasing[ci] = None, 0.0, False  # silent already
        audible = sorted((d for d in self.daleks if d.hum_vol > 0.0), key=lambda d: -d.hum_vol)
        want = audible[:HUM_CHANNELS]
        waiting = [d for d in want if d not in assign]
        for ci, d in enumerate(assign):
            if d is None:
                continue
            if d in want:
                releasing[ci] = False
            elif waiting and waiting[0].hum_vol > d.hum_vol * HUM_SWAP_MARGIN and not any(releasing):
                releasing[ci] = True  # one hand-over at a time
        for ci, d in enumerate(assign):
            if d is None:
                continue
            if releasing[ci]:
                gains[ci] = max(0.0, gains[ci] - step)
                if gains[ci] <= 0.0:
                    assign[ci], releasing[ci] = None, False
            else:
                gains[ci] = min(1.0, gains[ci] + step)
        for d in waiting:
            if d in assign:
                continue
            free = [ci for ci, x in enumerate(assign) if x is None]
            if not free:
                break
            assign[free[0]], gains[free[0]], releasing[free[0]] = d, 0.0, False
        # Several Daleks at once: scale them all down so the sum stays sensible.
        total = sum(d.hum_vol * gains[ci] for ci, d in enumerate(assign) if d is not None)
        target = min(1.0, HUM_SUM_MAX / total) if total > 0.0 else 1.0
        kg = 1.0 - math.exp(-dt / HUM_GAIN_SMOOTH_MS) if dt > 0 else 1.0
        self.hum_gain += (target - self.hum_gain) * kg
        if total * self.hum_gain > HUM_SUM_MAX * 1.15:  # never far over, even mid-smoothing
            self.hum_gain = HUM_SUM_MAX * 1.15 / total
        nearby = active and any(d.hum_dist < HUM_STOP_DIST for d in self.daleks)
        for ci in range(HUM_CHANNELS):
            d = assign[ci]
            left, right = d.hum_lr if d is not None else (0.0, 0.0)
            g = gains[ci] * self.hum_gain
            self.sfx.set_hum(ci, left * g, right * g, nearby)

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
            if self.grid[self.row][self.col] == EXIT:  # (normally caught as the step starts)
                self._begin_exit(now)
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
        if self.exit_t0 is not None:
            u = self.exit_walk_u(now)
            u = u * u * (3.0 - 2.0 * u) * 0.35 + u * 0.65  # steady walk, soft start and stop
            sc, sr = self.exit_from
            ec, er = self.exit_cell
            return sc + (ec - sc) * u, sr + (er - sr) * u
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

    def draw(self, window: pygame.Surface, now: float):
        """Everything is drawn into self.frame, an opaque back buffer made
        like the world surface, and copied to the window in one opaque blit.

        Nothing with per-pixel alpha is ever blitted straight onto the window
        surface: on some systems that surface has an alpha channel which ends
        up 0, and pygame then copies source pixels verbatim instead of
        blending them (transparent parts of glows, text and the laser showed
        as black or coloured boxes)."""
        if self.frame is None or self.frame.get_size() != window.get_size():
            self.frame = pygame.Surface(window.get_size()).convert()
        screen = self.frame
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
        self._draw_level_hud(screen)
        if self.dead and now - self.death_t0 >= DEATH_MSG_MS:
            self._draw_panel(screen, "EXTERMINATED!", f"You reached level {self.level}.  Press Enter to start again", (255, 96, 72))
        self._draw_banners(screen, now)
        self._draw_card(screen, now)
        window.blit(screen, (0, 0))

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
        elif self.exit_t0 is not None:
            t = self.exit_walk_u(now)
            local = (t * 2.0) % 1.0 if t < 1.0 else 0.0
            feet_sy -= int(round(math.sin(local * math.pi) * 2))
        self.archie_feet = (feet_sx, feet_sy)
        # One pass, back to front. Archie, the Daleks and the TARDIS slot in
        # by depth (row + col) when the tiles in front of them start.
        char_depth = vrow + vcol
        entities = []
        # Walking into the exit TARDIS he keeps his normal depth: the box (same
        # depth, drawn after him) and the hedges in front hide him as he goes in.
        entities.append((char_depth, 1, lambda: self._draw_archie(screen, feet_sx, feet_sy, now)))
        for d in self.daleks:
            entities.append((d.pos[0] + d.pos[1], 0, lambda d=d: self._draw_dalek(screen, d, now, cam_x, cam_y)))
        ec, er = self.exit_cell
        entities.append((float(ec + er), 2, lambda: self._draw_tardis(screen, cam_x, cam_y, now)))
        if self.demat_t0 is None or now - self.demat_t0 < self.demat_len:
            dc, dr = self.demat_cell
            # On its own cell, (1, 1), one behind Archie's start cell.
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

    def _draw_tardis(self, screen, cam_x: float, cam_y: float, now: float):
        """The exit TARDIS on the exit cell, anchored by the centre of its base.
        When Archie has walked into it, it dematerialises."""
        ec, er = self.exit_cell
        fx, fy = tile_origin(ec, er)
        fx -= cam_x
        fy += TILE_H // 2 - cam_y
        img = self.tardis
        if fx < -img.get_width() or fx > self.view_w + img.get_width() or fy < -40 or fy > self.view_h + img.get_height():
            return
        if self.exit_demat_t0 is not None:
            alpha, lamp = self._demat_curve(now - self.exit_demat_t0)
        else:
            alpha, lamp = 1.0, 0.0
        self._blit_tardis(screen, fx, fy, alpha, lamp)

    def _blit_tardis(self, screen, fx: float, fy: float, alpha: float, lamp: float):
        """A TARDIS with its base centre at (fx, fy): pre-faded copies (no
        set_alpha on per-pixel-alpha surfaces) and a roof-lamp glow."""
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
            screen.blit(g, (int(lx - g.get_width() / 2), int(ly - g.get_height() / 2)))

    def demat_alpha(self, now: float):
        """(TARDIS opacity, lamp brightness), both 0..1.

        For the first 5 s the TARDIS stands solid with its lamp glowing gently.
        Then the dematerialisation: classic fade pulsing (solid, faint, solid
        again, about once a second with our sound) inside an overall fade that
        reaches nothing DEMAT_END_GAP_MS before the sound ends. A longer
        user-supplied sound stretches the fade and slows the pulses to match.
        The roof lamp flashes while it goes.
        """
        if self.demat_t0 is None or now < self.demat_t0:
            since = 0.0 if self.start_t0 is None else now - self.start_t0
            return 1.0, 0.45 + 0.15 * math.sin(2 * math.pi * since / 2000.0)
        return self._demat_curve(now - self.demat_t0)

    def _demat_curve(self, t: float):
        """(opacity, lamp) t ms into a dematerialisation; used at both ends."""
        if t < 0:
            return 1.0, 0.0
        if t >= self.demat_len:
            return 0.0, 0.0
        fade_end = self.demat_len - DEMAT_END_GAP_MS
        period = DEMAT_PULSE_MS * math.sqrt(max(1.0, self.demat_len / DEMAT_MS))
        u = min(1.0, t / fade_end)
        overall = 1.0 - u * u * (3.0 - 2.0 * u)
        pulse = 0.12 + 0.88 * (0.5 + 0.5 * math.cos(2 * math.pi * t / period)) ** 1.5
        alpha = overall * pulse
        flash = (0.5 + 0.5 * math.cos(2 * math.pi * t / (period / 2))) ** 2
        lamp = flash * min(1.0, 0.25 + 1.2 * overall) * (1.0 if t < fade_end else 0.0)
        return alpha, lamp

    def _draw_demat(self, screen, now: float, cam_x: float, cam_y: float):
        alpha, lamp = self.demat_alpha(now)
        if alpha <= 0.0 and lamp <= 0.0:
            return
        dc, dr = self.demat_cell
        fx, fy = tile_origin(dc, dr)
        fx -= cam_x
        fy += TILE_H // 2 - cam_y
        img_w, img_h = self.tardis.get_size()
        if fx < -img_w or fx > self.view_w + img_w or fy < -40 or fy > self.view_h + img_h:
            return
        self._blit_tardis(screen, fx, fy, alpha, lamp)

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
            cached = _finish_rgba(pygame.transform.smoothscale(base, (w, h)))
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
        if self.exit_t0 is not None:
            level = int(round(self.exit_fade(now) * 16))
            if level <= 0:
                return
            if level < 16:
                faded = self.archie_fades.get((key, level))
                if faded is None:
                    faded = (_alpha_scaled(self.shadow, level / 16), _alpha_scaled(sprite, level / 16))
                    self.archie_fades[(key, level)] = faded
                screen.blit(faded[0], (feet_sx - self.shadow.get_width() // 2, feet_sy - 6))
                screen.blit(faded[1], pos)
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
                self._solid_glow(screen, ex, ey, (3.0 + 6.0 * u) * flick, EYE_GLOW)
            if d.state == "aim" or (d.state == "fire" and now - d.fire_t0 < LASER_MS + 400):
                self._draw_shout(screen, d, now)
        if self.dead and self.shooter is not None:
            t = now - self.death_t0
            if t < LASER_MS:
                gx, gy = self._to_window(*self._dalek_point(self.shooter, now, self.dalek_gun))
                fx, fy = self.archie_feet
                tx, ty = self._to_window(fx, fy - 34)
                self._draw_laser(screen, (gx, gy), (tx, ty), now, t)

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

    def _solid_glow(self, screen, x: float, y: float, radius: float, colours):
        """A glow impression from solid concentric circles (no alpha)."""
        c = (int(round(x)), int(round(y)))
        for k, colour in zip((1.0, 0.72, 0.45), colours):
            r = int(round(radius * k))
            if r >= 1:
                pygame.draw.circle(screen, colour, c, r)

    def _draw_laser(self, screen, start, end, now: float, t: float):
        """Solid opaque lines straight onto the frame, wide dark blue to a thin
        white core, flickering in width and colour; solid circles at the gun
        tip and the hit point. No intermediate surface, no alpha."""
        rng = random.Random(int(now // 33))
        fade = 1.0 if t < LASER_MS * 0.6 else max(0.0, 1.0 - (t - LASER_MS * 0.6) / (LASER_MS * 0.4))
        if fade <= 0.05:
            return
        a = (int(round(start[0])), int(round(start[1])))
        b = (int(round(end[0])), int(round(end[1])))
        j = rng.uniform(0.75, 1.25)
        hot = rng.random() < 0.5  # flicker between two palettes
        for width, colour in zip(LASER_WIDTHS, LASER_HOT if hot else LASER_COLOURS):
            w = int(round(width * j * fade))
            if w >= 1:
                pygame.draw.line(screen, colour, a, b, w)
        self._solid_glow(screen, a[0], a[1], 6.0 * j * fade, LASER_TIP_GLOW)
        self._solid_glow(screen, b[0], b[1], 8.0 * rng.uniform(0.8, 1.15) * fade, LASER_HIT_GLOW)

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
        box = _new_rgba((bw + pad_x * 2, text.get_height() + pad_y * 2 + 10))
        box.fill((36, 24, 16, 190))
        pygame.draw.rect(box, (186, 160, 96, 200), box.get_rect(), 1)
        box.blit(text, (pad_x, pad_y))
        by = pad_y + text.get_height() + 4
        pygame.draw.rect(box, (20, 14, 10, 230), (pad_x, by, bw, 6))
        pygame.draw.rect(box, bar, (pad_x, by, int(bw * max(0.0, min(1.0, frac))), 6))
        box = _finish_rgba(box)
        screen.blit(box, (WIN_W - box.get_width() - 14, WIN_H - box.get_height() - 14))

    def _draw_minimap(self, screen):
        scale = 3
        pad = 6
        size = MAZE_SIZE * scale
        box = _new_rgba((size + pad * 2, size + pad * 2))
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
        box = _finish_rgba(box)
        screen.blit(box, (x, 14))

    def _draw_hint(self, screen):
        mute = "M to unmute" if self.sfx.muted else "M to mute"
        text = self.font_hint.render(
            f"Left and right to turn. Up to step forward. H to hide as a hedge. {mute}", True, (240, 234, 214)
        )
        pad_x, pad_y = 12, 8
        box = _new_rgba((text.get_width() + pad_x * 2, text.get_height() + pad_y * 2))
        box.fill((36, 24, 16, 180))
        pygame.draw.rect(box, (186, 160, 96, 200), box.get_rect(), 1)
        x, y = 14, WIN_H - box.get_height() - 14
        box = _finish_rgba(box)
        screen.blit(box, (x, y))
        screen.blit(text, (x + pad_x, y + pad_y))

    def _draw_level_hud(self, screen):
        text = self.font_hud.render(f"Level {self.level}    Daleks: {len(self.daleks)}", True, (240, 234, 214))
        pad_x, pad_y = 12, 7
        box = _new_rgba((text.get_width() + pad_x * 2, text.get_height() + pad_y * 2))
        box.fill((36, 24, 16, 180))
        pygame.draw.rect(box, (186, 160, 96, 200), box.get_rect(), 1)
        box = _finish_rgba(box)
        screen.blit(box, (14, 14))
        screen.blit(text, (14 + pad_x, 14 + pad_y))

    def _banner(self, screen, text: str, colour, fade: float, y: int):
        if fade <= 0.02:
            return
        surf = self.font_big.render(text, True, colour)
        shadow = self.font_big.render(text, True, (20, 12, 6))
        x = (WIN_W - surf.get_width()) // 2
        screen.blit(_alpha_scaled(shadow, fade * 0.8), (x + 2, y + 2))
        screen.blit(_alpha_scaled(surf, fade), (x, y))

    def _draw_banners(self, screen, now: float):
        # "Level N" as a level starts (the card already said it after a level change).
        if self.banner and self.start_t0 is not None and not self.won and not self.dead:
            t = now - self.start_t0
            if t < LEVEL_BANNER_MS:
                fade = min(1.0, t / 300.0, (LEVEL_BANNER_MS - t) / 600.0)
                self._banner(screen, f"Level {self.level}", (255, 236, 170), fade, 90)
        # "Level complete!" while the TARDIS dematerialises with Archie inside.
        if self.exit_demat_t0 is not None and self.card_t0 is None:
            t = now - self.exit_demat_t0
            fade = max(0.0, min(1.0, t / COMPLETE_FADE_IN_MS,
                                (self.demat_len + EXIT_CARD_GAP_MS - t) / COMPLETE_FADE_OUT_MS))
            level = int(round(fade * (len(self.complete_fades) - 1)))
            if level > 0:
                img = self.complete_fades[level]
                screen.blit(img, ((WIN_W - img.get_width()) // 2, int(WIN_H * COMPLETE_Y)))

    def _draw_card(self, screen, now: float):
        """Fade to black, "Level N", fade into the new maze."""
        if self.card_t0 is None:
            return
        t = now - self.card_t0
        if t < CARD_FADE_MS:
            a = t / CARD_FADE_MS
        elif t < CARD_FADE_MS + CARD_HOLD_MS:
            a = 1.0
        else:
            a = max(0.0, 1.0 - (t - CARD_FADE_MS - CARD_HOLD_MS) / CARD_FADE_MS)
        self.fader.fill((0, 0, 0, int(255 * a)))
        screen.blit(self.fader, (0, 0))
        if self.card_switched:
            level = self.level
            text_fade = min(1.0, (t - CARD_FADE_MS) / 250.0) if t < CARD_FADE_MS + CARD_HOLD_MS else a
        else:
            level = self.level + 1
            text_fade = a
        self._banner(screen, f"Level {level}", (255, 236, 170), text_fade, WIN_H // 2 - 40)
        sub = self.font_small.render(f"{daleks_for_level(level)} Daleks", True, (232, 214, 170))
        if text_fade > 0.02:
            screen.blit(_alpha_scaled(sub, text_fade), ((WIN_W - sub.get_width()) // 2, WIN_H // 2 + 10))

    def _draw_panel(self, screen, title_text: str, sub_text: str, title_colour):
        title = self.font_big.render(title_text, True, title_colour)
        sub = self.font_small.render(sub_text, True, (232, 214, 170))
        gap = 10
        width = max(title.get_width(), sub.get_width()) + 56
        height = title.get_height() + sub.get_height() + gap + 36
        panel = _new_rgba((width, height))
        panel.fill((36, 24, 16, 255))
        pygame.draw.rect(panel, (212, 170, 90), panel.get_rect(), 2)
        panel.blit(title, ((width - title.get_width()) // 2, 16))
        panel.blit(sub, ((width - sub.get_width()) // 2, 16 + title.get_height() + gap))
        panel = _finish_rgba(panel)
        screen.blit(panel, ((WIN_W - width) // 2, (WIN_H - height) // 2))


def parse_args(argv):
    parser = argparse.ArgumentParser(description="Archie's isometric hedge maze")
    parser.add_argument("--seed", type=int, default=None, help="maze seed (default: time)")
    parser.add_argument("--screenshot", type=str, default=None, help="save a frame to this path and quit")
    parser.add_argument("--frames", type=int, default=None, help="after the first frame, simulate N movement frames")
    parser.add_argument("--level", type=int, default=1, help="start on this level (3 + 2 per level Daleks)")
    parser.add_argument("--scene", choices=("dalek", "laser", "telegraph", "disguise", "tardis", "tardis_demat", "tardis_exit"), default=None,
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
    game = Game(args.seed, args.level)
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
