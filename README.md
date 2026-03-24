# LTC to MIDI Program Change

<p align="center">
  <img src="logo.png" alt="LTC to MIDI logo" width="600"/>
</p>

A Windows and macOS desktop application that reads **SMPTE LTC (Linear Timecode)** from an audio input and fires **MIDI Program Change** messages at defined timecodes — ideal for automating snapshots on a **Waves LV1** mixing desk (or any MIDI-controllable system) during live shows.

---

## Features

- **Windows and macOS** — single codebase, native feel on both platforms
- Reads LTC from any audio input (ASIO, WDM, MME on Windows — CoreAudio on macOS)
- **ASIO support** — works with SoundGrid Driver and other ASIO interfaces
- Software BMC/LTC decoder — no external libraries needed
- Fires MIDI Program Change on any channel (1–16) at frame-accurate timecodes
- Supports 24, 25, 29.97, 30, 50, 59.94 and 60 fps
- Drop-frame timecode support
- Cue list saved as JSON — easy to edit and share
- TAP button to capture live timecode into a cue
- Test Fire button to verify MIDI output without waiting for the timecode
- Enable/Disable individual cues without deleting them
- Frame tolerance setting for real-world jitter

---

## Download

Go to the [Releases](../../releases) page and download the file for your platform:

| Platform | File |
|----------|------|
| Windows  | `LTCtoMIDI.exe` — no installation required |
| macOS    | `LTCtoMIDI.dmg` — open and drag to Applications |

---

## First Launch — Security Warnings

The app is not yet signed with a commercial certificate. Both Windows and macOS will warn you the first time you run it.

### macOS

macOS Gatekeeper blocks apps from unidentified developers by default.

1. Try to open the app — Gatekeeper will block it
2. Open **System Settings → Privacy & Security**
3. Scroll down to the security section — you will see a message about LTCtoMIDI being blocked
4. Click **Open Anyway**
5. Confirm by clicking **Open** in the dialog that appears

> After the first authorisation the app opens normally every time.

### Windows

Windows SmartScreen may block the exe because it is downloaded from the internet.

1. Right-click `LTCtoMIDI.exe` → **Properties**
2. At the bottom, tick **Unblock** → click **OK**
3. Run the exe normally

If SmartScreen still appears when launching:
- Click **More info** → **Run anyway**

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

### High frame rate (50 / 59.94 / 60 fps)

50 and 60 fps LTC uses a doubled bit rate — the signal runs at twice the speed of 25/30 fps LTC, while frame numbers still encode the base-rate count (0–24 or 0–29).

> **Use 96 kHz sample rate** for reliable decoding at 50 fps and above. At 48 kHz the half-bit period drops to ~6 samples, which leaves very little margin for jitter. Select `96000` in the **SR** dropdown before starting.

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
