"""Phase 0 smoke test.

Default run is SAFE (dry-run): it plans actions and prints the audit trail without
moving your mouse or typing anything.

    python examples/phase0_smoke.py

Pass --real to actually drive the mouse/keyboard (3-second countdown first). Throw
the cursor into a screen corner at any time to abort (pyautogui failsafe), or press
Ctrl+Alt+Q if the `keyboard` package is installed.

    python examples/phase0_smoke.py --real
"""

from __future__ import annotations

import sys
import time

import humanpc


def main() -> None:
    real = "--real" in sys.argv

    if real:
        print("REAL mode: will move the mouse and type. Starting in...")
        for n in (3, 2, 1):
            print(f"  {n}")
            time.sleep(1)
        bot = humanpc.Bot(persona="careful")
    else:
        print("DRY-RUN mode (no OS input). Pass --real to actually execute.\n")
        bot = humanpc.Bot(dry_run=True)

    (
        bot.move_to((600, 400))
        .click()
        .type("hello from humanpc")
        .press("enter")
        .hotkey("ctrl", "a")
        .scroll(-3)
    )

    print(f"DPI mode: {bot.dpi_mode}")
    print(f"Actions recorded: {len(bot.audit)}")
    for entry in bot.audit.entries:
        action = entry.pop("action")
        entry.pop("ts", None)
        print(f"  {action:<10} {entry}")


if __name__ == "__main__":
    main()
