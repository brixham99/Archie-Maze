#!/usr/bin/env python3
"""Generate the Archie Maze sound effects as small WAV files.

    python3 tools/make_sounds.py                 # writes assets/sounds/*.wav
    python3 tools/make_sounds.py --spectrograms DIR

Needs numpy. The two voice sounds (ow, exterminate) also need espeak-ng on
the PATH (offline TTS); the laser and footsteps are pure synthesis.
Everything is 22050 Hz, 16-bit mono. title_theme is a longer seamless loop for the title screen.
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


def make_rustle() -> np.ndarray:
    """A tiny, soft leafy rustle for a single bump into a hedge."""
    rng = np.random.default_rng(77)
    dur = 0.16
    n = int(dur * SR)
    t = np.arange(n) / SR
    grains = np.zeros(n)
    for _ in range(int(rng.integers(40, 55))):
        p = int(rng.beta(1.4, 2.6) * 0.13 * SR)
        length = int(rng.integers(20, 70))
        burst = rng.uniform(-1, 1, length) * np.exp(-np.arange(length) / (length / 3))
        end = min(n, p + length)
        grains[p:end] += burst[: end - p] * rng.uniform(0.2, 1.0)
    leaves = biquad_bp(grains, 3600.0, 0.7)
    body = onepole_lp(onepole_lp(rng.uniform(-1, 1, n), 300.0), 300.0)
    body = normalise(body, 1.0) * np.exp(-t / 0.03) * np.minimum(1.0, t / 0.004)
    env = np.minimum(1.0, t / 0.01) * np.exp(-t / 0.06)
    x = normalise(leaves, 1.0) * env * 0.8 + body * 0.35
    return fade(normalise(x, 0.35), 0.002, 0.03)


def _chime(freq: float, dur: float, tau: float, rng) -> np.ndarray:
    """One small inharmonic bell/chime strike."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    out = np.zeros(n)
    for ratio, amp in ((1.0, 1.0), (2.756, 0.38), (5.404, 0.14), (8.93, 0.05)):
        f = freq * ratio * (1 + rng.uniform(-0.004, 0.004))
        out += amp * np.sin(2 * np.pi * f * t + rng.uniform(0, 2 * np.pi)) * np.exp(-t * ratio ** 0.5 / tau)
    return out * np.minimum(1.0, t / 0.002)


def make_cloak(rising: bool) -> np.ndarray:
    """Sped-up wind chime / teleport shimmer: a run of chimes and a sparkle."""
    rng = np.random.default_rng(31 if rising else 47)
    dur = 0.46
    n = int(dur * SR)
    t = np.arange(n) / SR
    # Pentatonic run C6..E7 (rising) or the reverse (falling).
    notes = [1046.5, 1174.7, 1318.5, 1568.0, 1760.0, 2093.0, 2349.3, 2637.0]
    if not rising:
        notes = notes[::-1]
    x = np.zeros(n)
    spacing = 0.034
    for i, f in enumerate(notes):
        start = int((i * spacing + rng.uniform(0, 0.006)) * SR)
        c = _chime(f, dur, 0.075, rng) * (0.75 + 0.25 * rng.random())
        x[start:] += c[: n - start]
    # Airy shimmer: high noise with a fast flutter, swelling over the run.
    noise = onepole_hp(rng.uniform(-1, 1, n), 5000.0)
    flutter = 0.5 + 0.5 * np.sin(2 * np.pi * 38.0 * t)
    swell = np.sin(np.pi * np.clip(t / 0.36, 0, 1)) ** 2
    x += normalise(noise, 1.0) * flutter * swell * 0.18
    # A soft sweep underneath (up for on, down for off).
    f0, f1 = (500.0, 1500.0) if rising else (1500.0, 500.0)
    sweep_f = f0 * (f1 / f0) ** np.clip(t / 0.34, 0, 1)
    sweep = np.sin(2 * np.pi * np.cumsum(sweep_f) / SR) * swell * 0.12
    x += sweep
    x = onepole_lp(x, 9000.0)
    return fade(normalise(x, 0.7), 0.002, 0.06)


def _circular_band(n, rng, fc, width_oct, tilt=0.0):
    """Noise band-passed with an FFT (circular), so the result loops seamlessly."""
    spec = np.fft.rfft(rng.standard_normal(n))
    f = np.fft.rfftfreq(n, 1.0 / SR)
    f[0] = 1e-3
    octs = np.log2(f / fc)
    shape = np.exp(-0.5 * (octs / width_oct) ** 2) * (f / fc) ** tilt
    y = np.fft.irfft(spec * shape, n)
    return y / (np.sqrt(np.mean(y ** 2)) or 1.0)



def make_title_theme() -> np.ndarray:
    """Original ~12 s seamless electronic title loop: Doctor Who *vibes* only
    (not the BBC theme). Heavy throbbing bass, whooshy swept synth, eerie
    minor lead. Every oscillator, LFO and sweep has a whole number of cycles
    in the loop so the end runs straight into the start. No clipping."""
    rng = np.random.default_rng(42)
    dur = 12.0
    n = int(dur * SR)
    t = np.arange(n) / SR

    def lfo(cycles, phase=0.0):
        return np.sin(2 * np.pi * cycles / dur * t + phase)

    # --- heavy bass: detuned saws at 55 Hz (integer cycles: 55*12=660) ---
    def partial_saw(f0, amp, n_partials=12):
        y = np.zeros(n)
        for k in range(1, n_partials + 1):
            y += (amp / k) * np.sin(2 * np.pi * k * f0 * t + rng.uniform(0, 2 * np.pi))
        return y

    bass = partial_saw(55.0, 1.0) + 0.7 * partial_saw(55.5, 0.55) + 0.35 * partial_saw(110.0, 0.4)
    # 2 Hz throb with a softer 1 Hz swell (24 and 12 cycles in 12 s)
    bass *= (0.55 + 0.45 * (0.5 + 0.5 * lfo(24)) * (0.65 + 0.35 * lfo(12, 0.3)))
    bass = onepole_lp(bass, 380.0)

    # --- whooshy noise pad: band centre sweeps 400↔2200 Hz, 3 cycles ---
    sweep = 0.5 + 0.5 * lfo(3, -np.pi / 2)
    fc = 400.0 * (2200.0 / 400.0) ** sweep
    whoosh = _swept_noise(n, rng, lambda tt: float(np.interp(tt, t, fc)), 0.55)
    whoosh = onepole_hp(whoosh, 180.0) * (0.35 + 0.65 * sweep)

    # --- eerie lead: minor motif (A3 E4 C4 G3 B3 E3 A3), soft square, portamento ---
    # Notes as Hz; each held for 1.5 s → 8 notes = 12 s exactly.
    motif = np.array([220.0, 329.63, 261.63, 196.0, 246.94, 164.81, 220.0, 174.61])
    note_n = n // len(motif)
    # smooth step between note frequencies (integer samples per note)
    freq = np.zeros(n)
    for i, f in enumerate(motif):
        a, b = i * note_n, (i + 1) * note_n if i < len(motif) - 1 else n
        # glide from previous into this note over first 0.12 s
        prev = motif[i - 1] if i else motif[-1]
        glide = int(0.12 * SR)
        for j in range(a, b):
            if j - a < glide:
                u = (j - a) / glide
                u = u * u * (3 - 2 * u)
                freq[j] = prev + (f - prev) * u
            else:
                freq[j] = f
    phase = np.cumsum(2 * np.pi * freq / SR)
    # soft square via odd partials, amplitude gently pulsed
    lead = np.zeros(n)
    for k in (1, 3, 5, 7):
        lead += (0.55 / k) * np.sin(k * phase + rng.uniform(0, 0.4))
    lead *= (0.7 + 0.3 * lfo(8))
    lead = onepole_lp(lead, 2400.0)

    # --- high ghost shimmer (detuned, quiet) ---
    shimmer = np.sin(2 * np.pi * 880.0 * t + 1.2 * np.sin(2 * np.pi * 110.0 * t))
    shimmer *= (0.25 + 0.75 * (0.5 + 0.5 * lfo(6))) * 0.12

    # --- low drone under everything ---
    drone = 0.22 * np.sin(2 * np.pi * 55.0 * t) + 0.12 * np.sin(2 * np.pi * 82.5 * t)
    drone *= (0.8 + 0.2 * lfo(4))

    x = 0.95 * bass + 0.55 * whoosh + 0.42 * lead + shimmer + drone
    # Soft edges already seamless by construction; normalise below clip
    peak = np.max(np.abs(x)) + 1e-9
    x = x / peak * 0.82
    # Equal-power crossfade of the last/first 100 ms into a seamless join.
    fade = int(0.10 * SR)
    head, tail = x[:fade].copy(), x[-fade:].copy()
    a = np.linspace(0, np.pi / 2, fade)
    blended = tail * np.cos(a) + head * np.sin(a)
    x[:fade] = blended
    x[-fade:] = blended  # identical ends → wrap has zero discontinuity
    x = np.clip(x / (np.max(np.abs(x)) + 1e-9) * 0.85, -0.95, 0.95)
    return x



def make_dalek_hum() -> np.ndarray:
    """A 2 s seamless loop: a throbbing electronic glide hum, pitched so that
    laptop and phone speakers (which drop everything below ~200 Hz) play it.

    Detuned saws at 110/111 Hz, a square at 165 Hz and a saw an octave up,
    built partial by partial (random partial phases keep the peaks low)
    through a resonant low-pass sweeping 400 -> 2500 Hz and back twice per
    loop, with a 150 Hz high-pass, a 4 Hz throb, an FM shimmer and a
    sweeping electronic whoosh. Every frequency, sweep and wobble has a whole
    number of cycles in 2 s, so the end runs straight into the start.
    """
    rng = np.random.default_rng(78)
    dur = 2.0
    n = int(dur * SR)
    t = np.arange(n) / SR

    def lfo(cycles_per_loop, phase=0.0):
        return np.sin(2 * np.pi * cycles_per_loop / dur * t + phase)

    sweep = 0.5 + 0.5 * lfo(2, -np.pi / 2)        # 0..1, twice per loop
    fc = 400.0 * (2500.0 / 400.0) ** sweep        # resonant low-pass cutoff
    q = 5.0

    def gain(f):
        r = f / fc
        lp = 1.0 / np.sqrt((1.0 - r * r) ** 2 + (r / q) ** 2)
        hp = f / np.sqrt(f * f + 150.0 ** 2)
        return lp * hp

    synth = np.zeros(n)
    for f0, amp, odd_only in ((110.0, 1.0, False), (111.0, 0.85, False), (165.0, 0.45, True), (220.5, 0.35, False)):
        k = 1
        while k * f0 < 6000.0:
            if not odd_only or k % 2 == 1:
                f = k * f0
                synth += amp / k * gain(f) * np.sin(2 * np.pi * f * t + rng.uniform(0, 2 * np.pi))
            k += 1
    synth /= np.sqrt(np.mean(synth ** 2))
    throb = 0.72 + 0.28 * lfo(8) * (0.55 + 0.45 * sweep)          # 4 Hz pulse
    synth *= throb
    fm = np.sin(2 * np.pi * 1320.0 * t + 1.5 * np.sin(2 * np.pi * 165.0 * t))
    shimmer = fm * (0.55 + 0.45 * lfo(7)) * (0.4 + 0.6 * sweep)    # 3.5 Hz flutter
    whoosh = _circular_band(n, rng, 1300.0, 0.45) * (0.35 + 0.65 * sweep)
    x = synth + 0.16 * shimmer + 0.14 * whoosh
    x = x / np.sqrt(np.mean(x ** 2)) * 0.20  # about -14 dBFS RMS
    return np.clip(x, -0.95, 0.95)


def _swept_noise(n, rng, fc_of_t, width_oct):
    """Noise through a band-pass whose centre moves with time (STFT masking)."""
    win, hop = 1024, 256
    w = np.hanning(win)
    noise = rng.standard_normal(n + win)
    out = np.zeros(n + win)
    norm = np.zeros(n + win)
    f = np.fft.rfftfreq(win, 1.0 / SR)
    f[0] = 1e-3
    for start in range(0, n, hop):
        fc = fc_of_t((start + win / 2) / SR)
        mask = np.exp(-0.5 * (np.log2(f / fc) / width_oct) ** 2)
        frame = np.fft.irfft(np.fft.rfft(noise[start:start + win] * w) * mask, win)
        out[start:start + win] += frame * w
        norm[start:start + win] += w * w
    return (out / np.maximum(norm, 1e-3))[:n]


def _reverb(x, rng, seconds=1.3, decay=0.38, wet=0.32):
    """Synthetic room: convolve with exponentially decaying, darkened noise."""
    m = int(seconds * SR)
    t = np.arange(m) / SR
    ir = rng.standard_normal(m) * np.exp(-t / decay)
    ir = onepole_lp(ir, 3500.0)
    ir[0] = 0.0
    ir /= np.sqrt(np.sum(ir ** 2))
    size = 1 << int(np.ceil(np.log2(len(x) + m)))
    tail = np.fft.irfft(np.fft.rfft(x, size) * np.fft.rfft(ir, size), size)[:len(x) + m]
    dry = np.concatenate([x, np.zeros(m)])
    return (1 - wet) * dry + wet * tail


TARDIS_CYCLE_S = 1.0   # one wheeze-groan per second, matching the visual pulses
TARDIS_CYCLES = 3


def make_tardis_demat() -> np.ndarray:
    """An original 'wheeze-groan' evocation (not a copy of any broadcast sound).

    Three rising-and-falling grinding groans, one per second, each swelling as
    the TARDIS fades on screen (loudest at 0.5, 1.5 and 2.5 s): narrow-band
    noisy harmonics on a gliding pitch, a breathy wheeze band that sweeps with
    it, ring-modulated metallic overtones, a synthetic reverb, and a soft
    thud as it winks out at about 3.25 s.
    """
    rng = np.random.default_rng(1963)
    body_s = TARDIS_CYCLES * TARDIS_CYCLE_S + 0.35
    n = int(body_s * SR)
    t = np.arange(n) / SR
    cyc = t / TARDIS_CYCLE_S
    ph = cyc % 1.0
    k = np.minimum(np.floor(cyc), TARDIS_CYCLES - 1)
    # Pitch: up then down each cycle (a slightly lopsided arch), sagging a
    # little lower cycle by cycle; the last cycle droops away.
    arch = np.sin(np.pi * np.clip(ph, 0, 1)) ** 1.3
    f0 = 92.0 * (1.0 - 0.05 * k) * (1.0 + 0.75 * arch)
    f0 = np.where(cyc >= TARDIS_CYCLES, 92.0 * 0.86 * (1 - 0.3 * np.clip(cyc - TARDIS_CYCLES, 0, 1)), f0)
    f0 = onepole_lp(f0, 12.0)
    # Loudness: a swell per cycle, peaking mid-cycle; the third one fades away.
    swell = 0.25 + 0.75 * np.sin(np.pi * np.clip(ph, 0, 1)) ** 1.6
    overall = np.where(cyc < TARDIS_CYCLES - 1, 1.0, np.clip(1.0 - 0.7 * (cyc - (TARDIS_CYCLES - 1)), 0.0, 1.0))
    env = onepole_lp(swell * overall, 25.0)
    env *= np.clip(t / 0.04, 0, 1)
    # Grinding groan: harmonics of f0, each with a jittery narrow-band
    # amplitude (low-passed noise), so it scrapes instead of singing.
    groan = np.zeros(n)
    phase = 2 * np.pi * np.cumsum(f0) / SR
    for h in range(1, 15):
        formant = np.exp(-0.5 * (np.log2(h * 92.0 * 1.4 / 800.0) / 0.8) ** 2) + 0.5 * np.exp(-0.5 * (np.log2(h * 92.0 * 1.4 / 2300.0) / 0.4) ** 2)
        jitter = onepole_lp(rng.standard_normal(n), 60.0 + 10 * h)
        jitter = 0.35 + jitter / (np.std(jitter) + 1e-9) * 0.65
        groan += formant / h ** 0.35 * jitter * np.sin(h * phase + rng.uniform(0, 2 * np.pi))
    groan = np.tanh(1.6 * groan / (np.std(groan) * 3))
    # Breathy wheeze: a noise band sweeping with the pitch, strongest on the up-swing.
    wheeze = _swept_noise(n, rng, lambda tt: 700.0 + 1500.0 * np.sin(np.pi * ((tt / TARDIS_CYCLE_S) % 1.0)) ** 1.3, 0.35)
    wheeze *= 0.6 + 0.4 * np.clip(np.cos(np.pi * ph), 0, 1)
    # Metallic overtones: the groan ring-modulated by two inharmonic carriers.
    metal = groan * (0.6 * np.sin(2 * np.pi * 431.0 * t) + 0.4 * np.sin(2 * np.pi * 1117.0 * t))
    metal = onepole_hp(metal, 400.0)
    x = env * (0.62 * groan / (np.std(groan) + 1e-9)
               + 0.30 * wheeze / (np.std(wheeze) + 1e-9)
               + 0.22 * metal / (np.std(metal) + 1e-9))
    x = onepole_lp(x, 4200.0)
    x = onepole_hp(x, 45.0)
    tail = int(0.15 * SR)
    x[-tail:] *= np.linspace(1.0, 0.0, tail) ** 2  # the groan dies away, no hard stop
    # Soft thud as it winks out.
    td = TARDIS_CYCLES * TARDIS_CYCLE_S + 0.25
    i0 = int(td * SR)
    m = n - i0
    tt = np.arange(m) / SR
    thud = (np.sin(2 * np.pi * (70.0 - 25.0 * tt / 0.35) * tt) * np.exp(-tt / 0.07)
            + 0.3 * onepole_lp(rng.standard_normal(m), 300.0) * np.exp(-tt / 0.04))
    x[i0:] += 0.9 * thud * np.clip(tt / 0.008, 0, 1)
    x = _reverb(x / np.max(np.abs(x)), rng)
    x = fade(x, 0.004, 0.25)
    return normalise(x, 0.85)


SOUNDS = {
    "exterminate": make_exterminate,
    "laser": make_laser,
    "ow": make_ow,
    "step1": lambda: make_step(101, 1.0),
    "step2": lambda: make_step(202, 0.88),
    "step3": lambda: make_step(303, 1.12),
    "rustle": make_rustle,
    "cloak_on": lambda: make_cloak(True),
    "cloak_off": lambda: make_cloak(False),
    "dalek_hum": make_dalek_hum,
    "title_theme": make_title_theme,
    "tardis_demat": make_tardis_demat,
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
    ap.add_argument("--overwrite-tardis", action="store_true",
                    help="replace an existing tardis_demat.wav (it may be a real clip you supplied) with ours")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    for name, fn in SOUNDS.items():
        path = os.path.join(args.out, f"{name}.wav")
        if name == "tardis_demat" and os.path.exists(path) and not args.overwrite_tardis:
            print(f"{name:12s} kept the existing {os.path.relpath(path)} (use --overwrite-tardis to replace it)")
            continue
        x = fn()
        write_wav(path, x)
        rms = float(np.sqrt(np.mean(x ** 2)))
        print(f"{name:12s} {len(x) / SR:5.2f} s  peak {np.max(np.abs(x)):.2f}  rms {rms:.3f}  -> {os.path.relpath(path)}")
        if args.spectrograms and name in ("exterminate", "laser", "ow", "cloak_on", "cloak_off", "rustle", "tardis_demat"):
            os.makedirs(args.spectrograms, exist_ok=True)
            spectrogram_png(x, os.path.join(args.spectrograms, f"spec_{name}.png"), name)
        if args.spectrograms and name == "title_theme":
            spectrogram_png(np.concatenate([x, x[: SR]]), os.path.join(args.spectrograms, "spec_title_theme.png"),
                            f"title_theme, {len(x)/SR:.1f}s loop (+1s of next)")
        if args.spectrograms and name == "dalek_hum":
            # The loop played twice, so the seam at 2.00 s can be checked by eye.
            os.makedirs(args.spectrograms, exist_ok=True)
            spectrogram_png(np.concatenate([x, x]), os.path.join(args.spectrograms, "spec_dalek_hum.png"),
                            "dalek_hum, looped twice (seam at 2.00 s)")


if __name__ == "__main__":
    main()
