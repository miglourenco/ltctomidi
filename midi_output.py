"""
MIDI output — two backends, tried in order:

  1. python-rtmidi  (cross-platform; required on macOS/Linux)
  2. Windows WinMM  (ctypes → winmm.dll; zero extra dependencies, Windows only)

On macOS/Linux python-rtmidi is the only backend.  Install with:
    pip install python-rtmidi
On macOS it uses CoreMIDI under the hood — pair it with the built-in IAC Driver
(Audio MIDI Setup → IAC Driver → enable).
"""
from __future__ import annotations

import ctypes
import sys
from typing import List, Optional


class MidiError(Exception):
    pass


# ── rtmidi availability ───────────────────────────────────────────────────────

try:
    import rtmidi as _rtmidi
    _HAS_RTMIDI = True
except ImportError:
    _HAS_RTMIDI = False


# ── Windows WinMM (Windows only) ──────────────────────────────────────────────

_winmm = None  # ctypes.WinDLL handle, or None

if sys.platform == "win32":
    import ctypes.wintypes as _wintypes

    try:
        _winmm = ctypes.WinDLL("winmm")   # type: ignore[assignment]
    except OSError:
        pass

    class _MIDIOUTCAPSA(ctypes.Structure):
        _fields_ = [
            ("wMid",            _wintypes.WORD),
            ("wPid",            _wintypes.WORD),
            ("vDriverVersion",  ctypes.c_uint32),
            ("szPname",         ctypes.c_char * 32),
            ("wTechnology",     _wintypes.WORD),
            ("wVoices",         _wintypes.WORD),
            ("wNotes",          _wintypes.WORD),
            ("wChannelMask",    _wintypes.WORD),
            ("dwSupport",       _wintypes.DWORD),
        ]

    def _winmm_list_ports() -> List[str]:
        assert _winmm is not None
        n: int = _winmm.midiOutGetNumDevs()
        ports: List[str] = []
        for i in range(n):
            caps = _MIDIOUTCAPSA()
            res = _winmm.midiOutGetDevCapsA(
                ctypes.c_uint(i),
                ctypes.byref(caps),
                ctypes.c_uint(ctypes.sizeof(caps)),
            )
            if res == 0:  # MMSYSERR_NOERROR
                ports.append(caps.szPname.decode("mbcs", errors="replace"))
        return ports

    def _winmm_open(port_index: int) -> ctypes.c_void_p:
        assert _winmm is not None
        handle = ctypes.c_void_p(0)
        res = _winmm.midiOutOpen(
            ctypes.byref(handle),
            ctypes.c_uint(port_index),
            ctypes.c_size_t(0),
            ctypes.c_size_t(0),
            ctypes.c_uint32(0),
        )
        if res != 0:
            raise MidiError(f"midiOutOpen failed — MMRESULT={res:#06x}")
        return handle

    def _winmm_short_msg(handle: ctypes.c_void_p, msg: int) -> None:
        assert _winmm is not None
        res = _winmm.midiOutShortMsg(handle, ctypes.c_uint32(msg))
        if res != 0:
            raise MidiError(f"midiOutShortMsg failed — MMRESULT={res:#06x}")

    def _winmm_close(handle: ctypes.c_void_p) -> None:
        if _winmm is not None and handle:
            try:
                _winmm.midiOutClose(handle)
            except Exception:
                pass


# ── MidiOutput ────────────────────────────────────────────────────────────────

class MidiOutput:
    """
    Sends MIDI Program Change messages.
    Uses python-rtmidi when available; falls back to Windows WinMM via ctypes.
    All methods must be called from the main thread.
    """

    def __init__(self) -> None:
        self._backend: Optional[str] = None        # "rtmidi" | "winmm"
        self._rtmidi_out = None
        self._winmm_handle: Optional[ctypes.c_void_p] = None
        self._port_name: Optional[str] = None

    # ── port enumeration ──────────────────────────────────────────────────────

    @staticmethod
    def list_ports() -> List[str]:
        """Return available MIDI output port names."""
        if _HAS_RTMIDI:
            try:
                m = _rtmidi.MidiOut()   # type: ignore[union-attr]
                ports = m.get_ports()
                del m
                return ports
            except Exception:
                pass
        if _winmm is not None:
            try:
                return _winmm_list_ports()
            except Exception:
                pass
        return []

    @staticmethod
    def backend_name() -> str:
        """Human-readable name of the active MIDI backend."""
        if _HAS_RTMIDI:
            return "rtmidi"
        if _winmm is not None:
            return "WinMM (ctypes)"
        return "none"

    # ── lifecycle ─────────────────────────────────────────────────────────────

    def open(self, port_index: int) -> None:
        self.close()
        ports = self.list_ports()
        if not ports:
            raise MidiError("No MIDI output ports found")
        if port_index >= len(ports):
            raise MidiError(
                f"MIDI port index {port_index} out of range "
                f"({len(ports)} port(s) available)"
            )

        if _HAS_RTMIDI:
            out = _rtmidi.MidiOut()     # type: ignore[union-attr]
            out.open_port(port_index)
            self._rtmidi_out = out
            self._backend = "rtmidi"
        elif _winmm is not None:
            self._winmm_handle = _winmm_open(port_index)
            self._backend = "winmm"
        else:
            if sys.platform == "darwin":
                raise MidiError(
                    "python-rtmidi is required on macOS.\n"
                    "Install it with:  pip install python-rtmidi"
                )
            raise MidiError(
                "No MIDI backend available.\n"
                "Install python-rtmidi or run on Windows (WinMM is built-in)."
            )
        self._port_name = ports[port_index]

    def close(self) -> None:
        if self._backend == "rtmidi" and self._rtmidi_out is not None:
            try:
                self._rtmidi_out.close_port()
            except Exception:
                pass
            self._rtmidi_out = None
        elif self._backend == "winmm" and self._winmm_handle is not None:
            _winmm_close(self._winmm_handle)
            self._winmm_handle = None
        self._backend = None
        self._port_name = None

    # ── messaging ─────────────────────────────────────────────────────────────

    def send_program_change(self, channel: int, program: int) -> None:
        """
        Send a MIDI Program Change.
        channel: 1–16  (human-readable)
        program: 0–127
        """
        if not self.is_open:
            raise MidiError("MIDI port not open")
        status = 0xC0 | ((channel - 1) & 0x0F)
        prog   = program & 0x7F
        if self._backend == "rtmidi":
            try:
                self._rtmidi_out.send_message([status, prog])
            except Exception as exc:
                raise MidiError(f"Send failed: {exc}") from exc
        elif self._backend == "winmm":
            _winmm_short_msg(self._winmm_handle, status | (prog << 8))

    def send_all_notes_off(self, channel: int = 1) -> None:
        """CC 123 — all notes off, useful for cleanup."""
        if not self.is_open:
            return
        status = 0xB0 | ((channel - 1) & 0x0F)
        if self._backend == "rtmidi" and self._rtmidi_out:
            try:
                self._rtmidi_out.send_message([status, 123, 0])
            except Exception:
                pass
        elif self._backend == "winmm" and self._winmm_handle:
            try:
                _winmm_short_msg(self._winmm_handle, status | (123 << 8) | (0 << 16))
            except Exception:
                pass

    # ── status ────────────────────────────────────────────────────────────────

    @property
    def is_open(self) -> bool:
        if self._backend == "rtmidi":
            return self._rtmidi_out is not None
        if self._backend == "winmm":
            return self._winmm_handle is not None and self._winmm_handle.value != 0
        return False

    @property
    def port_name(self) -> Optional[str]:
        return self._port_name
