"""Live end-to-end demo: drive the REAL Notepad with human-like input.

WARNING: this moves your real mouse and types for real. It launches Notepad,
clicks into the text area, types a message with human timing, and saves a
screenshot to captures/notepad_demo.png. Throw the cursor into a screen corner
(top-left) at any time to abort (pyautogui failsafe).

    python examples/notepad_live.py
"""

from __future__ import annotations

import os
import time

from humanpc import Bot

MESSAGE = (
    "Hello from humanpc!\n"
    "This was typed by a bot - but with human timing:\n"
    "variable speed, thinking pauses, and the odd self-corrected typo.\n"
)


def main() -> None:
    bot = Bot(persona="default")

    print("Launching Notepad in 2s (move mouse to a screen corner to abort)...")
    time.sleep(2)

    bot.open_app("notepad.exe", wait="Notepad", timeout=15)
    time.sleep(1.2)  # let the window settle

    win = bot.focus("Notepad")
    r = win.rect
    print(f"Focused {win.title!r} at {r.as_tuple()}")

    # Move + click into the text area (human mouse path), then type.
    bot.click((r.x + r.width // 2, r.y + r.height // 2))
    bot.think("low")
    bot.type(MESSAGE)

    os.makedirs("captures", exist_ok=True)
    out = os.path.join("captures", "notepad_demo.png")
    bot.screenshot(out, region=r)

    print(f"Done. {len(bot.audit)} actions. Screenshot -> {out}")


if __name__ == "__main__":
    main()
