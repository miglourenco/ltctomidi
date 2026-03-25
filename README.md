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
- **ASIO channel names** — channel dropdown shows the real driver names (e.g. "SoundGrid 1")
- **Built-in virtual MIDI port on macOS** — appears as a MIDI input in any app, no extra software needed
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

Windows may block the exe depending on your security settings.

**Option A — Unblock in Properties** (works on most systems):
1. Right-click `LTCtoMIDI.exe` → **Properties**
2. At the bottom, tick **Unblock** → click **OK**
3. Run the exe normally

**Option B — SmartScreen warning** (click More info → Run anyway):
If a blue SmartScreen dialog appears when launching, click **More info** then **Run anyway**.

**Option C — Windows 11 Smart App Control** (most restrictive):
Smart App Control does not have a "Run anyway" option. To run unsigned apps you need to disable it:
1. Open **Windows Security → App & browser control**
2. Click **Smart App Control settings**
3. Set it to **Off**

> ⚠️ Smart App Control cannot be re-enabled without reinstalling Windows.

> 🔐 A code signing certificate application has been submitted to [SignPath.io](https://signpath.io) under their open-source programme. Once approved, future releases will be signed and will not trigger any security warnings on Windows or macOS.

---

## Recommended Setup

### macOS — Built-in Virtual MIDI Port

On macOS, LTC to MIDI creates its own virtual MIDI port automatically. No extra software needed.

1. Open **LTC to MIDI**
2. In the **MIDI Output** dropdown, select **LTC to MIDI (virtual)**
3. In your target software (DAW, Waves LV1, etc.), set the MIDI input to **LTC to MIDI**

That's it — no IAC Driver configuration required.

### Windows — loopMIDI

On Windows, a virtual MIDI loopback driver is needed to route MIDI between apps on the same machine.

We recommend **loopMIDI** by Tobias Erichsen — free and widely used in professional audio.

1. Download loopMIDI: **https://www.tobias-erichsen.de/software/loopmidi.html**
2. Install and open loopMIDI
3. Click **+** to create a new virtual port (e.g. `LTC-MIDI`)
4. In **LTC to MIDI**, select that port as the MIDI Output
5. In your target software (Waves LV1, DAW, etc.), set the MIDI input to the same port

> loopMIDI must be running before you start LTC to MIDI.

### Physical MIDI Interface

On either platform, connect a USB MIDI interface and select it directly as the MIDI Output — no virtual port needed.

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
        ├─── macOS: LTC to MIDI (virtual) ──►  Waves LV1 / DAW / any CoreMIDI app
        │
        └─── Windows: loopMIDI port        ──►  Waves LV1 / DAW / any MIDI app
```

---

## Quick Start

1. **Connect** your LTC source to an audio input on your interface
2. Open **LTC to MIDI**
3. Select the **Audio Input** device and the channel carrying the LTC signal
4. Select the **MIDI Output** port:
   - **macOS** → select **LTC to MIDI (virtual)** — no extra setup needed
   - **Windows** → select your loopMIDI port or physical MIDI interface
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
