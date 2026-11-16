#!/usr/bin/env python3
"""poems.txt -> animated video + matching music -> Instagram Story.

  python main.py                 # render next unposted poem only (preview)
  python main.py --post          # render and post it as a story
  python main.py --index 1       # pick a specific poem (0-based)
  python main.py --mood sad      # override mood detection
"""
import argparse
import json
from pathlib import Path

from dotenv import load_dotenv

from poetry_bot.mood import MOODS, detect_mood
from poetry_bot.music import pick_track
from poetry_bot.poems import load_poems
from poetry_bot.video import render, story_duration

STATE = Path("posted.json")


def main():
    load_dotenv()
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default="poems.txt")
    ap.add_argument("--index", type=int, help="poem index (default: next unposted)")
    ap.add_argument("--mood", choices=MOODS)
    ap.add_argument("--music", choices=["openverse", "synth"], default="openverse",
                    help="music source (default: Creative Commons track from Openverse)")
    ap.add_argument("--bg", choices=["ai", "gradient"], default="ai",
                    help="background: AI-animated clip via fal.ai (costs ~$0.60) or free gradient")
    ap.add_argument("--format", choices=["story", "reel"], default="story",
                    help="publish as an Instagram Story (24h) or a Reel (permanent)")
    ap.add_argument("--caption", default=None, help="reel caption (default: title + music credit)")
    ap.add_argument("--post", action="store_true", help="actually publish to Instagram")
    ap.add_argument("--duration", type=float)
    args = ap.parse_args()

    poems = load_poems(args.file)
    if not poems:
        raise SystemExit(f"No poems found in {args.file}")
    posted = set(json.loads(STATE.read_text())) if STATE.exists() else set()

    if args.index is not None:
        idx = args.index
    else:
        idx = next((i for i in range(len(poems)) if i not in posted), None)
        if idx is None:
            raise SystemExit("All poems already posted (delete posted.json to reset).")
    poem = poems[idx]

    mood = MOODS[args.mood] if args.mood else detect_mood(poem.text)
    print(f"Poem #{idx}: {poem.title or poem.lines[0]!r}  mood={mood.name}")

    out = Path("output"); out.mkdir(exist_ok=True)
    video = out / f"poem_{idx}.mp4"
    duration = args.duration or story_duration(poem)
    audio, credit = pick_track(mood, duration, out / f"poem_{idx}.wav", source=args.music, seed=idx,
                              hints=poem.music_hints)
    bg_clips = None
    if args.bg == "ai":
        try:
            from poetry_bot.ai_bg import generate
            bg_clips = generate(poem, mood, idx, out / "ai")
        except Exception as e:
            print(f"  AI background failed ({e}); falling back to gradient")
    render(poem, mood, audio, video, duration=duration, credit=credit, bg_clips=bg_clips)
    print(f"Saved {video}")

    if not args.post:
        print("Preview only. Re-run with --post to publish.")
        return
    from poetry_bot.publish import post_reel, post_story, upload_public
    print("Uploading video...")
    url = upload_public(video)
    print(f"Publishing {args.format}...")
    if args.format == "reel":
        caption = args.caption or "\n\n".join(x for x in (poem.title, credit) if x)
        media_id = post_reel(url, caption)
    else:
        media_id = post_story(url)
    posted.add(idx)
    STATE.write_text(json.dumps(sorted(posted)))
    print(f"Posted! media id {media_id}")


if __name__ == "__main__":
    main()
