#!/usr/bin/env python3
"""Cost-limited comparison: 1 image + 1 short clip per model, saved to output/ai_test/.

  python try_video_models.py            # runs the default two models
"""
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from dotenv import load_dotenv

from poetry_bot import fal

IMAGE_PROMPT = ("serene moonlit ocean at dusk, gentle waves on a quiet empty shore, soft painterly "
                "cinematic style, deep teal and silver light, dreamy atmosphere, vertical composition, "
                "no text, no people")
MOTION_PROMPT = ("waves roll gently onto the shore, moonlight shimmers on the water, clouds drift slowly, "
                 "slow subtle camera push-in, calm and peaceful")

MODELS = {
    # name: (endpoint, payload builder)  -- input names verified against fal's OpenAPI schemas
    "grok": ("xai/grok-imagine-video/image-to-video",
             lambda img: {"prompt": MOTION_PROMPT, "image_url": img, "duration": 6,
                          "resolution": "720p", "aspect_ratio": "9:16"}),
    "kling26": ("fal-ai/kling-video/v2.6/pro/image-to-video",
                lambda img: {"prompt": MOTION_PROMPT, "start_image_url": img,
                             "duration": "5", "generate_audio": False}),
}


def main():
    load_dotenv()
    out = Path("output/ai_test"); out.mkdir(parents=True, exist_ok=True)

    print("Generating still image...")
    res = fal.run("fal-ai/flux/schnell", {"prompt": IMAGE_PROMPT, "image_size": "portrait_16_9",
                                          "num_inference_steps": 4})
    img_url = res["images"][0]["url"]
    fal.download(img_url, out / "still.jpg")
    print("  saved", out / "still.jpg")

    names = sys.argv[1:] or list(MODELS)

    def one(name):
        ep, build = MODELS[name]
        try:
            r = fal.run(ep, build(img_url), timeout=900)
            url = r["video"]["url"]
            p = fal.download(url, out / f"{name}.mp4")
            return name, str(p), None
        except Exception as e:
            return name, None, str(e)

    with ThreadPoolExecutor(len(names)) as ex:
        for name, path, err in ex.map(one, names):
            print(f"  {name}: {path or 'FAILED: ' + err}")


if __name__ == "__main__":
    main()
