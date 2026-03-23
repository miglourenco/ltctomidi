"""
Data models: Cue, CueList, AppSettings.
No I/O side effects at import time.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict
from typing import List, Optional


# ── Cue ───────────────────────────────────────────────────────────────────────

@dataclass
class Cue:
    id: int
    label: str
    timecode: str          # canonical "HH:MM:SS:FF"
    program: int           # MIDI Program Change 0-127
    channel: int           # MIDI channel 1-16
    enabled: bool = True
    fired: bool = field(default=False, repr=False, compare=False)

    # ---- serialisation -------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "label": self.label,
            "timecode": self.timecode,
            "program": self.program,
            "channel": self.channel,
            "enabled": self.enabled,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Cue":
        return cls(
            id=int(d.get("id", 0)),
            label=str(d.get("label", "")),
            timecode=str(d.get("timecode", "00:00:00:00")),
            program=int(d.get("program", d.get("program_change", 0))),
            channel=int(d.get("channel", d.get("midi_channel", 1))),
            enabled=bool(d.get("enabled", True)),
        )

    # ---- helpers -------------------------------------------------------------

    def timecode_as_frames(self, fps: float = 25.0) -> int:
        """Convert HH:MM:SS:FF to absolute frame count."""
        try:
            parts = self.timecode.replace(";", ":").split(":")
            h, m, s, f = int(parts[0]), int(parts[1]), int(parts[2]), int(parts[3])
            return (h * 3600 + m * 60 + s) * round(fps) + f
        except Exception:
            return -1


# ── CueList ───────────────────────────────────────────────────────────────────

class CueList:
    def __init__(self) -> None:
        self.cues: List[Cue] = []
        self._next_id: int = 1

    # ---- I/O -----------------------------------------------------------------

    @classmethod
    def load(cls, path: str) -> "CueList":
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        cl = cls()
        cl.cues = [Cue.from_dict(d) for d in data]
        cl._next_id = max((c.id for c in cl.cues), default=0) + 1
        return cl

    def save(self, path: str) -> None:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump([c.to_dict() for c in self.cues], fh, indent=2, ensure_ascii=False)

    # ---- mutation ------------------------------------------------------------

    def add(self, label: str, timecode: str, program: int, channel: int) -> Cue:
        cue = Cue(id=self._next_id, label=label, timecode=timecode,
                  program=program, channel=channel)
        self._next_id += 1
        self.cues.append(cue)
        return cue

    def replace(self, cue_id: int, **kwargs) -> bool:
        cue = self.by_id(cue_id)
        if cue is None:
            return False
        for k, v in kwargs.items():
            if hasattr(cue, k):
                setattr(cue, k, v)
        return True

    def remove(self, cue_id: int) -> bool:
        before = len(self.cues)
        self.cues = [c for c in self.cues if c.id != cue_id]
        return len(self.cues) < before

    def move_up(self, cue_id: int) -> bool:
        idx = self._index(cue_id)
        if idx is None or idx == 0:
            return False
        self.cues[idx], self.cues[idx - 1] = self.cues[idx - 1], self.cues[idx]
        return True

    def move_down(self, cue_id: int) -> bool:
        idx = self._index(cue_id)
        if idx is None or idx >= len(self.cues) - 1:
            return False
        self.cues[idx], self.cues[idx + 1] = self.cues[idx + 1], self.cues[idx]
        return True

    def reset_fired_flags(self) -> None:
        for c in self.cues:
            c.fired = False

    # ---- queries -------------------------------------------------------------

    def by_id(self, cue_id: int) -> Optional[Cue]:
        return next((c for c in self.cues if c.id == cue_id), None)

    def _index(self, cue_id: int) -> Optional[int]:
        return next((i for i, c in enumerate(self.cues) if c.id == cue_id), None)

    def __len__(self) -> int:
        return len(self.cues)


# ── AppSettings ───────────────────────────────────────────────────────────────

_APPDATA = os.environ.get("APPDATA", os.path.expanduser("~"))
_SETTINGS_DIR = os.path.join(_APPDATA, "LTCtoMIDI")
SETTINGS_PATH = os.path.join(_SETTINGS_DIR, "settings.json")


@dataclass
class AppSettings:
    audio_device: str = ""
    audio_channel: int = 1       # 1-based for UI; convert to 0-based when using
    sample_rate: int = 48000
    midi_port: str = ""
    tolerance_frames: int = 1
    last_cue_file: str = ""

    @classmethod
    def load(cls) -> "AppSettings":
        try:
            with open(SETTINGS_PATH, "r", encoding="utf-8") as fh:
                d = json.load(fh)
            return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})
        except Exception:
            return cls()

    def save(self) -> None:
        os.makedirs(_SETTINGS_DIR, exist_ok=True)
        with open(SETTINGS_PATH, "w", encoding="utf-8") as fh:
            json.dump(asdict(self), fh, indent=2)
