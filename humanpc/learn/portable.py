"""Standalone trainer for other machines (what ``HumanpcTrainer.exe`` runs).

Asks for a name, runs the trainer, and keeps ``Desktop/mousedata_<name>.zip``
up to date in the background: every save (autosave every 15 tasks, pause,
break, leaving the window, quitting, even a crash) rebuilds the zip with *all*
of that person's sessions. The file on the Desktop is always the one to send.
"""

from __future__ import annotations

import ctypes
import os
import subprocess
import sys
import traceback
from pathlib import Path


def app_dir() -> Path:
    return Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "humanpc-trainer"


def desktop_dir() -> Path:
    """Real Desktop folder (follows OneDrive redirection), falling back to home."""
    if sys.platform == "win32":
        buf = ctypes.create_unicode_buffer(260)
        if ctypes.windll.shell32.SHGetFolderPathW(None, 0x0010, None, 0, buf) == 0 and buf.value:
            return Path(buf.value)
    d = Path.home() / "Desktop"
    return d if d.is_dir() else Path.home()


def _ask_name(root, default: str) -> str | None:
    from tkinter import messagebox, simpledialog

    from .dataset import clean_person
    while True:
        name = simpledialog.askstring(
            "humanpc trainer", "Your name (used to label your mouse data):",
            initialvalue=default, parent=root)
        if name is None:
            return None
        try:
            return clean_person(name)
        except ValueError:
            messagebox.showwarning("humanpc trainer", "Please use letters or numbers.", parent=root)


def _log_error(text: str) -> Path:
    path = app_dir() / "trainer_error.log"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(text + "\n")
    return path


def main() -> int:
    import tkinter as tk
    from tkinter import messagebox

    from ..perception.dpi import set_dpi_awareness
    from .trainer_app import run_trainer
    from .transfer import BackgroundExporter

    dpi_mode = set_dpi_awareness()  # before any window exists
    base = app_dir()
    base.mkdir(parents=True, exist_ok=True)
    last_name_file = base / "last_name.txt"
    default = last_name_file.read_text(encoding="utf-8").strip() if last_name_file.exists() else ""

    root = tk.Tk()
    root.withdraw()
    person = _ask_name(root, default)
    root.destroy()
    if not person:
        return 0
    last_name_file.write_text(person, encoding="utf-8")

    data_dir = base / person
    out = desktop_dir() / f"mousedata_{person}.zip"
    errors: list[str] = []
    exporter = BackgroundExporter(data_dir, person, out,
                                  on_error=lambda e: errors.append(_log_error(repr(e)).name))
    crash = None
    try:
        run_trainer(data_dir, person=person, dpi_mode=dpi_mode, on_saved=exporter.request)
    except Exception:  # noqa: BLE001 - data is already saved by the app; tell the user
        crash = _log_error(traceback.format_exc())
    final = exporter.flush()

    root = tk.Tk()
    root.withdraw()
    if final:
        msg = (f"Thanks! Your mouse data is saved here:\n\n{final['zip']}\n\n"
               f"{final['sessions']} session(s), {final['bytes'] / 1024:.0f} KB.\n"
               "Send this file to the person collecting the data.\n"
               "Running the trainer again adds to the same file.")
        if crash:
            msg += f"\n\n(The trainer hit an error; details in {crash})"
        messagebox.showinfo("humanpc trainer", msg, parent=root)
        if sys.platform == "win32":
            subprocess.Popen(["explorer", "/select,", str(final["zip"])])
    elif crash or errors:
        messagebox.showerror("humanpc trainer", f"Something went wrong. Details: {crash or base}", parent=root)
    root.destroy()
    return 0
