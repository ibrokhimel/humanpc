"""Phase 2 targeting demo.

Shows how a single verb accepts many target kinds. The coordinate/region cases run
anywhere (dry-run, no screen). The string/image cases need a real desktop and the
optional backends, so they're shown but guarded behind --real.

    python examples/targeting_demo.py          # safe: coords + region only
    python examples/targeting_demo.py --real    # also try text/image on the live screen
"""

from __future__ import annotations

import sys

import humanpc
from humanpc import Bot, Image, Region


def main() -> None:
    real = "--real" in sys.argv
    bot = Bot() if real else Bot(dry_run=True)

    # These resolve locally — no dependencies, no screen needed.
    bot.click((400, 300))                 # exact point
    bot.click(Region(100, 100, 60, 24))   # a rectangle -> clicks its centre

    if not real:
        print("DRY-RUN. Targets resolved & planned without touching the OS:")
        for e in bot.audit.entries:
            print(f"  {e['action']:<9} via={e.get('via', '-'):<7} {e}")
        print("\nRun with --real to also try text/image targets on the live screen.")
        return

    # These need a live desktop + the optional backends (UIA / OCR / OpenCV).
    bot.click("File")                     # text -> UIA name, then OCR fallback
    bot.click(Image("button.png"))        # picture -> OpenCV template match
    if bot.exists("Save"):
        bot.click("Save")
    bot.wait_for("Done", timeout=15)      # poll until it appears


if __name__ == "__main__":
    main()
