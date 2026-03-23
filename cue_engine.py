"""
CueEngine — frame-accurate cue matching and MIDI firing.

All methods must be called from the main thread only (same thread that polls
the timecode queue and owns MidiOutput).
"""
from __future__ import annotations

from typing import Callable, List, Optional

from ltc_decoder import Timecode
from midi_output import MidiOutput, MidiError
from models import Cue, CueList


class CueEngine:
    """
    Receives Timecode objects one at a time, matches them against a CueList,
    and fires MIDI Program Changes when a match is found.

    Fired cues are marked so they only trigger once per playback pass.
    When TC jumps backwards the engine resets fired flags for future cues.
    """

    def __init__(self, midi_output: MidiOutput, tolerance_frames: int = 1) -> None:
        self._midi = midi_output
        self.tolerance_frames = tolerance_frames
        self._cue_list: CueList = CueList()
        self._fps: float = 25.0
        self._last_frame: Optional[int] = None

        # Optional callbacks (called from main thread)
        self.on_cue_fired:  Optional[Callable[[Cue], None]] = None
        self.on_midi_error: Optional[Callable[[str], None]] = None

    # ── configuration ─────────────────────────────────────────────────────────

    def load_cue_list(self, cue_list: CueList) -> None:
        self._cue_list = cue_list
        self._cue_list.reset_fired_flags()
        self._last_frame = None

    def set_fps(self, fps: float) -> None:
        self._fps = fps

    def reset(self) -> None:
        """Reset all fired flags (call on stop/rewind)."""
        self._cue_list.reset_fired_flags()
        self._last_frame = None

    # ── main processing entry point ───────────────────────────────────────────

    def on_timecode(self, tc: Timecode) -> List[Cue]:
        """
        Process one incoming Timecode.
        Returns the list of cues fired during this call (may be empty).
        Must be called from the main thread.
        """
        fps = tc.fps if tc.fps else self._fps
        current_frame = tc.to_frame_number()

        self._handle_backwards_jump(current_frame, fps)
        self._last_frame = current_frame

        fired: List[Cue] = []
        for cue in self._cue_list.cues:
            if not cue.enabled or cue.fired:
                continue
            cue_frame = cue.timecode_as_frames(fps)
            if cue_frame < 0:
                continue
            if abs(current_frame - cue_frame) <= self.tolerance_frames:
                self._fire(cue)
                fired.append(cue)

        return fired

    # ── internal ──────────────────────────────────────────────────────────────

    def _handle_backwards_jump(self, current_frame: int, fps: float) -> None:
        """
        If TC jumped backwards by more than 1 second, reset fired flags for
        all cues whose timecode is >= current position.
        """
        if self._last_frame is None:
            return
        jump = self._last_frame - current_frame
        if jump > round(fps):  # more than 1 second backwards
            for cue in self._cue_list.cues:
                cue_frame = cue.timecode_as_frames(fps)
                if cue_frame >= current_frame:
                    cue.fired = False

    def _fire(self, cue: Cue) -> None:
        cue.fired = True
        try:
            if self._midi.is_open:
                self._midi.send_program_change(cue.channel, cue.program)
        except MidiError as exc:
            if self.on_midi_error:
                self.on_midi_error(str(exc))

        if self.on_cue_fired:
            self.on_cue_fired(cue)
