"""Phase 5: record a macro, save it, and replay it.

Dry-run by default (no OS input) so it's safe to run anywhere.

    python examples/record_replay.py
"""

from __future__ import annotations

import os

from humanpc import Bot, Macro, Recorder


def main() -> None:
    bot = Bot(dry_run=True)

    # Record while executing (dry-run): each call is both done and remembered.
    rec = Recorder(bot=bot)
    rec.click("400,300").type("hello").press("tab").type("world").hotkey("ctrl", "s")

    os.makedirs("captures", exist_ok=True)
    path = os.path.join("captures", "macro.json")
    rec.save(path)
    print(f"Recorded {len(rec.steps)} steps -> {path}")
    for step in rec.steps:
        print(f"  {step}")

    # Replay it on a fresh bot.
    print("\nReplaying...")
    results = Macro.load(path).replay(bot=Bot(dry_run=True))
    print(f"Replayed {len(results)} steps; behavior trace ends in "
          f"{Bot(dry_run=True).state.value!r}-capable machine.")


if __name__ == "__main__":
    main()
