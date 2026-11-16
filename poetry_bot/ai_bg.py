"""AI-generated animated background: poem -> still image (Flux) -> animated clip
(Grok Imagine via fal.ai) -> seamless ping-pong loop.

Results are cached per poem so re-rendering never pays twice.
Approx cost: image ~$0.003 + Grok 720p ~$0.07/s (8 s ~ $0.60).
"""
import subprocess
from pathlib import Path

import imageio_ffmpeg

from . import fal
from .mood import Mood
from .poems import Poem

IMAGE_ENDPOINT = "fal-ai/flux/schnell"
VIDEO_ENDPOINT = "xai/grok-imagine-video/image-to-video"
CLIP_SECONDS = 8
COST_PER_SECOND = 0.07

STYLES = {
    "calm":     ("serene, tranquil, soft misty light, teal and silver tones",
                 "gentle flowing motion, slow drifting mist and light"),
    "sad":      ("melancholic, rainy blue-grey dusk, lonely atmosphere, muted colors",
                 "slow falling rain or drifting fog, very subtle movement"),
    "romantic": ("warm romantic glow, rose and golden tones, soft bokeh lights",
                 "soft swaying motion, floating petals or glowing lights"),
    "joyful":   ("bright golden sunlight, vivid warm colors, lively and airy",
                 "gentle wind in the scene, sparkling light, lively but smooth motion"),
    "dark":     ("moody dark atmosphere, deep shadows, mysterious violet and black tones",
                 "slow creeping fog and shifting shadows"),
    "hopeful":  ("hopeful sunrise glow, warm light breaking through darkness, orange and violet sky",
                 "light slowly growing, clouds drifting, embers or particles rising"),
}


def build_prompts(text: str, scene_hint: str, mood: Mood) -> tuple[str, str]:
    """Image + motion prompts for one scene. A hand-written Scene: hint wins over the stanza text."""
    style, motion = STYLES.get(mood.name, STYLES["calm"])
    if scene_hint:
        image = (f"Cinematic vertical artwork: {scene_hint}. {style}. Painterly, dreamy, atmospheric, "
                 "high detail. No text, no letters, no close-up faces.")
        video = (f"{scene_hint}. Slow cinematic camera movement with subtle natural motion "
                 f"(wind, dust, smoke, light). {motion}. No text.")
    else:
        image = (f"Cinematic vertical landscape artwork inspired by this poem: \"{text[:300]}\". "
                 f"{style}. Painterly, dreamy, beautiful, high detail. "
                 "No text, no letters, no people, no faces.")
        video = f"{motion}. Slow subtle camera push-in. Calm, graceful, cinematic. No text."
    return image, video


def _pingpong(src: Path, dst: Path) -> Path:
    """forward + reversed copy so looping has no visible jump."""
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    subprocess.run([ff, "-y", "-loglevel", "error", "-i", str(src), "-map", "0:v:0", "-an",
                    "-filter_complex", "[0:v]split[a][b];[b]reverse[r];[a][r]concat=n=2:v=1[v]",
                    "-map", "[v]", "-c:v", "libx264", "-crf", "16", "-pix_fmt", "yuv420p", str(dst)],
                   check=True)
    return dst


def generate_scene(text: str, hint: str, mood: Mood, name: str, out_dir: Path,
                   seconds: int = CLIP_SECONDS) -> Path:
    """Return a loopable background clip for one scene (cached under `name`)."""
    loop = out_dir / f"{name}_loop.mp4"
    if loop.exists():
        print(f"  using cached AI scene {loop.name}")
        return loop
    image_prompt, motion_prompt = build_prompts(text, hint, mood)

    still = out_dir / f"{name}_still.jpg"
    clip = out_dir / f"{name}_clip.mp4"
    if not clip.exists():
        if still.exists():
            import base64
            img_url = "data:image/jpeg;base64," + base64.b64encode(still.read_bytes()).decode()
        else:
            print(f"  [{name}] generating still image...")
            res = fal.run(IMAGE_ENDPOINT, {"prompt": image_prompt, "image_size": "portrait_16_9",
                                           "num_inference_steps": 4})
            img_url = res["images"][0]["url"]
            fal.download(img_url, still)
        print(f"  [{name}] animating with Grok Imagine ({seconds}s, ~${seconds * COST_PER_SECOND:.2f})...")
        res = fal.run(VIDEO_ENDPOINT, {"prompt": motion_prompt, "image_url": img_url,
                                       "duration": seconds, "resolution": "720p",
                                       "aspect_ratio": "9:16"}, timeout=900)
        fal.download(res["video"]["url"], clip)
    return _pingpong(clip, loop)


def generate(poem: Poem, mood: Mood, idx: int, out_dir: Path, seconds: int = CLIP_SECONDS) -> list[Path]:
    """One animated clip per stanza (generated in parallel). Single-stanza poems get one clip."""
    from concurrent.futures import ThreadPoolExecutor
    out_dir.mkdir(parents=True, exist_ok=True)
    n = len(poem.stanzas)
    jobs = [("\n".join(st), poem.scenes[i], f"poem_{idx}" + ("" if n == 1 else f"_s{i}"))
            for i, st in enumerate(poem.stanzas)]
    print(f"  AI background: {n} scene(s), up to ~${n * seconds * COST_PER_SECOND:.2f}")
    with ThreadPoolExecutor(n) as ex:
        futures = [ex.submit(generate_scene, t, h, mood, name, out_dir, seconds) for t, h, name in jobs]
        return [f.result() for f in futures]
