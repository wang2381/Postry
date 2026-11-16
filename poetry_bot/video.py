"""Render an animated 1080x1920 story video: flowing gradient + drifting
particles + poem lines fading in one by one, muxed with an audio track."""
import os
import subprocess
from pathlib import Path

import imageio_ffmpeg
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .mood import Mood
from .poems import Poem

W, H, FPS = 1080, 1920, 30
LW, LH = 135, 240  # low-res grid for the background field (upscaled)
SAFE_TOP, SAFE_BOTTOM = 260, 360  # areas covered by the Instagram story UI

CJK_FONTS = [
    "/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSerifCJK-Regular.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/mnt/c/Windows/Fonts/msyh.ttc",
    "/mnt/c/Windows/Fonts/simsun.ttc",
]
LATIN_FONTS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
    "/mnt/c/Windows/Fonts/georgia.ttf",
]


def _font(size: int, text: str) -> ImageFont.FreeTypeFont:
    candidates = []
    if os.getenv("FONT_PATH"):
        candidates.append(os.environ["FONT_PATH"])
    if any(ord(c) > 0x2E80 for c in text):
        candidates += CJK_FONTS
    candidates += LATIN_FONTS
    for p in candidates:
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default(size)


def _wrap(line: str, font, max_w: int) -> list[str]:
    tokens = line.split(" ") if " " in line else list(line)
    sep = " " if " " in line else ""
    out, cur = [], ""
    for tok in tokens:
        trial = (cur + sep + tok) if cur else tok
        if font.getlength(trial) <= max_w or not cur:
            cur = trial
        else:
            out.append(cur)
            cur = tok
    return out + [cur] if cur else out


PER_LINE, FADE, HOLD, LAST_HOLD, T0, OUT_FADE, GAP, XFADE = 2.0, 0.9, 2.0, 4.0, 1.5, 0.8, 0.3, 1.2


def timeline(poem: Poem):
    """[(start, end)] per stanza and the total story duration (uncapped).
    A stanza's text fades out just before `end`; the next stanza starts GAP later."""
    spans, t, end = [], T0, T0
    for i, lines in enumerate(poem.stanzas):
        n = len(lines) + (1 if i == 0 and poem.title else 0)
        last = i == len(poem.stanzas) - 1
        end = t + n * PER_LINE + (LAST_HOLD if last else HOLD)
        spans.append((t, end))
        t = end + GAP
    return spans, end


def _smooth(x: float) -> float:
    x = min(max(x, 0.0), 1.0)
    return x * x * (3 - 2 * x)


def _stanza_layers(lines: list[str], title: str, size: int, all_text: str):
    """Pre-render a stanza (and optional title) to one RGBA layer per line, centred vertically."""
    font = _font(size, all_text)
    title_font = _font(40, all_text)
    max_w = W - 220
    gap, line_h = 34, int(size * 1.35)

    items = []  # (lines, font, height)
    if title:
        items.append(([title.upper()], title_font, int(40 * 1.6) + 20))
    for l in lines:
        wrapped = _wrap(l, font, max_w)
        items.append((wrapped, font, len(wrapped) * line_h))

    total = sum(h for *_, h in items) + gap * (len(items) - 1)
    avail = H - SAFE_TOP - SAFE_BOTTOM
    y = SAFE_TOP + max(0, (avail - total) // 2)

    layers = []
    for lns, f, h in items:
        img = Image.new("RGBA", (W, h + 40), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        for i, ln in enumerate(lns):
            x = (W - f.getlength(ln)) / 2
            yy = 20 + i * line_h
            d.text((x + 3, yy + 4), ln, font=f, fill=(0, 0, 0, 120))  # soft shadow
            d.text((x, yy), ln, font=f, fill=(255, 255, 255, 255))
        layers.append((y - 20, np.asarray(img, dtype=np.float32) / 255.0))
        y += h + gap
    return layers


def _credit_layer(text: str):
    """Small attribution line near the bottom (above the story UI zone)."""
    font = _font(28, text)
    lines = _wrap(text, font, W - 200)[:2]
    h = len(lines) * 40 + 20
    img = Image.new("RGBA", (W, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    for i, ln in enumerate(lines):
        x = (W - font.getlength(ln)) / 2
        d.text((x + 2, 10 + i * 40 + 2), ln, font=font, fill=(0, 0, 0, 120))
        d.text((x, 10 + i * 40), ln, font=font, fill=(255, 255, 255, 255))
    return (H - SAFE_BOTTOM - h - 10, np.asarray(img, dtype=np.float32) / 255.0)


def _gradient_lut(colors, brightness):
    stops = np.array(colors, dtype=np.float32)
    xs = np.linspace(0, 1, 256)
    pts = np.array([0, 0.5, 1.0])
    lut = np.stack([np.interp(xs, pts, stops[:, c]) for c in range(3)], axis=1)
    return np.clip(lut * brightness, 0, 255)


_k = np.arange(-3, 4, dtype=np.float32)
_KERNEL = np.exp(-(_k[:, None] ** 2 + _k[None, :] ** 2) / 3.0)


def _background(t: float, lut, gx, gy, particles) -> np.ndarray:
    v = (np.sin(gx * 3.0 + t * 0.35)
         + np.sin(gy * 2.2 - t * 0.28)
         + np.sin((gx + gy) * 2.6 + t * 0.22)
         + np.sin(np.hypot(gx - 0.5, gy - 0.5) * 6.0 - t * 0.45))
    v = (v + 4) / 8  # 0..1
    # drifting glow particles (low-res, upscaled => soft bokeh)
    px = particles[:, 0] + 0.03 * np.sin(t * particles[:, 3] + particles[:, 4])
    py = (particles[:, 1] - t * particles[:, 2]) % 1.0
    ix, iy = (px % 1.0 * (LW - 1)).astype(int), (py * (LH - 1)).astype(int)
    glow = np.zeros((LH, LW), np.float32)
    for x, y, s in zip(ix, iy, particles[:, 5]):
        y0, x0 = y - 3, x - 3
        ky0, kx0 = max(0, -y0), max(0, -x0)
        ys, xs = max(0, y0), max(0, x0)
        sub = _KERNEL[ky0:, kx0:][:LH - ys, :LW - xs]
        glow[ys:ys + sub.shape[0], xs:xs + sub.shape[1]] += s * sub
    v = np.clip(v + glow * 0.35, 0, 1)
    rgb = lut[(v * 255).astype(np.uint8)].astype(np.uint8)
    img = Image.fromarray(rgb).resize((W, H), Image.BICUBIC)
    return np.asarray(img, dtype=np.float32)


def story_duration(poem: Poem) -> float:
    return float(np.clip(timeline(poem)[1], 10, 58))


def render(poem: Poem, mood: Mood, audio_path: str | Path, out_path: str | Path,
           duration: float | None = None, progress=True, credit: str | None = None,
           bg_clips: list | None = None) -> Path:
    """bg_clips: optional list of looping video clips, one per stanza (scene changes
    crossfade as each new stanza begins). Without it, the procedural gradient is used."""
    size = 62 if max(len(l) for l in poem.lines) < 45 else 52
    all_text = poem.text + poem.title
    stanza_layers = [_stanza_layers(lines, poem.title if i == 0 else "", size, all_text)
                     for i, lines in enumerate(poem.stanzas)]
    spans, _ = timeline(poem)
    credit_layer = _credit_layer(credit) if credit else None
    duration = duration or story_duration(poem)
    n_frames = int(duration * FPS)

    # scene i starts when stanza i-1's text has finished; it crossfades in over XFADE
    scenes = []
    if bg_clips:
        starts = [0.0] + [spans[min(i - 1, len(spans) - 1)][1] for i in range(1, len(bg_clips))]
        for i, clip in enumerate(bg_clips):
            end = (starts[i + 1] + XFADE) if i + 1 < len(bg_clips) else duration
            scenes.append({"clip": clip, "start": starts[i], "end": min(end, duration), "proc": None, "last": None})

    rng = np.random.default_rng(7)
    particles = np.stack([rng.random(45), rng.random(45), 0.02 + 0.04 * rng.random(45),
                          0.3 + rng.random(45), rng.random(45) * 6, 0.4 + 0.6 * rng.random(45)], axis=1)
    gx, gy = np.meshgrid(np.linspace(0, 1, LW, dtype=np.float32), np.linspace(0, 1.78, LH, dtype=np.float32))
    lut = _gradient_lut(mood.colors, mood.brightness)

    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    vign = (1 - 0.45 * (((xx / W - .5) ** 2 + (yy / H - .5) ** 2) * 2.2).clip(0, 1))[..., None]

    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    cmd = [ffmpeg, "-y", "-loglevel", "error",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
           "-i", str(audio_path),
           "-map", "0:v", "-map", "1:a", "-t", f"{duration:.2f}",
           "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
           "-af", f"afade=t=in:d=1,afade=t=out:st={max(duration - 3, 0):.2f}:d=3,loudnorm=I=-18:TP=-2",
           "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(out_path)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)

    def scene_frame(sc, t):
        """Next decoded frame of a scene (decoder starts lazily; repeats last frame at EOF)."""
        if sc["proc"] is None:
            sc["proc"] = subprocess.Popen(
                [ffmpeg, "-loglevel", "error", "-stream_loop", "-1", "-i", str(sc["clip"]), "-map", "0:v:0",
                 "-vf", f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={FPS}",
                 "-t", f"{sc['end'] - sc['start'] + 0.2:.2f}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                stdout=subprocess.PIPE)
        n, buf = W * H * 3, b""
        while len(buf) < n:
            more = sc["proc"].stdout.read(n - len(buf))
            if not more:
                break
            buf += more
        if len(buf) == n:
            sc["last"] = np.frombuffer(buf, np.uint8).reshape(H, W, 3).astype(np.float32)
        return sc["last"]

    def background(t):
        active = [sc for sc in scenes if sc["start"] <= t < sc["end"]]
        if not active:
            return None
        frames = [scene_frame(sc, t) for sc in active]
        if len(frames) == 1 or frames[0] is None or frames[-1] is None:
            return frames[-1] if frames[-1] is not None else frames[0]
        a = _smooth((t - active[-1]["start"]) / XFADE)
        return frames[0] * (1 - a) + frames[-1] * a

    try:
        for f in range(n_frames):
            t = f / FPS
            bg = background(t) if scenes else None
            if bg is not None:
                frame = bg * 0.72 * vign  # dim a little so the poem stays readable
            else:
                frame = _background(t, lut, gx, gy, particles) * vign
            for s, (t0, t1) in enumerate(spans):
                if t < t0:
                    continue
                last = s == len(spans) - 1
                out = 1.0 if last else 1.0 - _smooth((t - (t1 - OUT_FADE)) / OUT_FADE)
                if out <= 0:
                    continue
                for i, (y0, layer) in enumerate(stanza_layers[s]):
                    a = _smooth((t - (t0 + i * PER_LINE)) / FADE)
                    if a <= 0:
                        continue
                    rise = int((1 - a) * 24)
                    h = layer.shape[0]
                    ys = y0 + rise
                    alpha = layer[..., 3:4] * a * out
                    frame[ys:ys + h] = frame[ys:ys + h] * (1 - alpha) + layer[..., :3] * 255 * alpha
            if credit_layer is not None:
                y0, layer = credit_layer
                a = float(np.clip((t - 0.8) / 0.8, 0, 1))
                h = layer.shape[0]
                alpha = layer[..., 3:4] * a * 0.85
                frame[y0:y0 + h] = frame[y0:y0 + h] * (1 - alpha) + layer[..., :3] * 255 * alpha
            # fade to black at the end
            if t > duration - 1.0:
                frame *= max(0.0, (duration - t))
            proc.stdin.write(frame.clip(0, 255).astype(np.uint8).tobytes())
            if progress and f % FPS == 0:
                print(f"\r  rendering {f / n_frames:4.0%}", end="", flush=True)
    finally:
        for sc in scenes:
            if sc["proc"]:
                sc["proc"].kill()
        proc.stdin.close()
        proc.wait()
    if progress:
        print("\r  rendering 100%")
    if proc.returncode != 0:
        raise RuntimeError("ffmpeg failed")
    return Path(out_path)
