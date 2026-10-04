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
import sys
import time

# No audio device is required, and a missing one should not abort headless runs.
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
        self.given_seed = seed
        self.reset(seed if seed is not None else (time.time_ns() & 0x7FFFFFFF))

    def reset(self, seed: int):
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
        if not self.is_open(nc, nr):
            if self.bump_dir != (dc, dr):
                self.bump_dir = (dc, dr)
                self.bump_t0 = now
            return False
        self.bump_dir = None
        self.queued = None
        self.src = (self.col, self.row)
        self.dst = (nc, nr)
        self.move_t0 = now
        self.moving = True
        return True

    def try_action(self, action, now: float) -> bool:
        if self.won:
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
        if key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_r, pygame.K_SPACE) and self.won:
            self.reset(time.time_ns() & 0x7FFFFFFF)
            return
        action = KEY_ACTIONS.get(key)
        if action is None or self.won:
            return
        self.wish = action
        self.try_action(action, now)

    def hold_action(self, keys, now: float):
        if self.busy() or self.won:
            return
        action = self.desired_action(keys)
        if action is None:
            return
        self.wish = action
        self.try_action(action, now)

    def nudge(self, now: float):
        """Headless test: step forward, or turn right if that cell is shut."""
        if self.busy() or self.won:
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
        if self.turning:
            if now - self.turn_t0 >= TURN_MS:
                self.turning = False
                self._fire_queued(now)
            return
        if not self.moving:
            return
        if now - self.move_t0 >= MOVE_MS:
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
        # HUD at full window resolution, on top of the scaled world.
        self._draw_minimap(screen)
        self._draw_hint(screen)
        if self.won:
            self._draw_win(screen)

    def _draw_world(self, screen: pygame.Surface, now: float):
        screen.fill(BG_COLOUR)
        vcol, vrow = self.visual_pos(now)
        feet_x, feet_y = tile_origin(vcol, vrow)
        feet_y += TILE_H // 2
        # Feet sit near the centre; looking a little above them puts his body
        # just above centre. The maze scrolls; tiles are not yaw-rotated.
        cam_x = feet_x - self.view_w / 2
        cam_y = (feet_y - 46) - self.view_h / 2
        tiles = self._visible_tiles(cam_x, cam_y)

        feet_sx = int(round(feet_x - cam_x))
        feet_sy = int(round(feet_y - cam_y))
        if self.moving:
            t = max(0.0, min(1.0, (now - self.move_t0) / MOVE_MS))
            local = (t * 2.0) % 1.0 if t < 1.0 else 0.0
            feet_sy -= int(round(math.sin(local * math.pi) * 2))
        # One pass, back to front. Archie slots in when tiles in front start.
        char_depth = vrow + vcol
        drew = False
        for depth, col, row, tx, ty in tiles:
            if not drew and depth > char_depth + 0.05:
                self._draw_archie(screen, feet_sx, feet_sy, now)
                drew = True
            cell = self.grid[row][col]
            if cell == WALL:
                self._draw_hedge(screen, col, row, tx, ty)
            elif cell == EXIT:
                self._draw_exit(screen, tx, ty)
            else:
                self._draw_dirt(screen, col, row, tx, ty)
        if not drew:
            self._draw_archie(screen, feet_sx, feet_sy, now)

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

    def _draw_exit(self, screen, tx: int, ty: int):
        stone = self._fog((214, 198, 150), ty)
        stone_edge = self._fog((148, 112, 64), ty)
        pts = diamond_points(tx, ty)
        pygame.draw.polygon(screen, stone, pts)
        inner = (
            (tx, ty + 5),
            (tx + TILE_W // 2 - 8, ty + TILE_H // 2),
            (tx, ty + TILE_H - 5),
            (tx - TILE_W // 2 + 8, ty + TILE_H // 2),
        )
        pygame.draw.polygon(screen, self._fog((232, 214, 168), ty), inner)
        pygame.draw.polygon(screen, stone_edge, pts, 1)
        hw = TILE_W // 2
        hh = TILE_H // 2
        left = (tx - hw // 2 + 2, ty + hh + 6)
        right = (tx + hw // 2 - 2, ty + hh + 6)
        post_h = 52
        post = (122, 74, 38)
        light = (214, 168, 86)
        for x, y in (left, right):
            pygame.draw.line(screen, post, (x, y), (x, y - post_h), 5)
            pygame.draw.line(screen, light, (x - 1, y - 4), (x - 1, y - post_h + 2), 1)
        arch_top = ((left[0] + right[0]) // 2, left[1] - post_h - 16)
        pygame.draw.lines(
            screen,
            light,
            False,
            [(left[0], left[1] - post_h), arch_top, (right[0], right[1] - post_h)],
            3,
        )
        pygame.draw.line(
            screen,
            post,
            (left[0], left[1] - post_h + 2),
            (right[0], right[1] - post_h + 2),
            2,
        )

    def _draw_archie(self, screen, feet_sx: int, feet_sy: int, now: float):
        key = self.pose(now)
        sprite = self.sprites[key]
        ax, ay = self.anchors[key]
        screen.blit(self.shadow, (feet_sx - self.shadow.get_width() // 2, feet_sy - 6))
        screen.blit(sprite, (int(round(feet_sx - ax)), int(round(feet_sy - ay))))

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
                    colour = (232, 196, 96)
                else:
                    colour = (142, 98, 56)
                box.fill(colour, (pad + col * scale, pad + row * scale, scale, scale))
        px = pad + int(self.col * scale)
        py = pad + int(self.row * scale)
        pygame.draw.rect(box, (255, 248, 230), (px, py, scale, scale))
        x = WIN_W - box.get_width() - 14
        screen.blit(box, (x, 14))

    def _draw_hint(self, screen):
        text = self.font_hint.render("Left and right to turn. Up to step forward", True, (240, 234, 214))
        pad_x, pad_y = 12, 8
        box = pygame.Surface((text.get_width() + pad_x * 2, text.get_height() + pad_y * 2), pygame.SRCALPHA)
        box.fill((36, 24, 16, 180))
        pygame.draw.rect(box, (186, 160, 96, 200), box.get_rect(), 1)
        x, y = 14, WIN_H - box.get_height() - 14
        screen.blit(box, (x, y))
        screen.blit(text, (x + pad_x, y + pad_y))

    def _draw_win(self, screen):
        title = self.font_big.render("You found the way out", True, (255, 244, 214))
        sub = self.font_small.render("Press Enter to play again", True, (232, 214, 170))
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
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(sys.argv[1:] if argv is None else argv)
    pygame.init()
    pygame.display.set_caption("Archie's Hedge Maze")
    screen = pygame.display.set_mode((WIN_W, WIN_H))
    game = Game(args.seed)
    headless = args.screenshot is not None or args.frames is not None

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
    game.draw(screen, now)
    pygame.display.flip()
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
