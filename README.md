# Archie Maze

An isometric hedge maze. Archie stays in the middle of the screen and the maze stays flat. Three Daleks roam the hedges; reach the TARDIS in the far corner to escape.

## Play

```bash
pip install -r requirements.txt
python3 game.py
```

| Key | Action |
| --- | --- |
| Left / A, Right / D | Turn Archie |
| Up / W | Step forward |
| Down / S | Step back |
| H (or Shift) | Hide as a hedge for up to 4 s (press again to stop early); 3 s to recharge |
| M | Mute / unmute the sound |
| Enter, R or Space | New maze after you win or are exterminated |
| Esc | Quit |

A Dalek sees Archie only along the corridor it is facing, up to 8 cells away with no hedge in between. It shouts, its eye stalk glows, and a moment later it fires. Daleks cannot see a hedge, and they turn away if one is in their path.

```bash
python3 game.py --seed 1
```

## Sound

All sounds are small WAV files in `assets/sounds/` (22050 Hz, 16-bit mono):

| File | When it plays | How it was made |
| --- | --- | --- |
| `ow.wav` | Archie bumps into a hedge (at most about once a second while you hold the key) | espeak-ng "Ouw!" in a light voice, sped up into a boy's pitch |
| `exterminate.wav` | A Dalek spots Archie | espeak-ng, one syllable at a time (EX-TER-MIN-ATE!), then a 30 Hz ring modulator, distortion and a short metallic echo |
| `laser.wav` | The Dalek fires | Synthesised: a descending zap with buzz and crackle |
| `step1.wav`, `step2.wav`, `step3.wav` | One soft footstep per half-tile hop, varied | Synthesised: a low thump plus a little gravel crunch |

To regenerate them (needs numpy; the two voices also need `espeak-ng`, for example `sudo apt install espeak-ng`):

```bash
python3 tools/make_sounds.py
python3 tools/make_sounds.py --spectrograms /tmp   # optional spectrogram PNGs
```

If the computer has no working audio, or a sound file is missing, the game still runs, just silently.

## Testing without a screen

```bash
SDL_VIDEODRIVER=dummy python3 game.py --seed 1 --screenshot shot.png --frames 20
SDL_VIDEODRIVER=dummy python3 game.py --seed 1 --scene laser --screenshot laser.png
```

Scenes: `dalek`, `laser`, `telegraph`, `disguise`, `tardis`.
