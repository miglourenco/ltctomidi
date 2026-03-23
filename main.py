"""
LTC → MIDI Program Change
Entry point.
"""
import os
import sys

# Must be set BEFORE sounddevice is imported anywhere.
# Tells sounddevice to load the ASIO-enabled PortAudio DLL (Windows only).
# On macOS/Linux this env var has no effect; don't set it to avoid spurious warnings.
if sys.platform == "win32":
    os.environ.setdefault("SD_ENABLE_ASIO", "1")

import tkinter as tk

from models import AppSettings
from main_window import MainWindow


def main() -> None:
    settings = AppSettings.load()

    root = tk.Tk()
    root.title("LTC → MIDI Program Change")
    root.minsize(860, 620)

    try:
        # High-DPI awareness on Windows
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

    try:
        root.iconbitmap("ltctomidi.ico")
    except Exception:
        pass

    MainWindow(root, settings)
    root.mainloop()


if __name__ == "__main__":
    main()
