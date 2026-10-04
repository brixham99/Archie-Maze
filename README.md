# Archie Maze

An isometric hedge maze. Archie stays in the middle of the screen and the maze stays flat. Daleks roam the hedges; reach the TARDIS in the far corner to escape to the next level, where there is a new maze and more Daleks.

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
| Enter, R or Space | After you are exterminated: start again from level 1 in a new maze |
| Esc | Quit |

A Dalek sees Archie only along the corridor it is facing, up to 8 cells away with no hedge in between. It shouts, its eye stalk glows, and a moment later it fires. Daleks cannot see a hedge, and they turn away if one is in their path.

You can hear a Dalek coming: it hums as it glides, faintly from about 25 cells away and louder the closer it is. Only the straight-line distance counts, so you hear Daleks behind hedges and on other paths too. The hum stops briefly while a Dalek turns or stands still. Four sound channels carry the four loudest Daleks; when several hum at once, they are all turned down a little so the total stays comfortable.

| Distance (cells, straight line) | 1 | 3 | 5 | 8 | 10 | 12 | 15 | 18 | 20 | 22 | 24 | 25+ |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Hum volume (of 1.0) | 0.50 | 0.46 | 0.42 | 0.35 | 0.31 | 0.27 | 0.21 | 0.15 | 0.10 | 0.06 | 0.02 | 0 |

## Levels

Level N has 3 + 2 × (N − 1) Daleks, up to a maximum of 15:

| Level | 1 | 2 | 3 | 4 | 5 | 6 | 7 and up |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Daleks | 3 | 5 | 7 | 9 | 11 | 13 | 15 |

The maze stays 41 × 41. Daleks start at least 12 cells (along the paths) from Archie's start and 10 from the exit TARDIS, and well apart from each other. If the maze cannot fit them all, the gap between Daleks is relaxed a step at a time.

When Archie steps onto the TARDIS, the controls lock and the Daleks freeze (their hum fades). Archie walks on from his corridor into the box and fades away inside it. The TARDIS then dematerialises with the same animation and sound as at the start, with "Level complete!" on screen. Then a short "Level N" card is shown, and the next level begins in a brand-new maze. The current level and the number of Daleks are shown in the top-left corner.

If a Dalek exterminates Archie, the message shows the level you reached. Press Enter, R or Space to start again from level 1 in a new maze.

Each level starts with the TARDIS that dropped Archie off standing on the corner cell, with Archie one cell in front of it, facing into the maze. You cannot walk back into it while it is there. After 5 seconds it dematerialises, fading in and out for as long as the TARDIS sound lasts (about 6.6 s with the supplied clip). You can start walking straight away.

```bash
python3 game.py --seed 1      # a fixed first maze
python3 game.py --level 4     # start on level 4 (9 Daleks)
```

## Sound

All sounds are small WAV files in `assets/sounds/` (22050 Hz, 16-bit mono):

| File | When it plays | How it was made |
| --- | --- | --- |
| `ow.wav` | Archie bumps into a hedge for the 3rd time within 2 seconds (held-key bumps count too), played quietly. A single bump is silent apart from the rustle | espeak-ng "Ouw!" in a light voice, sped up into a boy's pitch |
| `rustle.wav` | A very soft leafy rustle on the other hedge bumps | Synthesised: a few filtered leafy noise grains over a gentle low thud |
| `cloak_on.wav` | The hedge disguise starts (also when it kicks in after a hop lands) | Synthesised: a quick rising run of wind-chime bells (C6 to E7, pentatonic) over a fluttering shimmer, about 0.46 s |
| `cloak_off.wav` | The hedge disguise ends (time runs out or H is pressed again) | Synthesised: the same chimes as a falling run, about 0.46 s |
| `exterminate.wav` | A Dalek spots Archie | espeak-ng, one syllable at a time (EX-TER-MIN-ATE!), then a 30 Hz ring modulator, distortion and a short metallic echo |
| `laser.wav` | The Dalek fires | Synthesised: a descending zap with buzz and crackle |
| `step1.wav`, `step2.wav`, `step3.wav` | One soft footstep per half-tile hop, varied | Synthesised: a low thump plus a little gravel crunch |
| `dalek_hum.wav` | Loops for each Dalek gliding within about 25 cells (straight line), faint far off and louder up close, panned a little left or right; it fades out while the Dalek turns or stands still. Four mixer channels carry the hums of the four loudest Daleks | Synthesised 2 s seamless loop: detuned saw and square oscillators (110, 111, 165 and 220.5 Hz) through a resonant filter sweeping 400 to 2500 Hz twice per loop, a 4 Hz throb, an FM shimmer and an electronic whoosh. Pitched so laptop speakers can play it |
| `tardis_demat.wav` | The TARDIS dematerialises, 5 s into each level, and again when Archie leaves in it | A supplied recording. `tools/make_sounds.py` can also synthesise an original wheeze-groan here (three rising-and-falling grinding groans with ring-modulated metallic overtones, reverb and a soft thud), but it keeps an existing file unless you pass `--overwrite-tardis` |

To regenerate them (needs numpy; the two voices also need `espeak-ng`, for example `sudo apt install espeak-ng`):

```bash
python3 tools/make_sounds.py
python3 tools/make_sounds.py --spectrograms /tmp   # optional spectrogram PNGs (the hum is shown looped twice)
```

Drop your own TARDIS sound as `assets/sounds/tardis_real.wav` (or `.ogg`/`.mp3`) to use it; it is not included and is git-ignored. It replaces `tardis_demat.wav`, and the dematerialisation stretches to the clip's length (3 to 15 s), so the TARDIS finishes fading just before the sound ends.

If the computer has no working audio, or a sound file is missing, the game still runs, just silently.

## Testing without a screen

```bash
SDL_VIDEODRIVER=dummy python3 game.py --seed 1 --screenshot shot.png --frames 20
SDL_VIDEODRIVER=dummy python3 game.py --seed 1 --scene laser --screenshot laser.png
```

Scenes: `dalek`, `laser`, `telegraph`, `disguise`, `tardis`, `tardis_demat`, `tardis_exit`. Add `--scene-ms N` to choose how far into the scene the shot is taken, for example `--scene tardis_demat --scene-ms 6500` (the TARDIS waits 5 s, so that is 1.5 s into the dematerialisation).

`tardis_exit` puts Archie next to the TARDIS and steps him in. Use `--scene-ms` to follow the whole exit sequence. With a 6.6 s TARDIS sound: Archie walks in and fades out over 0 to 0.5 s, the dematerialisation runs from 0.9 s to about 7.5 s, the "Level 2" card from about 7.8 to 9.7 s, and level 2 starts after that.

```bash
SDL_VIDEODRIVER=dummy python3 game.py --seed 1 --scene tardis_exit --scene-ms 300 --screenshot exit.png
SDL_VIDEODRIVER=dummy python3 game.py --seed 1 --level 5 --scene laser --screenshot laser5.png
```
