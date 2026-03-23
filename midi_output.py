"""
MIDI output — three backends, tried in platform-preference order:

  1. macOS CoreMIDI  (ctypes → CoreMIDI.framework; macOS only)
     Preferred on macOS because python-rtmidi triggers a fatal GIL crash on
     Python 3.12+ when called after tkinter or PortAudio are initialised
     (CoreMIDI's notification thread calls PyEval_RestoreThread(NULL)).
  2. python-rtmidi   (cross-platform; used on Linux / fallback)
  3. Windows WinMM   (ctypes → winmm.dll; Windows only)

macOS setup: open Audio MIDI Setup → IAC Driver → enable "Device is online".
"""
from __future__ import annotations

import ctypes
import sys
from typing import List, Optional


class MidiError(Exception):
    pass


# ── macOS CoreMIDI (ctypes) ───────────────────────────────────────────────────
# All calls happen on the main thread — no Python callbacks registered.
# Client and output port are created once at module-import time.

_HAS_COREMIDI = False

if sys.platform == "darwin":
    try:
        from ctypes import (
            c_void_p as _cvp, c_uint32 as _cu32, c_uint64 as _cu64,
            c_uint16 as _cu16, c_ubyte as _cub, c_int32 as _ci32,
            c_bool as _cbool, byref as _byref, Structure as _Struct,
            create_string_buffer as _csb,
        )

        _cm  = ctypes.cdll.LoadLibrary(
            "/System/Library/Frameworks/CoreMIDI.framework/CoreMIDI")
        _cfr = ctypes.cdll.LoadLibrary(
            "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")

        # ── CF helpers ────────────────────────────────────────────────────────
        _kCFStringEncodingUTF8 = 0x08000100

        _cfr.CFStringCreateWithCString.restype = _cvp
        _cfr.CFStringGetCString.restype = _cbool
        _cfr.CFRelease.argtypes = [_cvp]

        def _cm_cfstr(s: str) -> "_cvp":   # type: ignore[name-defined]
            # Wrap in c_void_p so callers can pass it to CF/CoreMIDI functions
            # without argtypes — passing a raw Python int would truncate to 32-bit.
            v = _cfr.CFStringCreateWithCString(
                None, s.encode("utf-8"), _kCFStringEncodingUTF8)
            return _cvp(v)

        def _cm_cfstr_get(ref) -> str:
            # ref may be a c_void_p or an int
            val = ref.value if isinstance(ref, _cvp) else ref
            if not val:
                return ""
            buf = _csb(512)
            ok = _cfr.CFStringGetCString(_cvp(val), buf, 512, _kCFStringEncodingUTF8)
            return buf.value.decode("utf-8", errors="replace") if ok else ""

        # ── CoreMIDI function signatures ──────────────────────────────────────
        _cm.MIDIGetNumberOfDestinations.restype = _cu32
        _cm.MIDIGetDestination.restype         = _cvp
        _cm.MIDIObjectGetStringProperty.restype = _ci32
        _cm.MIDIClientCreate.restype           = _ci32
        _cm.MIDIOutputPortCreate.restype       = _ci32
        _cm.MIDISend.restype                   = _ci32

        # ── MIDIPacket / MIDIPacketList ───────────────────────────────────────
        # CoreMIDI's MIDIPacket is __attribute__((packed)) in <CoreMIDI/MIDIServices.h>.
        # Without _pack_=1 ctypes adds trailing padding (272 vs 266 bytes) and
        # MIDIPacketList gains 4 bytes of padding before packet[0] (offset 8 vs 4).
        # CoreMIDI then reads length=0 at offset 12 and silently discards every packet.
        class _MIDIPacket(_Struct):
            _pack_ = 1   # matches __attribute__((packed)) in CoreMIDI headers
            _fields_ = [
                ("timeStamp", _cu64),        # offset  0
                ("length",    _cu16),        # offset  8
                ("data",      _cub * 256),   # offset 10
            ]
        # sizeof(_MIDIPacket)==266; in _MIDIPacketList packet[0] starts at offset 4.

        class _MIDIPacketList(_Struct):
            _fields_ = [
                ("numPackets", _cu32),
                ("packet",     _MIDIPacket * 1),
            ]

        # ── Create MIDI client and output port at module level ─────────────────
        _cm_client = _cvp(0)
        _n = _cm_cfstr("LTCtoMIDI")
        _err = _cm.MIDIClientCreate(_n, None, None, _byref(_cm_client))
        _cfr.CFRelease(_n)
        if _err != 0 or not _cm_client:
            raise RuntimeError(f"MIDIClientCreate failed: {_err}")

        _cm_port = _cvp(0)
        _pn = _cm_cfstr("LTCtoMIDI-Out")
        _err = _cm.MIDIOutputPortCreate(_cm_client, _pn, _byref(_cm_port))
        _cfr.CFRelease(_pn)
        if _err != 0 or not _cm_port:
            raise RuntimeError(f"MIDIOutputPortCreate failed: {_err}")

        # ── CoreMIDI helper functions ─────────────────────────────────────────

        def _coremidi_list_ports() -> List[str]:
            n = _cm.MIDIGetNumberOfDestinations()
            result: List[str] = []
            prop = _cm_cfstr("name")   # c_void_p
            for i in range(n):
                ep = _cvp(_cm.MIDIGetDestination(i))   # wrap int → c_void_p
                name_ref = _cvp(0)
                _cm.MIDIObjectGetStringProperty(ep, prop, _byref(name_ref))
                result.append(_cm_cfstr_get(name_ref))
                if name_ref.value:
                    _cfr.CFRelease(name_ref)
            _cfr.CFRelease(prop)
            return result

        def _coremidi_get_dest(index: int) -> "_cvp":   # type: ignore[name-defined]
            # Wrap in c_void_p so the value is passed correctly as a 64-bit pointer.
            return _cvp(_cm.MIDIGetDestination(index))

        def _coremidi_send(dest: "_cvp", data: bytes) -> None:   # type: ignore[name-defined]
            pkt = _MIDIPacketList()
            pkt.numPackets = 1
            pkt.packet[0].timeStamp = 0   # 0 = send immediately
            pkt.packet[0].length = min(len(data), 256)
            for i, b in enumerate(data[:256]):
                pkt.packet[0].data[i] = b
            err = _cm.MIDISend(_cm_port, dest, _byref(pkt))
            if err != 0:
                raise MidiError(f"MIDISend failed — OSStatus={err:#010x}")

        _HAS_COREMIDI = True

    except Exception:
        _HAS_COREMIDI = False


# ── python-rtmidi ─────────────────────────────────────────────────────────────

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

    Backend priority:
      macOS  → CoreMIDI (ctypes, no GIL issues)
      other  → python-rtmidi, then Windows WinMM

    All methods must be called from the main thread.
    """

    def __init__(self) -> None:
        self._backend: Optional[str] = None   # "coremidi" | "rtmidi" | "winmm"
        self._coremidi_dest = None             # c_void_p endpoint ref (macOS)
        self._rtmidi_out = None
        self._winmm_handle: Optional[ctypes.c_void_p] = None
        self._port_name: Optional[str] = None

    # ── port enumeration ──────────────────────────────────────────────────────

    @staticmethod
    def list_ports() -> List[str]:
        """Return available MIDI output port names."""
        if _HAS_COREMIDI:
            try:
                return _coremidi_list_ports()
            except Exception:
                pass
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
        if _HAS_COREMIDI:
            return "CoreMIDI (ctypes)"
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

        if _HAS_COREMIDI:
            self._coremidi_dest = _coremidi_get_dest(port_index)
            self._backend = "coremidi"
        elif _HAS_RTMIDI:
            out = _rtmidi.MidiOut()     # type: ignore[union-attr]
            out.open_port(port_index)
            self._rtmidi_out = out
            self._backend = "rtmidi"
        elif _winmm is not None:
            self._winmm_handle = _winmm_open(port_index)
            self._backend = "winmm"
        else:
            raise MidiError(
                "No MIDI backend available.\n"
                "On macOS: CoreMIDI should be built-in — check system integrity.\n"
                "On Linux: install python-rtmidi  (pip install python-rtmidi).\n"
                "On Windows: WinMM should be built-in."
            )
        self._port_name = ports[port_index]

    def close(self) -> None:
        if self._backend == "coremidi":
            self._coremidi_dest = None
        elif self._backend == "rtmidi" and self._rtmidi_out is not None:
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
        if self._backend == "coremidi":
            _coremidi_send(self._coremidi_dest, bytes([status, prog]))
        elif self._backend == "rtmidi":
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
        if self._backend == "coremidi":
            try:
                _coremidi_send(self._coremidi_dest, bytes([status, 123, 0]))
            except Exception:
                pass
        elif self._backend == "rtmidi" and self._rtmidi_out:
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
        if self._backend == "coremidi":
            return self._coremidi_dest is not None
        if self._backend == "rtmidi":
            return self._rtmidi_out is not None
        if self._backend == "winmm":
            return self._winmm_handle is not None and self._winmm_handle.value != 0
        return False

    @property
    def port_name(self) -> Optional[str]:
        return self._port_name
