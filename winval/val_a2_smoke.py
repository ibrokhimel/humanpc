"""A) Real input smoke test — non-destructive, reads back from disk.

Opens a dedicated temp file in Notepad, types the sentence via the native
SendInput driver, saves (Ctrl+S, no dialog), and reads the FILE back to confirm
exact text. Does not touch your other Notepad tabs and does not taskkill Notepad.
"""
import os
import tempfile
import time

import win32con
import win32gui

from humanpc import Bot
from humanpc.config import Config
from humanpc.input.sendinput_driver import SendInputDriver

TEXT = "Hello from humanpc — does this look human?"  # — == em dash
path = os.path.join(tempfile.gettempdir(), "humanpc_notepad_smoke.txt")
with open(path, "w", encoding="utf-8"):
    pass  # create empty


def notepad_windows():
    out = []
    def cb(h, _):
        if win32gui.IsWindowVisible(h):
            t = win32gui.GetWindowText(h)
            if t.endswith("- Notepad"):
                out.append((h, t))
        return True
    win32gui.EnumWindows(cb, None)
    return out


bot = Bot(driver=SendInputDriver(), config=Config(seed=11), arm=False)
bot.open_app("notepad.exe", args=[path])

hwnd, title = None, None
deadline = time.time() + 15
while time.time() < deadline:
    for h, t in notepad_windows():
        if "humanpc_notepad_smoke" in t:
            hwnd, title = h, t
            break
    if hwnd:
        break
    time.sleep(0.3)
if hwnd is None:
    np = notepad_windows()
    hwnd, title = (np[0] if np else (None, None))

print("=== A) Notepad SendInput smoke (read back from disk) ===")
print(f"notepad window: {hwnd}  title={title!r}")
try:
    win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
    win32gui.SetForegroundWindow(hwnd)
except Exception as e:
    print(f"[warn] focus: {e}")
time.sleep(0.7)

t0 = time.perf_counter()
bot.type(TEXT)
elapsed = time.perf_counter() - t0
time.sleep(0.3)
bot.hotkey("ctrl", "s")   # file already has a path -> silent save
time.sleep(0.8)

with open(path, encoding="utf-8-sig") as f:
    got = f.read()
got_norm = got.replace("\r\n", "\n").rstrip("\n")
exact = got_norm == TEXT

print(f"expected : {TEXT!r}")
print(f"file says: {got!r}")
print(f"exact match (capitals/symbols/spacing/em-dash): {exact}")
print(f"typed {len(TEXT)} chars in {elapsed:.2f}s  (instant? {'NO' if elapsed > 1.0 else 'YES'})")
print(f"A RESULT: {'PASS' if exact and elapsed > 1.0 else 'FAIL'}")
print(f"(left the saved file open in a Notepad tab: {path})")
bot.close()
