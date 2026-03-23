"""
Audio capture using sounddevice (supports ASIO on Windows).

The audio callback runs in a PortAudio real-time thread.
Decoded Timecodes are placed on a queue.Queue for the main thread to consume.
"""
from __future__ import annotations

import queue
from typing import Any, Dict, List, Optional

import numpy as np

from ltc_decoder import LTCDecoder, Timecode


# ── Device enumeration ────────────────────────────────────────────────────────

def list_audio_devices() -> List[Dict[str, Any]]:
    """
    Return all input-capable audio devices.
    Each entry: {"index", "name", "channels", "hostapi", "default_samplerate"}
    """
    try:
        import sounddevice as sd
        result = []
        hostapis = sd.query_hostapis()
        for i, dev in enumerate(sd.query_devices()):
            if dev["max_input_channels"] > 0:
                api_name = hostapis[dev["hostapi"]]["name"] if dev["hostapi"] < len(hostapis) else ""
                result.append({
                    "index":            i,
                    "name":             dev["name"],
                    "channels":         dev["max_input_channels"],
                    "hostapi":          api_name,
                    "default_samplerate": int(dev["default_samplerate"]),
                })
        return result
    except Exception:
        return []


def list_asio_devices() -> List[Dict[str, Any]]:
    """Return only ASIO input devices."""
    return [d for d in list_audio_devices() if "asio" in d["hostapi"].lower()]


# ── AudioCapture ──────────────────────────────────────────────────────────────

class AudioCapture:
    """
    Opens a sounddevice InputStream, feeds audio to LTCDecoder,
    and puts decoded Timecodes on tc_queue.

    All public methods must be called from the main thread only.
    The audio callback runs in a PortAudio thread.
    """

    def __init__(self, tc_queue: "queue.Queue[Timecode]") -> None:
        self._tc_queue = tc_queue
        self._decoder: Optional[LTCDecoder] = None
        self._stream = None
        self._device_index: Optional[int] = None
        self._channel: int = 0          # 0-based
        self._sample_rate: int = 48000
        self._running: bool = False

    # ── configuration ─────────────────────────────────────────────────────────

    def configure(self, device_index: int, channel: int, sample_rate: int = 48000) -> None:
        """
        Set capture parameters. Must be called before start().
        channel: 0-based index into the device's input channels.
        """
        self._device_index = device_index
        self._channel = channel
        self._sample_rate = sample_rate

    # ── lifecycle ─────────────────────────────────────────────────────────────

    def start(self) -> None:
        if self._running:
            return
        if self._device_index is None:
            raise RuntimeError("Call configure() before start()")

        import sounddevice as sd

        dev_info = sd.query_devices(self._device_index)
        n_ch = int(dev_info["max_input_channels"])

        if self._channel >= n_ch:
            raise ValueError(
                f"Channel {self._channel + 1} not available — "
                f"device '{dev_info['name']}' has {n_ch} input channel(s)"
            )

        self._decoder = LTCDecoder(self._sample_rate)
        self._decoder.on_timecode = self._on_timecode

        self._stream = sd.InputStream(
            device=self._device_index,
            channels=n_ch,
            samplerate=self._sample_rate,
            blocksize=512,
            dtype="float32",
            callback=self._audio_callback,
            latency="low",
        )
        self._running = True
        self._stream.start()

        # For ASIO devices the driver controls the sample rate; the rate we
        # requested may differ from what the stream actually opened at.
        # Re-initialise the decoder with the real rate if needed.
        actual_sr = int(self._stream.samplerate)
        if actual_sr != self._sample_rate:
            self._sample_rate = actual_sr
            self._decoder = LTCDecoder(actual_sr)
            self._decoder.on_timecode = self._on_timecode

    def stop(self) -> None:
        self._running = False
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None
        self._decoder = None

    # ── status ────────────────────────────────────────────────────────────────

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def actual_sample_rate(self) -> Optional[int]:
        """The sample rate the stream actually opened at (may differ from configured rate for ASIO)."""
        if self._stream is not None:
            return int(self._stream.samplerate)
        return None

    @property
    def signal_present(self) -> bool:
        return self._decoder.signal_present if self._decoder else False

    @property
    def detected_fps(self) -> Optional[float]:
        return self._decoder.detected_fps if self._decoder else None

    @property
    def is_locked(self) -> bool:
        return self._decoder.is_locked if self._decoder else False

    # ── private ───────────────────────────────────────────────────────────────

    def _on_timecode(self, tc: Timecode) -> None:
        try:
            self._tc_queue.put_nowait(tc)
        except queue.Full:
            pass  # discard; main thread is falling behind

    def _audio_callback(self, indata: np.ndarray, frames: int, time_info, status) -> None:
        """Called from PortAudio real-time thread. Must not block."""
        if not self._running or self._decoder is None:
            return
        try:
            mono = indata[:, self._channel]
            self._decoder.push_samples(mono)
        except Exception:
            pass  # never let an exception propagate into PortAudio
