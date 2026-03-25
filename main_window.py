"""
Main application window — tkinter + ttk.

All UI updates and CueEngine calls happen in the main thread via root.after().
Audio and MIDI callbacks run in their own threads and communicate through
queue.Queue (timecode_queue).
"""
from __future__ import annotations

import json
import os
import queue
import re
import sys
import threading
import tkinter as tk
import ssl
import urllib.request
try:
    import certifi as _certifi
    _SSL_CTX = ssl.create_default_context(cafile=_certifi.where())
except Exception:
    _SSL_CTX = None
import webbrowser
from tkinter import filedialog, messagebox, ttk
from typing import Optional

from audio_capture import AudioCapture, list_audio_devices, get_channel_names
from cue_engine import CueEngine
from ltc_decoder import Timecode
from midi_output import MidiError, MidiOutput
from models import AppSettings, Cue, CueList


# ── Version / update check ────────────────────────────────────────────────────

_VERSION      = "1.4.0"
_RELEASES_API = "https://api.github.com/repos/miglourenco/ltctomidi/releases/latest"
_RELEASES_URL = "https://github.com/miglourenco/ltctomidi/releases"

# ── Colour palette ────────────────────────────────────────────────────────────

_BG      = "#1E1E1E"   # root / outer background
_BG_PAN  = "#252526"   # panel / frame interior
_BG_WID  = "#3C3C3C"   # entry / spinbox / combobox bg
_BG_TC   = "#0A0A0A"   # TC display (near-black)
_BG_SEL  = "#094771"   # treeview selected row
_BG_HDR  = "#2D2D2D"   # panel title-bar
_BORDER  = "#3C3C3C"   # 1-px highlight borders

_FG      = "#CCCCCC"   # normal text
_FG_HEAD = "#888888"   # panel headings / dim labels
_FG_DIM  = "#555555"   # very dim

_TC_ON   = "#00FF41"   # bright green — signal active
_TC_OFF  = "#1A3A1A"   # dark green   — no signal

_FG_OK   = "#4EC9B0"   # teal  — OK / success
_FG_ERR  = "#F44747"   # red   — error
_FG_WARN = "#D7BA7D"   # gold  — warning / flash
_FG_FIRE = "#4EC9B0"   # teal  — cue fired
_FG_DIS  = "#505050"   # grey  — disabled cue row

# tk.Button colours
_BTN_BG  = "#383838"
_BTN_FG  = "#CCCCCC"
_BTN_ABG = "#505050"

_GO_BG   = "#166534"   # Start — green
_GO_ABG  = "#15803D"
_GO_DIS  = "#0D3D20"   # Start disabled

_ST_BG   = "#7F1D1D"   # Stop — red
_ST_ABG  = "#991B1B"
_ST_DIS  = "#3D1010"   # Stop disabled

_F_UI    = ("Segoe UI", 9)    if sys.platform == "win32" else ("Helvetica Neue", 11)
_F_UIB   = ("Segoe UI", 9, "bold") if sys.platform == "win32" else ("Helvetica Neue", 11, "bold")
_F_TC    = ("Courier New", 52, "bold")
_F_FPS   = ("Courier New", 11)
_F_MONO  = ("Courier New", 10)


# ── Button factory ────────────────────────────────────────────────────────────
# On macOS, tk.Button ignores bg/fg (native Aqua style always renders white).
# _FlatButton is a Label-based widget that respects colors on all platforms.

class _FlatButton(tk.Label):
    """tk.Label acting as a flat button — bg/fg respected on macOS."""

    def __init__(self, parent, *, text, command,
                 bg, fg, activebackground, activeforeground,
                 font, padx=8, pady=3, width=None):
        kw: dict = dict(text=text, bg=bg, fg=fg, font=font,
                        cursor="hand2", padx=padx, pady=pady,
                        relief="flat", bd=0, highlightthickness=0)
        if width is not None:
            kw["width"] = width
        super().__init__(parent, **kw)
        self._cmd          = command
        self._bg_on        = bg
        self._fg_on        = fg
        self._bg_active    = activebackground
        self._fg_active    = activeforeground
        self._disabled     = False
        self.bind("<ButtonPress-1>",   self._press)
        self.bind("<ButtonRelease-1>", self._release)
        self.bind("<Enter>",           self._enter)
        self.bind("<Leave>",           self._leave)

    def _press(self, _e):
        if not self._disabled:
            tk.Label.config(self, bg=self._bg_active, fg=self._fg_active)
            self._cmd()

    def _release(self, _e):
        if not self._disabled:
            tk.Label.config(self, bg=self._bg_on, fg=self._fg_on)

    def _enter(self, _e):
        if not self._disabled:
            tk.Label.config(self, bg=self._bg_active, fg=self._fg_active)

    def _leave(self, _e):
        tk.Label.config(self, bg=self._bg_on, fg=self._fg_on)

    def config(self, **kw):  # type: ignore[override]
        if "state" in kw:
            state = kw.pop("state")
            self._disabled = (state == "disabled")
            tk.Label.config(self, cursor="arrow" if self._disabled else "hand2")
        if "bg" in kw:
            self._bg_on = kw["bg"]
        if "fg" in kw:
            self._fg_on = kw["fg"]
        if kw:
            tk.Label.config(self, **kw)

    configure = config   # alias expected by tkinter


def _btn(parent, text, cmd, *,
         bg=_BTN_BG, fg=_BTN_FG, abg=_BTN_ABG,
         width=None, font=_F_UI, px=8, py=3):
    # macOS: tk.Button ignores bg/fg (native Aqua rendering) → use _FlatButton.
    # Windows/Linux: tk.Button respects colors and has keyboard focus → keep it.
    if sys.platform == "darwin":
        return _FlatButton(
            parent, text=text, command=cmd,
            bg=bg, fg=fg, activebackground=abg, activeforeground=fg,
            font=font, padx=px, pady=py, width=width,
        )
    kw = dict(text=text, command=cmd, bg=bg, fg=fg,
              activebackground=abg, activeforeground=fg,
              relief="flat", font=font, cursor="hand2",
              padx=px, pady=py, bd=0, highlightthickness=0)
    if width is not None:
        kw["width"] = width
    return tk.Button(parent, **kw)


# ── CueDialog ─────────────────────────────────────────────────────────────────

class CueDialog(tk.Toplevel):
    """Modal dialog for adding or editing a single Cue."""

    TC_RE = re.compile(r"^\d{2}:\d{2}:\d{2}[:;]\d{2}$")

    def __init__(self, parent: tk.Tk, *,
                 title: str = "Cue",
                 timecode: str = "00:00:00:00",
                 label: str = "",
                 channel: int = 1,
                 program: int = 0) -> None:
        super().__init__(parent)
        self.title(title)
        self.configure(bg=_BG)
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.result: Optional[dict] = None

        fr = tk.Frame(self, bg=_BG, padx=18, pady=14)
        fr.pack()

        def _lbl(row: int, text: str) -> None:
            tk.Label(fr, text=text, bg=_BG, fg=_FG_HEAD,
                     font=_F_UI, anchor="w").grid(
                         row=row, column=0, sticky="w", pady=5)

        def _entry(row: int, var: tk.Variable, width: int = 16,
                   font=_F_UI) -> tk.Entry:
            e = tk.Entry(fr, textvariable=var, width=width, font=font,
                         bg=_BG_WID, fg=_FG, insertbackground=_FG,
                         relief="flat", highlightthickness=1,
                         highlightbackground=_BORDER, highlightcolor=_FG_OK)
            e.grid(row=row, column=1, sticky="w", padx=(12, 0), pady=5)
            return e

        self._tc  = tk.StringVar(value=timecode)
        self._lbl = tk.StringVar(value=label)
        self._ch  = tk.IntVar(value=channel)
        self._pc  = tk.IntVar(value=program)

        _lbl(0, "Timecode  (HH:MM:SS:FF)")
        tc_e = _entry(0, self._tc, width=16, font=_F_MONO)
        tc_e.focus_set()

        _lbl(1, "Label")
        _entry(1, self._lbl, width=28)

        _lbl(2, "MIDI Channel  (1–16)")
        ttk.Spinbox(fr, from_=1, to=16, textvariable=self._ch,
                    width=8).grid(row=2, column=1, sticky="w", padx=(12, 0), pady=5)

        _lbl(3, "Program Change  (0–127)")
        ttk.Spinbox(fr, from_=0, to=127, textvariable=self._pc,
                    width=8).grid(row=3, column=1, sticky="w", padx=(12, 0), pady=5)

        bf = tk.Frame(fr, bg=_BG)
        bf.grid(row=4, column=0, columnspan=2, pady=(14, 0))
        _btn(bf, "  OK  ", self._ok,   bg=_GO_BG, abg=_GO_ABG, fg="#FFF",
             width=7, py=5).pack(side="left", padx=5)
        _btn(bf, "Cancel", self.destroy, width=7, py=5).pack(side="left", padx=5)

        self.bind("<Return>", lambda _: self._ok())
        self.bind("<Escape>", lambda _: self.destroy())

        # Centre on parent
        self.update_idletasks()
        x = parent.winfo_rootx() + (parent.winfo_width()  - self.winfo_width())  // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{x}+{y}")

        self.wait_window()

    def _ok(self) -> None:
        tc = self._tc.get().strip()
        if not self.TC_RE.match(tc):
            messagebox.showerror("Invalid Timecode",
                                 "Enter timecode as HH:MM:SS:FF", parent=self)
            return
        pc = self._pc.get()
        ch = self._ch.get()
        if not (0 <= pc <= 127):
            messagebox.showerror("Invalid Program", "Program must be 0–127", parent=self)
            return
        if not (1 <= ch <= 16):
            messagebox.showerror("Invalid Channel", "Channel must be 1–16", parent=self)
            return
        self.result = {
            "timecode": tc,
            "label":    self._lbl.get().strip(),
            "channel":  ch,
            "program":  pc,
        }
        self.destroy()


# ── MainWindow ────────────────────────────────────────────────────────────────

class MainWindow:
    def __init__(self, root: tk.Tk, settings: AppSettings) -> None:
        self.root = root
        self.settings = settings
        self.root.configure(bg=_BG)

        # Core objects
        self._tc_queue: "queue.Queue[Timecode]" = queue.Queue(maxsize=200)
        self._audio    = AudioCapture(self._tc_queue)
        self._midi     = MidiOutput()
        self._cue_list = CueList()
        self._engine   = CueEngine(self._midi,
                                   tolerance_frames=settings.tolerance_frames)
        self._engine.on_cue_fired  = self._on_cue_fired
        self._engine.on_midi_error = self._on_midi_error

        # UI state
        self._running        = False
        self._current_tc:    Optional[Timecode] = None
        self._current_file:  Optional[str]      = None
        self._flash_after:   Optional[str]      = None
        self._last_tc_time:  int                = 0
        self._audio_devices: list               = []
        self._midi_ports:    list               = []
        self._detected_sr:   int                = settings.sample_rate

        self._apply_theme()
        self._build_ui()
        self._refresh_audio_devices()
        self._refresh_midi_ports()
        self._restore_device_selection()
        self._poll_queue()

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        if settings.last_cue_file and os.path.isfile(settings.last_cue_file):
            self._load_cue_file(settings.last_cue_file)

        # Auto-check for updates on startup (silent if already up to date)
        self.root.after(4000, lambda: self._check_updates(silent_if_ok=True))

    # ══════════════════════════════════════════════════════════════════════════
    # Theme
    # ══════════════════════════════════════════════════════════════════════════

    def _apply_theme(self) -> None:
        s = ttk.Style()
        try:
            s.theme_use("clam")
        except Exception:
            pass

        s.configure(".",
                    background=_BG, foreground=_FG,
                    fieldbackground=_BG_WID, troughcolor=_BG_PAN,
                    selectbackground=_BG_SEL, selectforeground=_FG,
                    bordercolor=_BORDER, darkcolor=_BG_PAN, lightcolor=_BG_PAN,
                    relief="flat")

        s.configure("TFrame",  background=_BG)
        s.configure("TLabel",  background=_BG, foreground=_FG, font=_F_UI)

        for w in ("TEntry", "TSpinbox"):
            s.configure(w,
                        fieldbackground=_BG_WID, foreground=_FG,
                        bordercolor=_BORDER, lightcolor=_BG_WID,
                        darkcolor=_BG_WID, insertcolor=_FG,
                        arrowcolor=_FG_HEAD, relief="flat")

        s.configure("TCombobox",
                    fieldbackground=_BG_WID, foreground=_FG,
                    bordercolor=_BORDER, lightcolor=_BG_WID, darkcolor=_BG_WID,
                    arrowcolor=_FG_HEAD, selectbackground=_BG_WID,
                    selectforeground=_FG, relief="flat")
        s.map("TCombobox",
              fieldbackground=[("readonly", _BG_WID)],
              selectbackground=[("readonly", _BG_WID)],
              selectforeground=[("readonly", _FG)])

        s.configure("TScrollbar",
                    background=_BG_PAN, troughcolor=_BG,
                    arrowcolor=_FG_HEAD, bordercolor=_BG,
                    darkcolor=_BG_PAN, lightcolor=_BG_PAN, relief="flat")
        s.map("TScrollbar", background=[("active", "#505050")])

        s.configure("TSeparator", background=_BORDER)

        s.configure("Treeview",
                    background=_BG_PAN, foreground=_FG,
                    fieldbackground=_BG_PAN, bordercolor=_BORDER,
                    rowheight=24, font=_F_UI)
        s.configure("Treeview.Heading",
                    background=_BG_HDR, foreground=_FG_HEAD,
                    relief="flat", font=_F_UIB, bordercolor=_BORDER)
        s.map("Treeview",
              background=[("selected", _BG_SEL)],
              foreground=[("selected", _FG)])
        s.map("Treeview.Heading",
              background=[("active", "#3A3A3A")])

    # ══════════════════════════════════════════════════════════════════════════
    # UI construction
    # ══════════════════════════════════════════════════════════════════════════

    def _build_ui(self) -> None:
        self._build_menubar()
        outer = tk.Frame(self.root, bg=_BG, padx=8, pady=8)
        outer.pack(fill="both", expand=True)
        self._build_device_panel(outer)
        self._build_tc_panel(outer)
        self._build_cue_panel(outer)
        self._build_footer(outer)

    def _panel(self, parent: tk.Frame, title: str) -> tk.Frame:
        """Dark panel with a slim title bar. Returns the content frame."""
        wrap = tk.Frame(parent, bg=_BG)
        wrap.pack(fill="x", pady=(0, 6))

        hdr = tk.Frame(wrap, bg=_BG_HDR)
        hdr.pack(fill="x")
        tk.Label(hdr, text=title, bg=_BG_HDR, fg=_FG_HEAD,
                 font=_F_UIB, padx=8, pady=3).pack(side="left")

        body = tk.Frame(wrap, bg=_BG_PAN, padx=8, pady=6,
                        highlightthickness=1, highlightbackground=_BORDER)
        body.pack(fill="x")
        return body

    # ── Menubar ───────────────────────────────────────────────────────────────

    def _build_menubar(self) -> None:
        menubar = tk.Menu(self.root, bg=_BG_PAN, fg=_FG,
                          activebackground=_BG_SEL, activeforeground=_FG,
                          relief="flat", bd=0)

        def _menu(label: str, items: list) -> None:
            m = tk.Menu(menubar, tearoff=0, bg=_BG_PAN, fg=_FG,
                        activebackground=_BG_SEL, activeforeground=_FG)
            for item in items:
                if item is None:
                    m.add_separator()
                else:
                    kw = {k: v for k, v in item.items() if k != "label"}
                    m.add_command(label=item["label"], **kw)
            menubar.add_cascade(label=label, menu=m)

        _menu("File", [
            {"label": "New",      "command": self._new_list,    "accelerator": "Ctrl+N"},
            {"label": "Open…",    "command": self._open_list,   "accelerator": "Ctrl+O"},
            {"label": "Save",     "command": self._save_list,   "accelerator": "Ctrl+S"},
            {"label": "Save As…", "command": self._save_list_as},
            None,
            {"label": "Exit",     "command": self._on_close},
        ])
        _menu("Cues", [
            {"label": "Add Cue…",        "command": self._add_cue,        "accelerator": "Ins"},
            {"label": "Edit Cue…",       "command": self._edit_cue,       "accelerator": "Enter"},
            {"label": "Remove Cue",      "command": self._remove_cue,     "accelerator": "Del"},
            {"label": "Toggle Enabled",  "command": self._toggle_enabled, "accelerator": "Space"},
            None,
            {"label": "Reset Fired Flags", "command": self._reset_fired},
        ])
        _menu("Help", [
            {"label": "Check for Updates…", "command": self._check_updates},
            None,
            {"label": f"About  (v{_VERSION})", "command": self._show_about},
        ])

        self.root.config(menu=menubar)
        self.root.bind("<Control-n>", lambda _: self._new_list())
        self.root.bind("<Control-o>", lambda _: self._open_list())
        self.root.bind("<Control-s>", lambda _: self._save_list())
        self.root.bind("<Insert>",    lambda _: self._add_cue())
        self.root.bind("<Delete>",    lambda _: self._remove_cue())

    # ── Device panel ──────────────────────────────────────────────────────────

    def _build_device_panel(self, parent: tk.Frame) -> None:
        wrap = tk.Frame(parent, bg=_BG)
        wrap.pack(fill="x", pady=(0, 6))

        hdr = tk.Frame(wrap, bg=_BG_HDR)
        hdr.pack(fill="x")
        tk.Label(hdr, text="DEVICES & TRANSPORT", bg=_BG_HDR, fg=_FG_HEAD,
                 font=_F_UIB, padx=8, pady=3).pack(side="left")

        body = tk.Frame(wrap, bg=_BG_PAN, padx=8, pady=6,
                        highlightthickness=1, highlightbackground=_BORDER)
        body.pack(fill="x")

        # Left: device combos
        left = tk.Frame(body, bg=_BG_PAN)
        left.pack(side="left", fill="both", expand=True)

        # Audio row
        ar = tk.Frame(left, bg=_BG_PAN)
        ar.pack(fill="x", pady=2)
        tk.Label(ar, text="Audio Input", bg=_BG_PAN, fg=_FG_HEAD,
                 font=_F_UI, width=11, anchor="w").pack(side="left")
        self._audio_var = tk.StringVar()
        self._audio_combo = ttk.Combobox(ar, textvariable=self._audio_var,
                                         width=36, state="readonly", font=_F_UI)
        self._audio_combo.pack(side="left", padx=(4, 8))
        tk.Label(ar, text="Ch", bg=_BG_PAN, fg=_FG_HEAD,
                 font=_F_UI).pack(side="left")
        self._ch_var = tk.StringVar(value=str(self.settings.audio_channel))
        self._ch_combo = ttk.Combobox(ar, textvariable=self._ch_var,
                                      width=5, state="readonly", font=_F_UI)
        self._ch_combo.pack(side="left", padx=4)
        self._sr_force_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(ar, text="SR Force:", variable=self._sr_force_var,
                        command=self._on_sr_force_toggle).pack(side="left", padx=(8, 2))
        self._sr_var = tk.StringVar(value=str(self.settings.sample_rate))
        self._sr_combo = ttk.Combobox(ar, textvariable=self._sr_var,
                                      values=["44100", "48000", "96000"],
                                      width=7, state="disabled")
        self._sr_combo.pack(side="left")
        _btn(ar, "↺", self._refresh_audio_devices, width=2,
             px=5, py=1).pack(side="left", padx=(6, 0))
        self._audio_combo.bind("<<ComboboxSelected>>", self._on_audio_device_changed)

        # MIDI row
        mr = tk.Frame(left, bg=_BG_PAN)
        mr.pack(fill="x", pady=2)
        tk.Label(mr, text="MIDI Output", bg=_BG_PAN, fg=_FG_HEAD,
                 font=_F_UI, width=11, anchor="w").pack(side="left")
        self._midi_var = tk.StringVar()
        self._midi_combo = ttk.Combobox(mr, textvariable=self._midi_var,
                                        width=36, state="readonly", font=_F_UI)
        self._midi_combo.pack(side="left", padx=(4, 8))
        _btn(mr, "↺", self._refresh_midi_ports, width=2,
             px=5, py=1).pack(side="left")

        # Right: transport
        tf = tk.Frame(body, bg=_BG_PAN, padx=8)
        tf.pack(side="right", fill="y", pady=2)

        self._start_btn = _btn(tf, "▶  START", self._start,
                               bg=_GO_BG, abg=_GO_ABG, fg="#FFFFFF",
                               width=10, px=14, py=8,
                               font=("Segoe UI", 9, "bold"))
        self._start_btn.pack(pady=(0, 4))

        self._stop_btn = _btn(tf, "■  STOP", self._stop,
                              bg=_ST_DIS, abg=_ST_ABG, fg="#555555",
                              width=10, px=14, py=8,
                              font=("Segoe UI", 9, "bold"))
        self._stop_btn.pack()
        self._stop_btn.config(state="disabled")

    # ── Timecode display ──────────────────────────────────────────────────────

    def _build_tc_panel(self, parent: tk.Frame) -> None:
        wrap = tk.Frame(parent, bg=_BG)
        wrap.pack(fill="x", pady=(0, 6))

        # TC display (left)
        tc_bg = tk.Frame(wrap, bg=_BG_TC, padx=20, pady=10,
                         highlightthickness=1, highlightbackground=_BORDER)
        tc_bg.pack(side="left", fill="both", expand=True)

        self._tc_label = tk.Label(tc_bg, text="--:--:--:--",
                                   font=_F_TC, fg=_TC_OFF, bg=_BG_TC)
        self._tc_label.pack()

        self._fps_label = tk.Label(tc_bg, text="FPS: —",
                                    font=_F_FPS, fg=_FG_DIM, bg=_BG_TC)
        self._fps_label.pack()

        # Status panel (right)
        sf = tk.Frame(wrap, bg=_BG_PAN, padx=16, pady=8,
                      highlightthickness=1, highlightbackground=_BORDER)
        sf.pack(side="right", fill="y")

        def _status_row(heading: str) -> tk.Label:
            tk.Label(sf, text=heading, bg=_BG_PAN, fg=_FG_HEAD,
                     font=("Segoe UI", 8, "bold"), anchor="w").pack(anchor="w")
            lbl = tk.Label(sf, text="—", bg=_BG_PAN, fg=_FG_DIM,
                           font=("Segoe UI", 10, "bold"), anchor="w",
                           justify="left")
            lbl.pack(anchor="w", pady=(0, 8))
            return lbl

        self._ltc_status   = _status_row("LTC SIGNAL")
        self._midi_status  = _status_row("MIDI")
        self._last_cue_lbl = _status_row("LAST CUE")

        self._ltc_status.config(text="● No signal", fg=_FG_DIM)
        self._midi_status.config(text="● Not open",  fg=_FG_DIM)
        self._last_cue_lbl.config(text="—",          fg=_FG_DIM)

    # ── Cue list panel ────────────────────────────────────────────────────────

    def _build_cue_panel(self, parent: tk.Frame) -> None:
        wrap = tk.Frame(parent, bg=_BG)
        wrap.pack(fill="both", expand=True, pady=(0, 6))

        hdr = tk.Frame(wrap, bg=_BG_HDR)
        hdr.pack(fill="x")
        tk.Label(hdr, text="CUE LIST", bg=_BG_HDR, fg=_FG_HEAD,
                 font=_F_UIB, padx=8, pady=3).pack(side="left")

        body = tk.Frame(wrap, bg=_BG_PAN, padx=4, pady=4,
                        highlightthickness=1, highlightbackground=_BORDER)
        body.pack(fill="both", expand=True)

        # Toolbar
        tb = tk.Frame(body, bg=_BG_PAN, pady=3)
        tb.pack(fill="x", padx=4)

        def _sep() -> None:
            tk.Frame(tb, bg=_BORDER, width=1).pack(side="left", fill="y",
                                                     padx=4, pady=2)

        _btn(tb, "+ Add",    self._add_cue,    width=7).pack(side="left", padx=1)
        _btn(tb, "✎ Edit",   self._edit_cue,   width=7).pack(side="left", padx=1)
        _btn(tb, "− Remove", self._remove_cue, width=8).pack(side="left", padx=1)
        _sep()
        self._tap_btn = _btn(tb, "⏱ TAP", self._tap, width=7)
        self._tap_btn.pack(side="left", padx=1)
        self._tap_btn.config(state="disabled")
        _sep()
        _btn(tb, "↑", self._move_up,   width=2).pack(side="left", padx=1)
        _btn(tb, "↓", self._move_down, width=2).pack(side="left", padx=1)
        _sep()
        _btn(tb, "▶ Test",   self._test_fire,   width=8).pack(side="left", padx=1)
        _btn(tb, "↺ Reset",  self._reset_fired, width=8).pack(side="left", padx=1)
        _sep()
        _btn(tb, "⊙ Enable/Disable", self._toggle_enabled,
             width=16).pack(side="left", padx=1)

        # Treeview
        tree_fr = tk.Frame(body, bg=_BG_PAN)
        tree_fr.pack(fill="both", expand=True, padx=4, pady=(2, 4))

        cols = ("num", "timecode", "label", "program", "channel", "enabled")
        self._tree = ttk.Treeview(tree_fr, columns=cols, show="headings",
                                   selectmode="browse", height=14)

        self._tree.heading("num",      text="#",        anchor="center")
        self._tree.heading("timecode", text="Timecode", anchor="center")
        self._tree.heading("label",    text="Label",    anchor="w")
        self._tree.heading("program",  text="PC",       anchor="center")
        self._tree.heading("channel",  text="Ch",       anchor="center")
        self._tree.heading("enabled",  text="✓",        anchor="center")

        self._tree.column("num",      width=36,  anchor="center", stretch=False)
        self._tree.column("timecode", width=120, anchor="center", stretch=False)
        self._tree.column("label",    width=260, anchor="w")
        self._tree.column("program",  width=50,  anchor="center", stretch=False)
        self._tree.column("channel",  width=50,  anchor="center", stretch=False)
        self._tree.column("enabled",  width=46,  anchor="center", stretch=False)

        sb = ttk.Scrollbar(tree_fr, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=sb.set)
        self._tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        self._tree.tag_configure("fired",    foreground=_FG_FIRE,
                                              font=("Segoe UI", 9, "bold"))
        self._tree.tag_configure("disabled", foreground=_FG_DIS)

        self._tree.bind("<Double-1>",        lambda _: self._edit_cue())
        self._tree.bind("<Return>",          lambda _: self._edit_cue())
        self._tree.bind("<space>",           lambda _: self._toggle_enabled())
        self._tree.bind("<ButtonRelease-1>", self._on_tree_click)

    def _on_tree_click(self, event) -> None:
        """Toggle enabled when clicking the ✓ column."""
        col = self._tree.identify_column(event.x)
        row = self._tree.identify_row(event.y)
        if col == "#6" and row:
            self._tree.selection_set(row)
            self._toggle_enabled()

    # ── Footer ────────────────────────────────────────────────────────────────

    def _build_footer(self, parent: tk.Frame) -> None:
        fr = tk.Frame(parent, bg=_BG)
        fr.pack(fill="x")

        tk.Label(fr, text="Frame tolerance ±", bg=_BG, fg=_FG_HEAD,
                 font=_F_UI).pack(side="left", padx=(0, 4))
        self._tol_var = tk.IntVar(value=self.settings.tolerance_frames)
        ttk.Spinbox(fr, from_=0, to=10, textvariable=self._tol_var,
                    width=4, command=self._update_tolerance).pack(side="left")
        tk.Label(fr, text="frames", bg=_BG, fg=_FG_HEAD,
                 font=_F_UI).pack(side="left", padx=(4, 0))

        self._file_lbl = tk.Label(fr, text="No file loaded", bg=_BG,
                                   fg=_FG_DIM, font=_F_UI)
        self._file_lbl.pack(side="right", padx=8)

    # ══════════════════════════════════════════════════════════════════════════
    # Device management
    # ══════════════════════════════════════════════════════════════════════════

    def _refresh_audio_devices(self) -> None:
        self._audio_devices = list_audio_devices()
        names = [f"{d['name']}  [{d['hostapi']}]" for d in self._audio_devices]
        self._audio_combo["values"] = names
        if not names:
            self._audio_combo.set("(no input devices found)")
            return
        current = self._audio_var.get()
        if current in names:
            return
        asio_idx = next(
            (i for i, d in enumerate(self._audio_devices)
             if "asio" in d["hostapi"].lower()), None)
        self._audio_combo.current(asio_idx if asio_idx is not None else 0)
        self._on_audio_device_changed()

    def _refresh_midi_ports(self) -> None:
        self._midi_ports = MidiOutput.list_ports()
        self._midi_combo["values"] = self._midi_ports
        if not self._midi_ports:
            self._midi_combo.set("(no MIDI ports found)")
            self._midi_status.config(text="● No ports", fg=_FG_ERR)
            return
        current = self._midi_var.get()
        if current not in self._midi_ports:
            self._midi_combo.current(0)

    def _restore_device_selection(self) -> None:
        saved_audio = self.settings.audio_device
        saved_midi  = self.settings.midi_port
        if saved_audio:
            for i, d in enumerate(self._audio_devices):
                if d["name"] == saved_audio:
                    self._audio_combo.current(i)
                    break
        if saved_midi and saved_midi in self._midi_ports:
            self._midi_combo.current(self._midi_ports.index(saved_midi))
        self._on_audio_device_changed()

    def _on_audio_device_changed(self, event=None) -> None:
        idx = self._audio_combo.current()
        if idx < 0 or idx >= len(self._audio_devices):
            return
        dev = self._audio_devices[idx]
        self._detected_sr = int(dev["default_samplerate"])
        # Populate channel dropdown with named channels for this device
        names = get_channel_names(dev["index"], int(dev["channels"]), dev["hostapi"])
        self._ch_combo["values"] = names
        # Restore saved channel (1-based → 0-based index), clamp to valid range
        saved_idx = self.settings.audio_channel - 1
        saved_idx = max(0, min(saved_idx, len(names) - 1))
        self._ch_combo.current(saved_idx)

    def _on_sr_force_toggle(self) -> None:
        state = "readonly" if self._sr_force_var.get() else "disabled"
        self._sr_combo.config(state=state)

    def _get_sample_rate(self) -> int:
        if self._sr_force_var.get():
            return int(self._sr_var.get())
        return self._detected_sr

    # ══════════════════════════════════════════════════════════════════════════
    # Start / Stop
    # ══════════════════════════════════════════════════════════════════════════

    def _start(self) -> None:
        if self._running:
            return

        midi_idx = self._midi_combo.current()
        if midi_idx < 0 or not self._midi_ports:
            messagebox.showerror("MIDI", "Select a MIDI output port first.")
            return
        try:
            self._midi.open(midi_idx)
        except MidiError as exc:
            messagebox.showerror("MIDI Error", str(exc))
            return

        audio_idx = self._audio_combo.current()
        if audio_idx < 0 or not self._audio_devices:
            messagebox.showerror("Audio", "Select an audio input device first.")
            self._midi.close()
            return

        dev = self._audio_devices[audio_idx]
        channel = max(0, self._ch_combo.current())   # 0-based
        sr = self._get_sample_rate()
        try:
            self._audio.configure(dev["index"], channel, sr)
            self._audio.start()
        except Exception as exc:
            messagebox.showerror("Audio Error", str(exc))
            self._midi.close()
            return

        self._running = True
        self._engine.load_cue_list(self._cue_list)
        self._engine.tolerance_frames = self._tol_var.get()

        self._start_btn.config(state="disabled", bg=_GO_DIS, fg="#555555")
        self._stop_btn.config(state="normal",    bg=_ST_BG,  fg="#FFFFFF")
        self._tap_btn.config(state="normal")
        self._tc_label.config(fg=_TC_ON)
        self._midi_status.config(text=f"● {self._midi.port_name}", fg=_FG_OK)

    def _stop(self) -> None:
        if not self._running:
            return
        self._audio.stop()
        self._midi.close()
        self._running = False
        self._engine.reset()

        self._start_btn.config(state="normal",   bg=_GO_BG,  fg="#FFFFFF")
        self._stop_btn.config(state="disabled",  bg=_ST_DIS, fg="#555555")
        self._tap_btn.config(state="disabled")
        self._tc_label.config(text="--:--:--:--", fg=_TC_OFF)
        self._fps_label.config(text="FPS: —")
        self._ltc_status.config(text="● No signal", fg=_FG_DIM)
        self._midi_status.config(text="● Not open",  fg=_FG_DIM)

    # ══════════════════════════════════════════════════════════════════════════
    # Timecode poll loop (main thread, ~25 Hz)
    # ══════════════════════════════════════════════════════════════════════════

    def _poll_queue(self) -> None:
        if self._running:
            latest: Optional[Timecode] = None
            try:
                while True:
                    tc = self._tc_queue.get_nowait()
                    self._engine.on_timecode(tc)
                    self._engine.set_fps(tc.fps)
                    latest = tc
            except queue.Empty:
                pass

            if latest is not None:
                self._current_tc = latest
                self._tc_label.config(text=str(latest))
                self._last_tc_time = 0
                fps = self._audio.detected_fps
                if fps:
                    self._fps_label.config(text=f"FPS: {fps:.2f}")

            self._last_tc_time += 1
            if self._audio.signal_present:
                self._ltc_status.config(text="● LTC OK", fg=_FG_OK)
                self._tc_label.config(fg=_TC_ON)   # ← restore bright green on recovery
            elif self._last_tc_time > 25:           # ~1 s without TC
                self._tc_label.config(fg=_TC_OFF)
                self._ltc_status.config(text="● No signal", fg=_FG_ERR)

        self.root.after(40, self._poll_queue)   # 40 ms ≈ 25 Hz

    # ══════════════════════════════════════════════════════════════════════════
    # Cue list operations
    # ══════════════════════════════════════════════════════════════════════════

    def _refresh_tree(self) -> None:
        sel = self._tree.selection()
        self._tree.delete(*self._tree.get_children())
        for n, cue in enumerate(self._cue_list.cues, start=1):
            tags: list = []
            if cue.fired:
                tags.append("fired")
            if not cue.enabled:
                tags.append("disabled")
            self._tree.insert("", "end", iid=str(cue.id),
                               values=(n,
                                       cue.timecode,
                                       cue.label,
                                       cue.program,
                                       cue.channel,
                                       "●" if cue.enabled else "○"),
                               tags=tags)
        if sel:
            try:
                self._tree.selection_set(sel)
                self._tree.see(sel[0])
            except Exception:
                pass

    def _selected_cue(self) -> Optional[Cue]:
        sel = self._tree.selection()
        if not sel:
            return None
        return self._cue_list.by_id(int(sel[0]))

    def _add_cue(self) -> None:
        tc_str = str(self._current_tc) if self._current_tc else "00:00:00:00"
        dlg = CueDialog(self.root, title="Add Cue", timecode=tc_str)
        if dlg.result:
            self._cue_list.add(**dlg.result)
            self._refresh_tree()
            self._sync_engine()

    def _edit_cue(self) -> None:
        cue = self._selected_cue()
        if cue is None:
            return
        dlg = CueDialog(self.root, title="Edit Cue",
                        timecode=cue.timecode, label=cue.label,
                        channel=cue.channel, program=cue.program)
        if dlg.result:
            self._cue_list.replace(cue.id, **dlg.result)
            cue.fired = False
            self._refresh_tree()
            self._sync_engine()

    def _remove_cue(self) -> None:
        cue = self._selected_cue()
        if cue is None:
            return
        self._cue_list.remove(cue.id)
        self._refresh_tree()
        self._sync_engine()

    def _move_up(self) -> None:
        cue = self._selected_cue()
        if cue and self._cue_list.move_up(cue.id):
            self._refresh_tree()
            self._tree.selection_set(str(cue.id))

    def _move_down(self) -> None:
        cue = self._selected_cue()
        if cue and self._cue_list.move_down(cue.id):
            self._refresh_tree()
            self._tree.selection_set(str(cue.id))

    def _toggle_enabled(self) -> None:
        cue = self._selected_cue()
        if cue:
            cue.enabled = not cue.enabled
            self._refresh_tree()
            # Engine sees the change immediately (same object reference)

    def _tap(self) -> None:
        if not self._current_tc:
            return
        cue = self._selected_cue()
        tc_str = str(self._current_tc)
        if cue:
            self._cue_list.replace(cue.id, timecode=tc_str)
            cue.fired = False
            self._refresh_tree()
        else:
            dlg = CueDialog(self.root, title="Add Cue (TAP)", timecode=tc_str)
            if dlg.result:
                self._cue_list.add(**dlg.result)
                self._refresh_tree()
                self._sync_engine()

    def _test_fire(self) -> None:
        cue = self._selected_cue()
        if cue is None:
            messagebox.showinfo("Test Fire", "Select a cue first.")
            return
        if not self._midi.is_open:
            messagebox.showwarning("MIDI",
                                   "MIDI not connected — start the engine first.")
            return
        try:
            self._midi.send_program_change(cue.channel, cue.program)
            self._flash_midi(f"Test: PC {cue.program} → Ch {cue.channel}")
        except MidiError as exc:
            messagebox.showerror("MIDI Error", str(exc))

    def _reset_fired(self) -> None:
        self._engine.reset()
        self._refresh_tree()

    def _sync_engine(self) -> None:
        if self._running:
            self._engine.load_cue_list(self._cue_list)

    # ── CueEngine callbacks ───────────────────────────────────────────────────

    def _on_cue_fired(self, cue: Cue) -> None:
        self._refresh_tree()
        self._last_cue_lbl.config(
            text=f"#{cue.id}  {cue.label}\nPC {cue.program} → Ch {cue.channel}",
            fg=_FG_OK,
        )
        self._flash_midi(f"Fired: {cue.label}  PC {cue.program}")
        try:
            self._tree.see(str(cue.id))
        except Exception:
            pass

    def _on_midi_error(self, msg: str) -> None:
        self._midi_status.config(text=f"● ERR: {msg[:30]}", fg=_FG_ERR)

    def _flash_midi(self, msg: str) -> None:
        if self._flash_after:
            self.root.after_cancel(self._flash_after)
        self._midi_status.config(text=f"● {msg[:40]}", fg=_FG_WARN)
        port = self._midi.port_name or "Connected"
        self._flash_after = self.root.after(
            2000,
            lambda: self._midi_status.config(text=f"● {port}", fg=_FG_OK)
        )

    # ══════════════════════════════════════════════════════════════════════════
    # Update check
    # ══════════════════════════════════════════════════════════════════════════

    def _check_updates(self, silent_if_ok: bool = False) -> None:
        """Fetch latest release tag from GitHub in a background thread."""

        def _fetch() -> None:
            try:
                req = urllib.request.Request(
                    _RELEASES_API,
                    headers={"User-Agent": f"LTCtoMIDI/{_VERSION}"},
                )
                with urllib.request.urlopen(req, timeout=6, context=_SSL_CTX) as resp:
                    data = json.loads(resp.read())
                tag = data.get("tag_name", "").lstrip("v")
                url = data.get("html_url", _RELEASES_URL)
                self.root.after(0, lambda: _show(tag, url, None))
            except Exception as exc:
                self.root.after(0, lambda: _show(None, None, str(exc)))

        def _parse(v: str) -> tuple:
            try:
                return tuple(int(x) for x in v.split("."))
            except Exception:
                return (0,)

        def _show(tag, url, error) -> None:
            if error:
                if not silent_if_ok:
                    messagebox.showerror(
                        "Update check failed",
                        f"Could not reach GitHub:\n{error}",
                        parent=self.root,
                    )
                return
            if _parse(tag) > _parse(_VERSION):
                if messagebox.askyesno(
                    "Update available",
                    f"Version {tag} is available — you have {_VERSION}.\n\nOpen the download page?",
                    parent=self.root,
                ):
                    webbrowser.open(url)
            elif not silent_if_ok:
                messagebox.showinfo(
                    "Up to date",
                    f"You have the latest version ({_VERSION}).",
                    parent=self.root,
                )

        threading.Thread(target=_fetch, daemon=True).start()

    def _show_about(self) -> None:
        messagebox.showinfo(
            "About LTC to MIDI",
            f"LTC → MIDI Program Change\nVersion {_VERSION}\n\n"
            "Reads SMPTE LTC timecode from any audio input\n"
            "and fires MIDI Program Changes at defined cues.\n\n"
            "github.com/miglourenco/ltctomidi",
            parent=self.root,
        )

    # ══════════════════════════════════════════════════════════════════════════
    # File operations
    # ══════════════════════════════════════════════════════════════════════════

    def _new_list(self) -> None:
        if self._cue_list.cues:
            if not messagebox.askyesno("New", "Discard current cue list?"):
                return
        self._cue_list = CueList()
        self._current_file = None
        self._file_lbl.config(text="No file loaded")
        self._refresh_tree()
        self._sync_engine()

    def _open_list(self) -> None:
        path = filedialog.askopenfilename(
            title="Open Cue List",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if path:
            self._load_cue_file(path)

    def _load_cue_file(self, path: str) -> None:
        try:
            self._cue_list = CueList.load(path)
            self._current_file = path
            self._file_lbl.config(text=os.path.basename(path))
            self._refresh_tree()
            self._sync_engine()
        except Exception as exc:
            messagebox.showerror("Open Error", str(exc))

    def _save_list(self) -> None:
        if not self._current_file:
            self._save_list_as()
        else:
            self._write_cue_file(self._current_file)

    def _save_list_as(self) -> None:
        path = filedialog.asksaveasfilename(
            title="Save Cue List",
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if path:
            self._write_cue_file(path)
            self._current_file = path
            self._file_lbl.config(text=os.path.basename(path))

    def _write_cue_file(self, path: str) -> None:
        try:
            self._cue_list.save(path)
        except Exception as exc:
            messagebox.showerror("Save Error", str(exc))

    # ══════════════════════════════════════════════════════════════════════════
    # Tolerance & cleanup
    # ══════════════════════════════════════════════════════════════════════════

    def _update_tolerance(self) -> None:
        self._engine.tolerance_frames = self._tol_var.get()

    def _on_close(self) -> None:
        self._stop()
        audio_idx = self._audio_combo.current()
        if 0 <= audio_idx < len(self._audio_devices):
            self.settings.audio_device = self._audio_devices[audio_idx]["name"]
        midi_idx = self._midi_combo.current()
        if 0 <= midi_idx < len(self._midi_ports):
            self.settings.midi_port = self._midi_ports[midi_idx]
        self.settings.audio_channel    = max(1, self._ch_combo.current() + 1)
        self.settings.sample_rate      = int(self._sr_var.get())  # saves forced value
        self.settings.tolerance_frames = self._tol_var.get()
        self.settings.last_cue_file    = self._current_file or ""
        self.settings.save()
        self.root.destroy()
