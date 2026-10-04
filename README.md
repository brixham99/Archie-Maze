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

You can hear a Dalek coming: it hums as it glides, louder the closer it is (distance through the maze counts most, since hedges muffle it), and the hum stops briefly while it turns or stands still.

Each game starts as the TARDIS that dropped Archie off dematerialises behind him, fading in and out over about 3.5 s. You can start walking straight away.

```bash
python3 game.py --seed 1
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
| `dalek_hum.wav` | Loops on its own channel for each Dalek gliding within about 9 cells, louder as it gets closer and panned a little left or right; it fades out while the Dalek turns or stands still | Synthesised 2 s seamless loop: a 75 Hz mechanical hum with harmonics and a slight wobble, under a breathy band-passed noise whoosh |
| `tardis_demat.wav` | The TARDIS dematerialises at the start of each game | Synthesised, an original wheeze-groan: three rising-and-falling grinding groans (noisy harmonics on a gliding pitch, a sweeping breathy band, ring-modulated metallic overtones) with reverb and a soft thud as it vanishes, timed to the fade pulses |

To regenerate them (needs numpy; the two voices also need `espeak-ng`, for example `sudo apt install espeak-ng`):

```bash
python3 tools/make_sounds.py
python3 tools/make_sounds.py --spectrograms /tmp   # optional spectrogram PNGs (the hum is shown looped twice)
```

If the computer has no working audio, or a sound file is missing, the game still runs, just silently.

## Testing without a screen

```bash
SDL_VIDEODRIVER=dummy python3 game.py --seed 1 --screenshot shot.png --frames 20
SDL_VIDEODRIVER=dummy python3 game.py --seed 1 --scene laser --screenshot laser.png
```

Scenes: `dalek`, `laser`, `telegraph`, `disguise`, `tardis`, `tardis_demat`. Add `--scene-ms N` to choose how far into the scene the shot is taken, for example `--scene tardis_demat --scene-ms 1500`.
