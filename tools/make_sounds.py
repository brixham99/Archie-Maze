#!/usr/bin/env python3
"""Generate the Archie Maze sound effects as small WAV files.

    python3 tools/make_sounds.py                 # writes assets/sounds/*.wav
    python3 tools/make_sounds.py --spectrograms DIR

Needs numpy. The two voice sounds (ow, exterminate) also need espeak-ng on
the PATH (offline TTS); the laser and footsteps are pure synthesis.
Everything is 22050 Hz, 16-bit mono.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import tempfile
import wave

import numpy as np

SR = 22050
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "assets", "sounds")


# ---------------------------------------------------------------- helpers
def write_wav(path: str, x: np.ndarray):
    x = np.clip(x, -1.0, 1.0)
    data = (x * 32767.0).astype("<i2").tobytes()
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(data)


def read_wav(path: str) -> np.ndarray:
    with wave.open(path, "rb") as w:
        sr = w.getframerate()
        n = w.getnframes()
        raw = w.readframes(n)
        ch = w.getnchannels()
    x = np.frombuffer(raw, dtype="<i2").astype(np.float64) / 32768.0
    if ch > 1:
        x = x.reshape(-1, ch).mean(axis=1)
    if sr != SR:
        x = resample(x, sr / SR)
    return x


def resample(x: np.ndarray, factor: float) -> np.ndarray:
    """Play back `factor` times faster (factor > 1 raises pitch, shortens)."""
    n = max(1, int(len(x) / factor))
    src = np.arange(n) * factor
    return np.interp(src, np.arange(len(x)), x)


def onepole_lp(x, fc):
    a = np.exp(-2.0 * np.pi * fc / SR)
    y = np.empty_like(x)
    acc = 0.0
    for i, v in enumerate(x):
        acc = (1 - a) * v + a * acc
        y[i] = acc
    return y


def onepole_hp(x, fc):
    return x - onepole_lp(x, fc)


def biquad_bp(x, fc, q):
    w0 = 2 * np.pi * fc / SR
    alpha = np.sin(w0) / (2 * q)
    b0, b1, b2 = alpha, 0.0, -alpha
    a0, a1, a2 = 1 + alpha, -2 * np.cos(w0), 1 - alpha
    b0, b1, b2, a1, a2 = b0 / a0, b1 / a0, b2 / a0, a1 / a0, a2 / a0
    y = np.zeros_like(x)
    x1 = x2 = y1 = y2 = 0.0
    for i, v in enumerate(x):
        out = b0 * v + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2
        x2, x1 = x1, v
        y2, y1 = y1, out
        y[i] = out
    return y


def comb(x, delay_s, feedback, mix):
    d = max(1, int(delay_s * SR))
    y = np.concatenate([x, np.zeros(d * 6)])
    for i in range(d, len(y)):
        y[i] += feedback * y[i - d]
    dry = np.concatenate([x, np.zeros(d * 6)])
    return (1 - mix) * dry + mix * y


def trim(x, thresh=0.01, pad=0.005):
    idx = np.nonzero(np.abs(x) > thresh)[0]
    if idx.size == 0:
        return x
    p = int(pad * SR)
    return x[max(0, idx[0] - p): min(len(x), idx[-1] + p)]


def fade(x, fin=0.004, fout=0.02):
    x = x.copy()
    a = min(len(x), int(fin * SR))
    b = min(len(x), int(fout * SR))
    if a:
        x[:a] *= np.linspace(0, 1, a)
    if b:
        x[-b:] *= np.linspace(1, 0, b)
    return x


def normalise(x, peak):
    m = np.max(np.abs(x)) or 1.0
    return x * (peak / m)


def espeak(text: str, voice: str, pitch: int, speed: int, amp: int = 160, extra=()) -> np.ndarray:
    exe = shutil.which("espeak-ng") or shutil.which("espeak")
    if exe is None:
        raise SystemExit("espeak-ng is needed for the voice sounds (apt install espeak-ng)")
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "say.wav")
        subprocess.run(
            [exe, "-v", voice, "-p", str(pitch), "-s", str(speed), "-a", str(amp), *extra, "-w", path, text],
            check=True,
        )
        return read_wav(path)


# ---------------------------------------------------------------- sounds
def make_exterminate() -> np.ndarray:
    """Staccato EX-TER-MIN-ATE!, ring-modulated at 30 Hz and roughened."""
    parts = [
        # (text, espeak pitch, speed, gap after in seconds)
        ("[[Eks]]", 58, 175, 0.07),
        ("[[t3:]]", 62, 175, 0.07),
        ("[[mIn]]", 68, 175, 0.08),
        ("[[eI:t]]", 86, 105, 0.0),
    ]
    out = []
    for text, pitch, speed, gap in parts:
        syl = trim(espeak(text, "en-gb", pitch, speed, 180), 0.02)
        syl = fade(normalise(syl, 1.0), 0.003, 0.015)
        out.append(syl)
        out.append(np.zeros(int(gap * SR)))
    x = np.concatenate(out)
    # Raise it a touch: Daleks are shrill.
    x = resample(x, 1.06)
    t = np.arange(len(x)) / SR
    # Compress, then the classic 30 Hz ring modulator (mostly wet).
    x = np.tanh(3.0 * x) / np.tanh(3.0)
    ring = x * np.sin(2 * np.pi * 30.0 * t)
    x = 0.82 * ring + 0.18 * x
    # Harshness: drive into a soft clip, thin out the lows, emphasise the
    # rasp around 1.8 kHz, and a short metallic comb (inside the casing).
    x = np.tanh(5.0 * x)
    x = onepole_hp(x, 260.0)
    x = x + 0.6 * biquad_bp(x, 1800.0, 1.4)
    x = onepole_lp(x, 5200.0)
    x = comb(x, 0.0065, 0.35, 0.35)
    x = trim(x, 0.004)
    return fade(normalise(x, 0.89), 0.002, 0.04)


def make_laser() -> np.ndarray:
    """A descending zap with buzz and a noise crackle, about 0.42 s."""
    rng = np.random.default_rng(11)
    dur = 0.42
    n = int(dur * SR)
    t = np.arange(n) / SR
    f = 2600.0 * (170.0 / 2600.0) ** (t / dur)
    phase = 2 * np.pi * np.cumsum(f) / SR
    buzz = 1.0 + 0.45 * np.sin(2 * np.pi * 55.0 * t)
    tone = np.tanh(3.5 * np.sin(phase)) * 0.65 + 0.35 * np.sin(2.01 * phase)
    tone *= buzz
    noise = rng.uniform(-1, 1, n)
    crackle = onepole_hp(noise, 2500.0) * np.exp(-t / 0.05)
    hiss = onepole_lp(noise, 4000.0) * 0.25
    env = np.minimum(1.0, t / 0.004) * np.exp(-t / 0.16)
    x = (tone * 0.8 + hiss) * env + crackle * 0.55
    x = comb(x, 0.011, 0.3, 0.25)
    x = x[: int((dur + 0.03) * SR)]
    return fade(normalise(x, 0.82), 0.001, 0.03)


def make_ow() -> np.ndarray:
    """A short cute boy's 'ow!': light TTS voice, pitched up, quick."""
    # "Ow!" reads as "oh"; "Ouw!" gives /aUw/. Note espeak-ng ignores a
    # +variant on "en-gb", so the light f5 variant goes on plain "en".
    x = espeak("Ouw!", "en+f5", 95, 190, 170)
    x = trim(x, 0.015)
    # Speed up by ~2.5 semitones: higher pitch and smaller formants read
    # as a child's voice; it also keeps it short.
    x = resample(x, 1.16)
    x = onepole_hp(x, 180.0)
    x = trim(x, 0.01)
    return fade(normalise(x, 0.85), 0.003, 0.05)


def make_step(seed: int, pitch: float) -> np.ndarray:
    """A soft footstep on dirt and grit: low thump plus a little crunch."""
    rng = np.random.default_rng(seed)
    dur = 0.13
    n = int(dur * SR)
    t = np.arange(n) / SR
    noise = rng.uniform(-1, 1, n)
    thump = onepole_lp(onepole_lp(noise, 380.0 * pitch), 380.0 * pitch)
    thump = normalise(thump, 1.0) * np.exp(-t / 0.022) * np.minimum(1.0, t / 0.003)
    grains = np.zeros(n)
    count = int(rng.integers(26, 38))
    pos = (rng.beta(1.3, 3.0, count) * 0.09 * SR).astype(int)
    for p in pos:
        length = int(rng.integers(12, 40))
        burst = rng.uniform(-1, 1, length) * np.exp(-np.arange(length) / (length / 3))
        end = min(n, p + length)
        grains[p:end] += burst[: end - p] * rng.uniform(0.3, 1.0)
    crunch = biquad_bp(grains, 3200.0 * pitch, 0.9)
    crunch = normalise(crunch, 1.0) * np.exp(-t / 0.045)
    x = 0.75 * thump + 0.32 * crunch
    return fade(normalise(x, 0.30), 0.001, 0.03)


SOUNDS = {
    "exterminate": make_exterminate,
    "laser": make_laser,
    "ow": make_ow,
    "step1": lambda: make_step(101, 1.0),
    "step2": lambda: make_step(202, 0.88),
    "step3": lambda: make_step(303, 1.12),
}


# ---------------------------------------------------------------- spectrogram
def spectrogram_png(x: np.ndarray, path: str, title: str):
    import pygame

    win, hop = 512, 64
    frames = max(1, (len(x) - win) // hop)
    w = np.hanning(win)
    spec = np.array([np.abs(np.fft.rfft(x[i * hop: i * hop + win] * w)) for i in range(frames)]).T
    db = 20 * np.log10(spec + 1e-6)
    db = np.clip((db - (db.max() - 70)) / 70, 0, 1)
    db = db[::-1]  # low frequencies at the bottom
    # simple heat map: black -> purple -> orange -> yellow
    stops = np.array([[0, 0, 0], [70, 10, 110], [220, 70, 40], [255, 220, 90], [255, 255, 230]], float)
    idx = db * (len(stops) - 1)
    lo = np.floor(idx).astype(int).clip(0, len(stops) - 2)
    fr = (idx - lo)[..., None]
    rgb = stops[lo] * (1 - fr) + stops[lo + 1] * fr
    pygame.init()
    img = pygame.surfarray.make_surface(rgb.transpose(1, 0, 2).astype(np.uint8))
    W, H = 900, 380
    img = pygame.transform.smoothscale(img, (W, H))
    canvas = pygame.Surface((W + 60, H + 50))
    canvas.fill((24, 24, 28))
    canvas.blit(img, (50, 30))
    font = pygame.font.Font(None, 20)
    canvas.blit(font.render(f"{title}  ({len(x) / SR:.2f} s, 0-{SR // 2} Hz)", True, (230, 230, 230)), (50, 8))
    for khz in range(0, SR // 2000 + 1, 2):
        y = 30 + H - int(H * khz * 1000 / (SR / 2))
        canvas.blit(font.render(f"{khz}k", True, (200, 200, 200)), (8, y - 7))
    secs = len(x) / SR
    step = 0.1 if secs < 1.0 else 0.25
    s = 0.0
    while s <= secs + 1e-9:
        xp = 50 + int(W * s / secs)
        pygame.draw.line(canvas, (200, 200, 200), (xp, H + 30), (xp, H + 35))
        canvas.blit(font.render(f"{s:.2f}", True, (200, 200, 200)), (xp - 12, H + 36))
        s += step
    pygame.image.save(canvas, path)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--spectrograms", default=None, help="also write spectrogram PNGs here")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    for name, fn in SOUNDS.items():
        x = fn()
        path = os.path.join(args.out, f"{name}.wav")
        write_wav(path, x)
        rms = float(np.sqrt(np.mean(x ** 2)))
        print(f"{name:12s} {len(x) / SR:5.2f} s  peak {np.max(np.abs(x)):.2f}  rms {rms:.3f}  -> {os.path.relpath(path)}")
        if args.spectrograms and name in ("exterminate", "laser", "ow"):
            os.makedirs(args.spectrograms, exist_ok=True)
            spectrogram_png(x, os.path.join(args.spectrograms, f"spec_{name}.png"), name)


if __name__ == "__main__":
    main()
