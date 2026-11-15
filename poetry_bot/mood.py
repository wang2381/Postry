"""Detect the mood of a poem (keyword based, English + Chinese) and map it to
a visual palette and musical settings."""
from dataclasses import dataclass

MOOD_KEYWORDS = {
    "sad": "tears cry rain lonely alone grief loss goodbye gone ache sorrow miss weep "
           "泪 雨 孤独 寂寞 离别 悲 愁 思念 失去",
    "romantic": "love kiss heart lover darling desire embrace beloved rose 爱 吻 心 恋 玫瑰 拥抱",
    "joyful": "joy laugh dance sun smile bright happy sing spring light bloom 笑 欢 阳光 春 歌 快乐",
    "dark": "dark night shadow death fear storm cold void black ghost grave 夜 黑暗 影 死 恐惧 冷 风暴",
    "calm": "sea wave tide moon quiet gentle soft whisper river sleep morning dawn peace "
            "海 浪 月 静 轻 河 梦 晨 安宁",
    "hopeful": "hope dawn ember brave rise glow begin new grow believe 希望 黎明 勇敢 升起 新 成长",
}


@dataclass(frozen=True)
class Mood:
    name: str
    colors: tuple          # 3 RGB colors for the animated gradient
    root_hz: float         # tonic of the music
    scale: tuple           # semitone offsets used for the chord/arpeggio
    bpm: int
    brightness: float


MOODS = {
    "sad":      Mood("sad", ((18, 28, 60), (55, 70, 120), (110, 120, 160)), 220.00, (0, 3, 7, 10, 14), 54, 0.8),
    "romantic": Mood("romantic", ((70, 15, 45), (170, 50, 90), (250, 160, 150)), 261.63, (0, 4, 7, 11, 14), 62, 1.0),
    "joyful":   Mood("joyful", ((255, 140, 60), (255, 200, 90), (250, 110, 130)), 293.66, (0, 4, 7, 9, 12), 92, 1.1),
    "dark":     Mood("dark", ((5, 5, 12), (30, 15, 50), (70, 30, 80)), 164.81, (0, 3, 6, 10, 12), 48, 0.7),
    "calm":     Mood("calm", ((10, 50, 90), (30, 120, 150), (140, 210, 210)), 246.94, (0, 2, 7, 9, 14), 56, 0.95),
    "hopeful":  Mood("hopeful", ((25, 30, 80), (200, 90, 90), (255, 200, 120)), 261.63, (0, 2, 4, 7, 11), 70, 1.0),
}


def detect_mood(text: str) -> Mood:
    t = text.lower()
    scores = {m: sum(t.count(k) for k in kws.split()) for m, kws in MOOD_KEYWORDS.items()}
    best = max(scores, key=scores.get)
    return MOODS[best if scores[best] > 0 else "calm"]
