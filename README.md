# Daleks in Hedges

An isometric hedge maze. Archie or Holly stays in the middle of the screen and the maze stays flat. Daleks roam the hedges; reach the TARDIS in the far corner to escape to the next level, where there is a new maze and more Daleks.

The game opens on a **title screen** with a live decorative maze (ten Daleks roaming, no deaths) and a character select: Archie or Holly. After you are exterminated you return to the title screen to pick again.

## Play

```bash
git clone https://github.com/brixham99/Archie-Maze.git
cd Archie-Maze
pip install -r requirements.txt
python3 game.py
```

| Key | Action |
| --- | --- |
| Left / A, Right / D | Turn Archie |
| Up / W | Step forward |
| Down / S | Step back |
| H (or Shift) | **Chameleon Cloak**: hide as a hedge for up to 4 s (press again to stop early); 3 s to recharge |
| M | Mute / unmute the sound |
| Enter, R or Space | On the title screen: start. After you are exterminated: return to the title screen |
| Esc | Quit |

A Dalek sees Archie only along the corridor it is facing, up to 8 cells away with no hedge in between. It shouts, its eye stalk glows, and a moment later it fires. Daleks cannot see a hedge, and they turn away if one is in their path.

## Title screen

A live maze scrolls behind the menu with ten Daleks roaming for atmosphere (they cannot kill you there). Choose **Archie** or **Holly** with Left/Right, A/D, or 1/2, then Enter or Space to start. An original electronic title theme loops here (M mutes it); Dalek hums are silent until you play. Controls are listed on the title screen.

Every 7 seconds the middle of the title screen swaps between the character choice and the online **Top 10 scores**. Choosing keys work at any time (and bring the characters back); Enter or Space starts straight away.

## Score and leaderboard

Points come three ways:

- **1 point for every second on the move.** Time only counts while you are actually stepping from one cell to the next, plus a short 0.4 s grace after each step lands so tapping or holding the keys to walk counts smoothly. Standing still, turning on the spot, hiding under the Chameleon Cloak or bumping into a hedge earns nothing.
- **20 points each time a Dalek spots you** and shouts "Exterminate!", awarded the moment it shouts, even if the laser then gets you. One shout is one bonus: two Daleks spotting you together, or the same Dalek re-spotting you while it is still shouting, only counts once. A brief gold **+20** pops up beside the Score box. The random callouts ("Human detected!", "Destroy!", "Find the human!") are not worth anything.
- **50 points for each new level** you reach.

Nothing counts on the title screen, during the level card, while walking into the TARDIS, or after you are exterminated. Your score and the current high score are shown top-left, under the level box; the high score turns gold once you beat it.

When you are exterminated with at least one point, type a name (up to 8 letters, digits or spaces), then Enter to send it or Esc to skip. The last name you used is filled in for you. Scores go to a free [dreamlo](http://dreamlo.com) leaderboard, which keeps each name's best score. Public Top 10: <http://dreamlo.com/lb/6ac7b3018f40bc15a8400bbc/json>

All leaderboard traffic happens in the background with a short timeout, so the game never waits for it. Offline, the last Top 10 is shown from a local cache and unsent scores are kept and sent next time the title screen is reached online. The cache, your last name and your local best live in `~/.daleks_in_hedges/scores.json`. Run with `--offline` to never contact dreamlo.

Note: free dreamlo boards are client-side by design, so the private code that adds scores is in `game.py` and anyone reading the source could post or clear scores. That is fine for a family game; for anything more serious use a leaderboard with a server-side secret.

## Chameleon Cloak

Press **H** (or Shift) to become a hedge for up to 4 seconds. Daleks cannot see you while you are cloaked. A device graphic in the bottom-right corner shows the charge (ready / depleting / recharging). Peeking eyes still show so you can find yourself.

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

If a Dalek exterminates you, the message shows the character and the level you reached. Press Enter, R or Space to return to the title screen and choose again.

Each level starts with the TARDIS that dropped Archie off standing on the corner cell, with Archie one cell in front of it, facing into the maze. You cannot walk back into it while it is there. After 5 seconds it dematerialises, fading in and out for as long as the TARDIS sound lasts (about 6.6 s with the supplied clip). You can start walking straight away.

```bash
python3 game.py --seed 1                 # fixed maze (after the title screen)
python3 game.py --no-title --character holly
python3 game.py --level 4 --no-title     # start on level 4 (9 Daleks)
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
| `dalek_human_detected.wav`, `dalek_destroy.wav`, `dalek_find_the_human.wav` | Ambient callouts: every 30 to 45 s of play (random each time) the nearest Dalek says one of them at random (never the same twice running, one at a time). It is exactly as loud as that Dalek's hum would be (same straight-line distance, silent from about 25 cells, louder up close, same left/right pan), and follows the Dalek while it speaks. Skipped if every Dalek is out of earshot; held back while another voice is speaking or a Dalek is aiming; cut short by "Exterminate!". Never on the title screen, while dead or leaving in the TARDIS; M mutes them | The same voice chain as `exterminate.wav` (HU-MAN DE-TEC-TED!, DE-STROY!, FIND THE HU-MAN!) |
| `laser.wav` | The Dalek fires | Synthesised: a descending zap with buzz and crackle |
| `step1.wav`, `step2.wav`, `step3.wav` | One soft footstep per half-tile hop, varied | Synthesised: a low thump plus a little gravel crunch |
| `dalek_hum.wav` | Loops for each Dalek gliding within about 25 cells (straight line), faint far off and louder up close, panned a little left or right; it fades out while the Dalek turns or stands still. Four mixer channels carry the hums of the four loudest Daleks | Synthesised 2 s seamless loop: detuned saw and square oscillators (110, 111, 165 and 220.5 Hz) through a resonant filter sweeping 400 to 2500 Hz twice per loop, a 4 Hz throb, an FM shimmer and an electronic whoosh. Pitched so laptop speakers can play it |
| `title_theme.wav` | Loops on the title screen (muted with M); stops when a game starts. Dalek hums stay silent on the title | Synthesised 12 s seamless loop: heavy 55 Hz bass throb, whooshy swept-noise pad, eerie minor lead motif, soft shimmer and drone. Original electronic track inspired by Doctor Who *vibes* only — not the BBC theme |
| `tardis_demat.wav` | The TARDIS dematerialises, 5 s into each level, and again when Archie leaves in it | A supplied recording. `tools/make_sounds.py` can also synthesise an original wheeze-groan here (three rising-and-falling grinding groans with ring-modulated metallic overtones, reverb and a soft thud), but it keeps an existing file unless you pass `--overwrite-tardis` |

To regenerate them (needs numpy; the voices also need `espeak-ng`, for example `sudo apt install espeak-ng`):

```bash
python3 tools/make_sounds.py
python3 tools/make_sounds.py --only dalek_human_detected dalek_destroy dalek_find_the_human   # just these, leave the rest
python3 tools/make_sounds.py --spectrograms /tmp   # optional spectrogram PNGs (the hum is shown looped twice)
```

Drop your own TARDIS sound as `assets/sounds/tardis_real.wav` (or `.ogg`/`.mp3`) to use it; it is not included and is git-ignored. It replaces `tardis_demat.wav`, and the dematerialisation stretches to the clip's length (3 to 15 s), so the TARDIS finishes fading just before the sound ends.

If the computer has no working audio, or a sound file is missing, the game still runs, just silently.

## Effects and HUD

The world, HUD text, laser and overlays are all drawn on the low-resolution view and nearest-neighbour scaled up, so UI looks as chunky as the maze. The Dalek laser and glows use solid-colour lines and circles. The TARDIS roof-lamp glow and the Chameleon Cloak badge are PNGs in `assets/fx/`. The cloak badge is the one antialiased graphic: it is rendered with 4x4 supersampling, so its curved edges are soft rather than stair-stepped (the HUD box, meter and text stay chunky). They are made by:

```bash
python3 tools/make_fx.py
```

Each frame is drawn into an opaque back buffer and copied to the window in one go.

## Testing without a screen

```bash
SDL_VIDEODRIVER=dummy python3 game.py --seed 1 --screenshot shot.png --frames 20
SDL_VIDEODRIVER=dummy python3 game.py --seed 1 --scene laser --screenshot laser.png
```

Scenes: `dalek`, `laser`, `telegraph`, `disguise`, `tardis`, `tardis_demat`, `tardis_exit`, `title`, `title_top10`, `score_hud`, `name_entry`. Headless runs never contact dreamlo or write the score file; add `--demo-scores` to fill the Top 10 with sample names for a screenshot. Add `--scene-ms N` to choose how far into the scene the shot is taken, for example `--scene tardis_demat --scene-ms 6500` (the TARDIS waits 5 s, so that is 1.5 s into the dematerialisation).

`tardis_exit` puts Archie next to the TARDIS and steps him in. Use `--scene-ms` to follow the whole exit sequence. With a 6.6 s TARDIS sound: Archie walks in and fades out over 0 to 0.5 s, the dematerialisation runs from 0.9 s to about 7.5 s, the "Level 2" card from about 7.8 to 9.7 s, and level 2 starts after that.

```bash
SDL_VIDEODRIVER=dummy python3 game.py --seed 1 --scene tardis_exit --scene-ms 300 --screenshot exit.png
SDL_VIDEODRIVER=dummy python3 game.py --seed 1 --level 5 --scene laser --screenshot laser5.png
```
