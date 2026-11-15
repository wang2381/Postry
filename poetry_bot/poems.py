"""Load poems from a txt file.

Format: poems separated by a line containing only `---`.
An optional first line `Title: ...` sets the title.
"""
from dataclasses import dataclass
from pathlib import Path
import re


@dataclass
class Poem:
    title: str
    lines: list[str]

    @property
    def text(self) -> str:
        return "\n".join(self.lines)


def load_poems(path: str | Path) -> list[Poem]:
    raw = Path(path).read_text(encoding="utf-8")
    poems = []
    for block in re.split(r"^\s*---+\s*$", raw, flags=re.MULTILINE):
        lines = [l.rstrip() for l in block.strip().splitlines()]
        if not lines:
            continue
        title = ""
        if lines[0].lower().startswith("title:"):
            title = lines.pop(0).split(":", 1)[1].strip()
        lines = [l for l in lines if l.strip()]
        if lines:
            poems.append(Poem(title, lines))
    return poems
