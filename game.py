#!/usr/bin/env python3
"""Archie's hedge maze — a small isometric maze in pygame.

Play:  python3 game.py
Test:  SDL_VIDEODRIVER=dummy python3 game.py --seed 1 --screenshot preview.png --frames 8
"""

from __future__ import annotations

import argparse
import math
import os
import sys
import time

# No audio device is required, and a missing one should not abort headless runs.
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

# Classic 2:1 isometric projection. (tx, ty) is the top vertex of a tile.
#   screen_x = (col - row) * (TILE_W // 2)
#   screen_y = (col + row) * (TILE_H // 2)
TILE_W = 64
TILE_H = 32
HEDGE_H = 40
SPRITE_H = 74
MOVE_MS = 150
BUMP_MS = 110
WIN_W = 1100
WIN_H = 720
MAZE_SIZE = 41  # odd, so a perfect maze has a solid border
WALL, GRASS, EXIT = 0, 1, 2

# +col screen down-right, +row screen down-left, -col up-left, -row up-right.
DIR_SE = (1, 0)
DIR_SW = (0, 1)
DIR_NW = (-1, 0)
DIR_NE = (0, -1)
DIR_ORDER = (DIR_SE, DIR_SW, DIR_NW, DIR_NE)

GRASS_COLOURS = (
    (124, 190, 82),
    (112, 178, 74),
    (134, 198, 90),
    (104, 168, 68),
    (118, 184, 78),
    (140, 204, 96),
)
# Floors are drawn before the blocks so the whole maze stays readable from
# above. Hedges in front of Archie are then painted over just his shoes, so
# he tucks into the near wall without the hedge swallowing him.
OCCLUDE_BIAS = 0.35
SHOE_OCCLUDE = 18

HERE = os.path.dirname(os.path.abspath(__file__))
SPRITE_FILES = {
    DIR_SE: os.path.join(HERE, "assets", "archie_se.png"),
    DIR_SW: os.path.join(HERE, "assets", "archie_sw.png"),
    DIR_NW: os.path.join(HERE, "assets", "archie_nw.png"),
    DIR_NE: os.path.join(HERE, "assets", "archie_ne.png"),
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


def diamond_points(tx: int, ty: int):
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

    grid[1][1] = GRASS
    stack = [(1, 1)]
    while stack:
        col, row = stack[-1]
        carved = False
        for dc, dr in shuffled_dirs():
            nc, nr = col + dc, row + dr
            if 1 <= nc < size - 1 and 1 <= nr < size - 1 and grid[nr][nc] == WALL:
                grid[row + dr // 2][col + dc // 2] = GRASS
                grid[nr][nc] = GRASS
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


class Game:
    def __init__(self, seed: int | None):
        self.sprites = {}
        self.anchors = {}
        for direction, path in SPRITE_FILES.items():
            image = pygame.image.load(path).convert_alpha()
            h = image.get_height()
            if h != SPRITE_H:
                w = max(1, round(image.get_width() * SPRITE_H / h))
                image = pygame.transform.smoothscale(image, (w, SPRITE_H))
            self.sprites[direction] = image
            rect = image.get_bounding_rect(min_alpha=16)
            # Feet (bottom of the opaque sprite) sit on the tile centre.
            self.anchors[direction] = (rect.centerx, rect.bottom)
        self.shadow = pygame.Surface((40, 16), pygame.SRCALPHA)
        pygame.draw.ellipse(self.shadow, (20, 36, 18, 90), self.shadow.get_rect())
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
        self.facing = DIR_SE
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

    def try_move(self, dc: int, dr: int, now: float) -> bool:
        if self.won:
            return False
        if self.moving:
            self.queued = (dc, dr)
            return False
        self.facing = (dc, dr)
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

    def desired_direction(self, keys) -> tuple[int, int] | None:
        key_for = {
            DIR_SE: (pygame.K_RIGHT, pygame.K_d),
            DIR_NW: (pygame.K_LEFT, pygame.K_a),
            DIR_SW: (pygame.K_DOWN, pygame.K_s),
            DIR_NE: (pygame.K_UP, pygame.K_w),
        }
        held = []
        for direction in DIR_ORDER:
            a, b = key_for[direction]
            if keys[a] or keys[b]:
                held.append(direction)
        if not held:
            return None
        open_held = [
            d for d in held if self.is_open(self.col + d[0], self.row + d[1])
        ]
        if self.wish in open_held:
            return self.wish
        if open_held:
            return open_held[0]
        if self.wish in held:
            return self.wish
        return held[0]

    def on_key(self, key: int, now: float):
        if key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_r, pygame.K_SPACE) and self.won:
            self.reset(time.time_ns() & 0x7FFFFFFF)
            return
        mapping = {
            pygame.K_RIGHT: DIR_SE,
            pygame.K_d: DIR_SE,
            pygame.K_LEFT: DIR_NW,
            pygame.K_a: DIR_NW,
            pygame.K_DOWN: DIR_SW,
            pygame.K_s: DIR_SW,
            pygame.K_UP: DIR_NE,
            pygame.K_w: DIR_NE,
        }
        direction = mapping.get(key)
        if direction is None:
            return
        self.wish = direction
        if self.moving:
            # A tap during a step is kept, instead of being thrown away.
            self.queued = direction
            return
        self.try_move(*direction, now)

    def hold_move(self, keys, now: float):
        if self.moving or self.won:
            return
        direction = self.desired_direction(keys)
        if direction is None:
            return
        self.wish = direction
        self.try_move(*direction, now)

    def nudge(self, now: float):
        """Headless test: step toward an open neighbour, if there is one."""
        if self.moving or self.won:
            return
        for dc, dr in DIR_ORDER:
            if self.is_open(self.col + dc, self.row + dr):
                self.try_move(dc, dr, now)
                return

    def update(self, now: float):
        if not self.moving:
            return
        if now - self.move_t0 >= MOVE_MS:
            self.col, self.row = self.dst
            self.moving = False
            queued = self.queued
            self.queued = None
            if self.grid[self.row][self.col] == EXIT:
                self.won = True
                return
            if queued is not None:
                self.try_move(*queued, now)

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
        screen.fill((16, 32, 20))
        vcol, vrow = self.visual_pos(now)
        feet_x, feet_y = tile_origin(vcol, vrow)
        feet_y += TILE_H // 2
        # Look a little above the feet so Archie's body, not just his shoes, is centred.
        cam_x = feet_x - WIN_W / 2
        cam_y = (feet_y - 46) - WIN_H / 2
        tiles = self._visible_tiles(cam_x, cam_y)

        feet_sx = int(round(feet_x - cam_x))
        feet_sy = int(round(feet_y - cam_y))
        if self.moving:
            t = (now - self.move_t0) / MOVE_MS
            feet_sy -= int(round(math.sin(max(0.0, min(1.0, t)) * math.pi) * 3))
        # One pass, back to front: a hedge is the tile, not a second maze
        # painted over the paths. Archie slots in when the tiles in front of him start.
        char_depth = vrow + vcol
        drew = False
        for depth, col, row, tx, ty in tiles:
            if not drew and depth > char_depth + 0.05:
                self._draw_archie(screen, feet_sx, feet_sy)
                drew = True
            cell = self.grid[row][col]
            if cell == WALL:
                self._draw_hedge(screen, col, row, tx, ty)
            elif cell == EXIT:
                self._draw_exit(screen, tx, ty)
            else:
                self._draw_grass(screen, col, row, tx, ty)
        if not drew:
            self._draw_archie(screen, feet_sx, feet_sy)
        self._draw_minimap(screen)
        self._draw_hint(screen)
        if self.won:
            self._draw_win(screen)

    def _fog(self, colour, sy: int):
        # Slight aerial perspective: tiles higher on the screen are a touch darker.
        k = 0.88 + 0.14 * max(0.0, min(1.0, sy / WIN_H))
        return mix(colour, k)

    def _draw_tile(self, screen, col: int, row: int, tx: int, ty: int):
        cell = self.grid[row][col]
        if cell == WALL:
            self._draw_hedge(screen, col, row, tx, ty)
        elif cell == EXIT:
            self._draw_exit(screen, tx, ty)
        else:
            self._draw_grass(screen, col, row, tx, ty)

    def _draw_grass(self, screen, col: int, row: int, tx: int, ty: int):
        idx = (col * 5 + row * 3 + (col ^ row)) % len(GRASS_COLOURS)
        colour = self._fog(GRASS_COLOURS[idx], ty)
        pts = diamond_points(tx, ty)
        pygame.draw.polygon(screen, colour, pts)
        edge = self._fog((70, 120, 56), ty)
        pygame.draw.polygon(screen, edge, pts, 1)
        # A few short blades, stable per cell.
        cx, cy = tx, ty + TILE_H // 2
        h = (col * 131 + row * 719) & 0xFFFF
        blade = self._fog((62, 118, 48), ty)
        for _ in range(2):
            h = (h * 1103515245 + 12345) & 0xFFFF
            ox = (h % 21) - 10
            h = (h * 1103515245 + 12345) & 0xFFFF
            oy = (h % 11) - 5
            if abs(ox) / 32 + abs(oy) / 16 > 0.7:
                continue
            pygame.draw.line(screen, blade, (cx + ox, cy + oy), (cx + ox, cy + oy - 3), 1)

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
        # Front-left face, front-right face, then the leafy top.
        left_face = (ground[3], ground[2], raised[2], raised[3])
        right_face = (ground[1], ground[2], raised[2], raised[1])
        pygame.draw.polygon(screen, left, left_face)
        pygame.draw.polygon(screen, right, right_face)
        pygame.draw.polygon(screen, top, raised)
        # Lighter cushion on the top so the hedge reads as foliage, not a slab.
        cx, cy = tx, ty - HEDGE_H + TILE_H // 2
        inset = (
            (cx, cy - int(hh * 0.62)),
            (cx + int(hw * 0.62), cy),
            (cx, cy + int(hh * 0.62)),
            (cx - int(hw * 0.62), cy),
        )
        cushion = self._fog((56 + shift, 122 + shift, 50), ty)
        pygame.draw.polygon(screen, cushion, inset)
        # Stable leaf flecks on the crown.
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
        # A small warm gate so the way out reads at a glance.
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

    def _draw_archie(self, screen, feet_sx: int, feet_sy: int):
        sprite = self.sprites[self.facing]
        ax, ay = self.anchors[self.facing]
        screen.blit(self.shadow, (feet_sx - self.shadow.get_width() // 2, feet_sy - 6))
        screen.blit(sprite, (feet_sx - ax, feet_sy - ay))

    def _draw_minimap(self, screen):
        scale = 3
        pad = 6
        size = MAZE_SIZE * scale
        box = pygame.Surface((size + pad * 2, size + pad * 2), pygame.SRCALPHA)
        box.fill((12, 22, 14, 190))
        pygame.draw.rect(box, (186, 160, 96, 200), box.get_rect(), 1)
        for row in range(MAZE_SIZE):
            for col in range(MAZE_SIZE):
                cell = self.grid[row][col]
                if cell == WALL:
                    colour = (28, 72, 36)
                elif cell == EXIT:
                    colour = (232, 196, 96)
                else:
                    colour = (118, 186, 84)
                box.fill(colour, (pad + col * scale, pad + row * scale, scale, scale))
        px = pad + int(self.col * scale)
        py = pad + int(self.row * scale)
        pygame.draw.rect(box, (255, 248, 230), (px, py, scale, scale))
        x = WIN_W - box.get_width() - 14
        screen.blit(box, (x, 14))

    def _draw_hint(self, screen):
        text = self.font_hint.render("Arrow keys or WASD to walk", True, (240, 234, 214))
        pad_x, pad_y = 12, 8
        box = pygame.Surface((text.get_width() + pad_x * 2, text.get_height() + pad_y * 2), pygame.SRCALPHA)
        box.fill((16, 28, 16, 180))
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
        panel.fill((22, 32, 20, 255))
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
            game.hold_move(pygame.key.get_pressed(), now)
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
