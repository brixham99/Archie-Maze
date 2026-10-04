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
        self.font_hint = load_font(18)
        self.font_big = load_font(36, bold=True)
        self.font_small = load_font(20)
        self.given_seed = seed
        self.reset(seed if seed is not None else (time.time_ns() & 0x7FFFFFFF))

    def reset(self, seed: int):
        self.seed = seed & 0x7FFFFFFF
        self.grid = generate_maze(MAZE_SIZE, self.seed)
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

    def visual_pos(self, now: float):
        if self.moving:
            t = ease((now - self.move_t0) / MOVE_MS)
            sc, sr = self.src
            dc, dr = self.dst
            return sc + (dc - sc) * t, sr + (dr - sr) * t
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
                if sx < -margin_x or sx > WIN_W + margin_x:
                    continue
                if sy > WIN_H + margin_bottom or sy < -margin_top:
                    continue
                tiles.append((float(row + col), col, row, int(round(sx)), int(round(sy))))
        tiles.sort()
        return tiles

    def draw(self, screen: pygame.Surface, now: float):
        screen.fill(BG_COLOUR)
        vcol, vrow = self.visual_pos(now)
        feet_x, feet_y = tile_origin(vcol, vrow)
        feet_y += TILE_H // 2
        # Feet sit near the centre; looking a little above them puts his body
        # just above centre. The maze scrolls; tiles are not yaw-rotated.
        cam_x = feet_x - WIN_W / 2
        cam_y = (feet_y - 46) - WIN_H / 2
        tiles = self._visible_tiles(cam_x, cam_y)

        feet_sx = int(round(feet_x - cam_x))
        feet_sy = int(round(feet_y - cam_y))
        if self.moving:
            t = (now - self.move_t0) / MOVE_MS
            feet_sy -= int(round(math.sin(max(0.0, min(1.0, t)) * math.pi) * 3))
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
        self._draw_minimap(screen)
        self._draw_hint(screen)
        if self.won:
            self._draw_win(screen)

    def _fog(self, colour, sy: int):
        # Slight aerial perspective: tiles higher on the screen are a touch darker.
        k = 0.88 + 0.14 * max(0.0, min(1.0, sy / WIN_H))
        return mix(colour, k)

    def _draw_dirt(self, screen, col, row, tx: int, ty: int):
        """Clipped dirt diamond in tile space. Not a rotated sprite."""
        variant = (col * 5 + row * 3 + (col ^ row)) % N_DIRT
        cy = ty + TILE_H // 2
        if cy < WIN_H * 0.33:
            shade = 0
        elif cy < WIN_H * 0.66:
            shade = 1
        else:
            shade = 2
        sprite = self.dirt[variant][shade]
        screen.blit(
            sprite,
            (tx - sprite.get_width() // 2, cy - sprite.get_height() // 2),
        )

    def _draw_hedge(self, screen, col: int, row: int, tx: int, ty: int):
        shift = ((col * 13 + row * 7) % 11) - 5
        top = self._fog((40 + shift, 98 + shift, 42), ty)
        left = self._fog((16 + shift // 3, 48 + shift // 3, 22), ty)
        right = self._fog((26 + shift // 3, 70 + shift // 3, 30), ty)
        hw = TILE_W // 2
        hh = TILE_H // 2
        ground = (
            (tx, ty),
            (tx + hw, ty + hh),
            (tx, ty + TILE_H),
            (tx - hw, ty + hh),
        )
        raised = tuple((x, y - HEDGE_H) for x, y in ground)
        left_face = (ground[3], ground[2], raised[2], raised[3])
        right_face = (ground[1], ground[2], raised[2], raised[1])
        pygame.draw.polygon(screen, left, left_face)
        pygame.draw.polygon(screen, right, right_face)
        pygame.draw.polygon(screen, top, raised)
        cx, cy = tx, ty - HEDGE_H + TILE_H // 2
        inset = (
            (cx, cy - int(hh * 0.62)),
            (cx + int(hw * 0.62), cy),
            (cx, cy + int(hh * 0.62)),
            (cx - int(hw * 0.62), cy),
        )
        cushion = self._fog((56 + shift, 122 + shift, 50), ty)
        pygame.draw.polygon(screen, cushion, inset)
        h = (col * 92821 + row * 68917 + 17) & 0xFFFFFFFF
        for i in range(4):
            h = (h * 1664525 + 1013904223) & 0xFFFFFFFF
            u = ((h >> 8) % 100) / 100.0 - 0.5
            h = (h * 1664525 + 1013904223) & 0xFFFFFFFF
            v = ((h >> 8) % 100) / 100.0 - 0.5
            if abs(u) * 2 + abs(v) * 2 > 0.85:
                continue
            fleck = (96, 168, 86) if i % 2 == 0 else (40, 96, 44)
            pygame.draw.circle(
                screen,
                self._fog(fleck, ty),
                (int(cx + u * hw), int(cy + v * hh)),
                2,
            )
        outline = self._fog((16, 42, 22), ty)
        pygame.draw.polygon(screen, outline, raised, 1)
        pygame.draw.line(screen, outline, left_face[0], left_face[3], 1)
        pygame.draw.line(screen, outline, right_face[0], right_face[3], 1)

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
