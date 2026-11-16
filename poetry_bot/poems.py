"""Load poems from a txt file.

Format: poems separated by a line containing only `---`.
Optional header lines inside a poem:
    Title: ...           shown at the top
    Music: a, b, c       search words to prefer when picking music
Blank lines split a poem into stanzas. A stanza may start with
    Scene: ...           describes the background scene for that stanza (not shown)
"""
from dataclasses import dataclass, field
from pathlib import Path
import re


@dataclass
class Poem:
    title: str
    lines: list[str]
    stanzas: list[list[str]] = field(default_factory=list)
    scenes: list[str] = field(default_factory=list)       # one hint per stanza ("" if none)
    music_hints: list[str] = field(default_factory=list)

    def __post_init__(self):
        if not self.stanzas:
            self.stanzas = [self.lines]
            self.scenes = [""]

    @property
    def text(self) -> str:
        return "\n".join(self.lines)


def _parse(block: str) -> Poem | None:
    title, hints = "", []
    stanzas, scenes = [], []
    cur, cur_scene = [], ""

    def flush():
        nonlocal cur, cur_scene
        if cur:
            stanzas.append(cur)
            scenes.append(cur_scene)
        cur, cur_scene = [], (cur_scene if not cur else "")

    for raw in block.strip().splitlines():
        line = raw.strip()
        low = line.lower()
        if not line:
            flush()
        elif low.startswith("title:") and not stanzas and not cur:
            title = line.split(":", 1)[1].strip()
        elif low.startswith("music:") and not stanzas and not cur:
            hints = [w.strip().lower() for w in re.split(r"[,;]", line.split(":", 1)[1]) if w.strip()]
        elif low.startswith("scene:"):
            if cur:           # scene line in the middle: starts a new stanza
                flush()
            cur_scene = line.split(":", 1)[1].strip()
        else:
            cur.append(line)
    flush()
    if not stanzas:
        return None
    return Poem(title, [l for s in stanzas for l in s], stanzas, scenes, hints)


def load_poems(path: str | Path) -> list[Poem]:
    raw = Path(path).read_text(encoding="utf-8")
    poems = (_parse(b) for b in re.split(r"^\s*---+\s*$", raw, flags=re.MULTILINE))
    return [p for p in poems if p]
