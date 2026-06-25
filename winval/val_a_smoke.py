"""A) Real input smoke test: drive Notepad with the native SendInput driver.

Opens Notepad, types the sentence, reads it back via the clipboard, and confirms
the text is exact (capitals/symbols/spacing) and that typing was NOT instant.
"""
import subprocess
import sys
import time

from humanpc import Bot
from humanpc.config import Config
from humanpc.input.sendinput_driver import SendInputDriver

import win32clipboard

TEXT = "Hello from humanpc — does this look human?"  # — == em dash


def get_clip():
    win32clipboard.OpenClipboard()
    try:
        if win32clipboard.IsClipboardFormatAvailable(win32clipboard.CF_UNICODETEXT):
            return win32clipboard.GetClipboardData(win32clipboard.CF_UNICODETEXT)
    finally:
        win32clipboard.CloseClipboard()
    return None


def set_clip(text):
    win32clipboard.OpenClipboard()
    try:
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardText(text, win32clipboard.CF_UNICODETEXT)
    finally:
        win32clipboard.CloseClipboard()


def main():
    set_clip("__sentinel__")  # so a stale clipboard can't fake a pass
    bot = Bot(driver=SendInputDriver(), config=Config(seed=11), arm=False)
    proc = bot.open_app("notepad.exe", wait="Untitled - Notepad")
    time.sleep(1.0)
    try:
        bot.focus("Untitled - Notepad")
    except Exception as e:
        print(f"[warn] focus: {e}")
    time.sleep(0.4)

    # clear anything already in the editor
    bot.hotkey("ctrl", "a")
    time.sleep(0.1)
    bot.press("delete")
    time.sleep(0.2)

    t0 = time.perf_counter()
    bot.type(TEXT)
    elapsed = time.perf_counter() - t0

    time.sleep(0.3)
    bot.hotkey("ctrl", "a")
    time.sleep(0.15)
    bot.hotkey("ctrl", "c")
    time.sleep(0.4)
    got = get_clip()

    # Notepad copies the editor text verbatim; tolerate a trailing newline only.
    got_norm = (got or "").replace("\r\n", "\n").rstrip("\n")
    exact = got_norm == TEXT
    cps = len(TEXT) / elapsed if elapsed else 0

    print("=== A) Notepad SendInput smoke ===")
    print(f"expected : {TEXT!r}")
    print(f"got      : {got!r}")
    print(f"exact match (modulo trailing newline): {exact}")
    print(f"typed {len(TEXT)} chars in {elapsed:.2f}s  ({cps:.1f} chars/s effective)")
    print(f"instant?  {'NO (human-paced)' if elapsed > 1.5 else 'SUSPICIOUSLY FAST'}")
    print(f"RESULT: {'PASS' if exact and elapsed > 1.0 else 'FAIL'}")

    bot.close()
    subprocess.run(["taskkill", "/F", "/IM", "notepad.exe"],
                   capture_output=True, text=True)


if __name__ == "__main__":
    sys.exit(main())
