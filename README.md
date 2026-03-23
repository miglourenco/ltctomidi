# LTC to MIDI Program Change

A Windows desktop application that reads **SMPTE LTC (Linear Timecode)** from an audio input and fires **MIDI Program Change** messages at defined timecodes — ideal for automating snapshots on a **Waves LV1** mixing desk (or any MIDI-controllable system) during live shows.

---

## Features

- Reads LTC from any audio input (ASIO, WDM, MME)
- **ASIO support** — works with SoundGrid Driver and other ASIO interfaces
- Software BMC/LTC decoder — no external libraries needed
- Fires MIDI Program Change on any channel (1–16) at frame-accurate timecodes
- Supports 24, 25, 29.97 and 30 fps
- Drop-frame timecode support
- Cue list saved as JSON — easy to edit and share
- TAP button to capture live timecode into a cue
- Test Fire button to verify MIDI output without waiting for the timecode
- Enable/Disable individual cues without deleting them
- Frame tolerance setting for real-world jitter

---

## Download

Go to the [Releases](../../releases) page and download `LTCtoMIDI.exe`.
No installation required — just run the `.exe`.

---

## Recommended Setup

### Virtual MIDI Port — loopMIDI

To send MIDI Program Changes to software on the same machine (DAW, Waves LV1, etc.) you need a **virtual MIDI loopback driver**.

We recommend **loopMIDI** by Tobias Erichsen — it is free and widely used in professional audio.

1. Download loopMIDI: **https://www.tobias-erichsen.de/software/loopmidi.html**
2. Install and open loopMIDI
3. Click **+** to create a new virtual port (e.g. `LTC-MIDI`)
4. In **LTC to MIDI**, select that port as the MIDI Output
5. In your target software (Waves LV1, DAW, etc.), set the MIDI input to the same port

> loopMIDI must be running before you start LTC to MIDI.

### Physical MIDI Interface

If you prefer to send MIDI over a physical cable, connect a USB MIDI interface and select it directly as the MIDI Output — no loopMIDI needed.

---

## Workflow

```
Audio source (playback / timecode track)
        │
        │  LTC audio signal
        ▼
  Sound card / ASIO interface
        │
        │  audio input
        ▼
  LTC to MIDI (this app)
        │
        │  MIDI Program Change
        ▼
  loopMIDI virtual port  ──►  Waves LV1 / DAW / any MIDI device
```

---

## Quick Start

1. **Connect** your LTC source to an audio input on your interface
2. Open **LTC to MIDI**
3. Select the **Audio Input** device and the channel carrying the LTC signal
4. Select the **MIDI Output** port (loopMIDI virtual port or physical interface)
5. Click **▶ START**
6. The timecode display turns bright green when LTC is detected
7. Add cues to the list — set the timecode, MIDI channel, and Program Change number
8. Press Play on your timeline — cues fire automatically

---

## Cue List

| Column   | Description                                     |
|----------|-------------------------------------------------|
| #        | Cue order number                                |
| Timecode | HH:MM:SS:FF — when to fire                     |
| Label    | Free text description                           |
| PC       | Program Change number (0–127)                   |
| Ch       | MIDI channel (1–16)                             |
| ✓        | Enabled (● active / ○ disabled). Click to toggle |

- **Cues fire once** per playback pass. They reset automatically when TC jumps backwards by more than 1 second.
- Use **↺ Reset** to manually reset all fired flags (e.g. before a new run-through).
- Use **▶ Test** to send a Program Change immediately without waiting for the timecode.
- Cue lists are saved as `.json` files — open them with any text editor.

---

## ASIO / SoundGrid

For **SoundGrid Driver** or any other ASIO interface:

- The **SoundGrid Driver Control Panel** must be running before you open the app (ASIO drivers register dynamically)
- Select the ASIO device from the **Audio Input** dropdown
- If the device does not appear, click **↺** to refresh the list

---

## Frame Tolerance

The **Frame tolerance ±** setting (bottom of the window) defines how many frames early or late a cue can fire relative to its timecode. The default is `±1 frame`. Increase it slightly if cues are occasionally missed due to jitter in your playback system.

---

## Building from Source

Requirements: Python 3.12+ and the packages in `requirements.txt`.

```bash
pip install -r requirements.txt
python main.py
```

To build the standalone `.exe`:

```bash
build.bat
```

Output: `dist\LTCtoMIDI.exe`

---

## License

MIT — free to use, modify and distribute.
