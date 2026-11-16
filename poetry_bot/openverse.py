"""Find a Creative Commons track on Openverse that matches a mood.

Only licenses that are safe for a video with music added are used:
CC0, public domain, and CC-BY (needs credit; we print it on the video).
NC / ND / SA licenses are excluded on purpose.
"""
from dataclasses import dataclass
from pathlib import Path
import random
import unicodedata

import requests

API = "https://api.openverse.org/v1/audio/"
LICENSES = "cc0,pdm,by"
MAX_BYTES = 30 * 1024 * 1024
# Openverse search is AND-based, so multi-word queries return nothing: use single words.
MOOD_QUERIES = {
    "calm":     ["calm", "peaceful", "ambient", "serene", "relaxing"],
    "sad":      ["sad", "melancholy", "melancholic", "sorrow", "nostalgic"],
    "romantic": ["romantic", "love", "tender", "romance"],
    "joyful":   ["happy", "joyful", "uplifting", "cheerful", "sunny"],
    "dark":     ["dark", "mysterious", "haunting", "eerie", "brooding"],
    "hopeful":  ["hopeful", "inspiring", "uplifting", "dawn", "cinematic"],
}
LICENSE_NAMES = {"cc0": "CC0", "pdm": "Public Domain", "by": "CC BY"}
SKIP_WORDS = ("vocal", "vocals", "song", "sings", "lyrics", "remix")  # prefer instrumentals


@dataclass
class Track:
    path: Path
    title: str
    creator: str
    license: str
    source_url: str

    @property
    def credit(self) -> str:
        return f"Music: {self.title} — {self.creator} ({self.license})"


def _latin(text: str) -> bool:
    """True if every letter is Latin script (so titles/credits stay readable in English)."""
    return all(unicodedata.name(c, "").startswith("LATIN") for c in text if c.isalpha())


def _tags(x: dict) -> set[str]:
    return {(t.get("name") or "").lower() for t in (x.get("tags") or [])}


def _usable(x: dict) -> bool:
    """Instrumental only (no lyrics in any language), Latin-script title and creator."""
    tags = _tags(x)
    return ("instrumental" in tags and "vocal" not in tags
            and _latin(x.get("title") or "") and _latin(x.get("creator") or ""))


def _search(queries, min_seconds: float, seen: set) -> list[dict]:
    found = []
    for q in queries:
        try:
            r = requests.get(API, params={"q": q, "license": LICENSES, "category": "music",
                                          "page_size": 20}, timeout=30)
            r.raise_for_status()
        except requests.RequestException as e:
            print(f"  openverse search '{q}' failed: {e}")
            continue
        for x in r.json().get("results", []):
            title = (x.get("title") or "").lower()
            if (x["id"] in seen or not x.get("url") or (x.get("duration") or 0) < min_seconds * 1000
                    or any(w in title for w in SKIP_WORDS) or not _usable(x)):
                continue
            seen.add(x["id"])
            found.append(x)
    return found


def fetch_track(mood_name: str, min_seconds: float, cache_dir: Path, seed: int = 0,
                hints=()) -> Track | None:
    """Return a downloaded track, or None. Tracks matching `hints` (words from the poem's
    Music: line) are preferred over generic mood matches."""
    seen: set = set()
    rng = random.Random(seed)
    cands = _search(list(hints) + MOOD_QUERIES.get(mood_name, ["ambient"]), min_seconds, seen)
    # rank by how many of the poem's hint words / the mood appear in the track's tags or title
    wanted = {w.lower() for w in hints} | {mood_name}
    rng.shuffle(cands)  # random order among equally good matches
    cands.sort(key=lambda x: -len(wanted & (_tags(x) | set((x.get("title") or "").lower().split()))))
    cache_dir.mkdir(parents=True, exist_ok=True)
    for x in cands[:5]:
        dest = cache_dir / f"{x['id']}.mp3"
        try:
            if not dest.exists():
                with requests.get(x["url"], stream=True, timeout=60) as r:
                    r.raise_for_status()
                    size = int(r.headers.get("content-length") or 0)
                    if size > MAX_BYTES or "audio" not in r.headers.get("content-type", ""):
                        continue
                    with open(dest, "wb") as f:
                        for chunk in r.iter_content(1 << 16):
                            f.write(chunk)
        except requests.RequestException as e:
            print(f"  download failed ({e}); trying next")
            dest.unlink(missing_ok=True)
            continue
        lic = LICENSE_NAMES.get(x["license"], x["license"].upper())
        return Track(dest, x["title"].strip(), (x.get("creator") or "unknown").strip(), lic,
                     x.get("foreign_landing_url") or x["url"])
    return None
