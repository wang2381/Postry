"""Procedurally synthesize royalty-free ambient music that matches a mood.

No external audio is used, so there are no copyright problems on Instagram.
If you'd rather use your own tracks, drop files in music/<mood>.mp3 (or .wav)
and they will be used instead (see `pick_track`).
"""
from pathlib import Path
import wave
import numpy as np

from .mood import Mood

SR = 44100


def _env(n: int, attack: float, decay: float) -> np.ndarray:
    t = np.arange(n) / SR
    return np.minimum(t / attack, 1.0) * np.exp(-t / decay)


def _reverb(x: np.ndarray, seconds: float, rng) -> np.ndarray:
    n = int(SR * seconds)
    ir = rng.standard_normal(n) * np.exp(-np.arange(n) / (SR * seconds / 4))
    ir[0] = 0
    size = 1 << (len(x) + n).bit_length()
    y = np.fft.irfft(np.fft.rfft(x, size) * np.fft.rfft(ir, size), size)[: len(x)]
    return y / (np.abs(y).max() + 1e-9)


def synth(mood: Mood, duration: float, out_path: str | Path, seed: int = 0) -> Path:
    rng = np.random.default_rng(seed)
    n = int(duration * SR)
    t = np.arange(n) / SR
    freq = lambda semis, octave=1.0: mood.root_hz * octave * 2 ** (semis / 12)

    # Pad: detuned sines on chord tones, slow breathing.
    pad = np.zeros(n)
    for i, s in enumerate(mood.scale[:4]):
        f = freq(s, 0.5)
        lfo = 0.65 + 0.35 * np.sin(2 * np.pi * (0.07 + 0.03 * i) * t + i)
        for detune in (-0.003, 0.0, 0.003):
            pad += lfo * (np.sin(2 * np.pi * f * (1 + detune) * t)
                          + 0.3 * np.sin(2 * np.pi * 2 * f * (1 + detune) * t))
    pad /= np.abs(pad).max()

    # Plucked arpeggio notes with a soft bell-like decay.
    arp = np.zeros(n)
    step = 60.0 / mood.bpm
    k = 0
    pos = 1.0
    while pos < duration - 1:
        s = mood.scale[int(rng.integers(len(mood.scale)))]
        f = freq(s, 2.0 if rng.random() < 0.7 else 1.0)
        m = int(min(3.0 * SR, n - int(pos * SR)))
        nt = np.arange(m) / SR
        note = (np.sin(2 * np.pi * f * nt) + 0.25 * np.sin(2 * np.pi * 2.01 * f * nt)) * _env(m, 0.01, 0.9)
        a = int(pos * SR)
        arp[a:a + m] += note * (0.5 + 0.5 * rng.random())
        pos += step * float(rng.choice([1, 1, 2, 3]))
        k += 1
    arp /= np.abs(arp).max() + 1e-9

    dry = 0.55 * pad + 0.45 * arp
    left = dry + 0.6 * _reverb(dry, 2.5, rng)
    right = dry + 0.6 * _reverb(dry, 2.5, rng)
    stereo = np.stack([left, right], axis=1)

    fade_in, fade_out = int(1.5 * SR), int(3.0 * SR)
    stereo[:fade_in] *= np.linspace(0, 1, fade_in)[:, None]
    stereo[-fade_out:] *= np.linspace(1, 0, fade_out)[:, None]
    stereo *= 0.8 / np.abs(stereo).max()

    out_path = Path(out_path)
    with wave.open(str(out_path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((stereo * 32767).astype("<i2").tobytes())
    return out_path


def pick_track(mood: Mood, duration: float, out_path: str | Path, music_dir="music",
               source: str = "openverse", seed: int = 0, hints=()):
    """Return (audio_path, credit_text_or_None).

    Order: your own music/<mood>.mp3 -> Openverse (Creative Commons) -> synthesized.
    """
    for ext in (".mp3", ".wav", ".m4a"):
        p = Path(music_dir) / f"{mood.name}{ext}"
        if p.exists():
            return p, None
    if source == "openverse":
        from .openverse import fetch_track
        track = fetch_track(mood.name, duration, Path(out_path).parent / "music_cache", seed, hints)
        if track:
            print(f"  music: {track.credit}")
            return track.path, track.credit
        print("  no suitable Openverse track found; using synthesized music")
    return synth(mood, duration, out_path), None
