"""HumanTimingManager — thinking and reading delays.

A small, sync port of the blueprint's timing/reading sections. The mouse and
typing engines own their own micro-timing; this manager covers the *between*
actions pauses (deliberating before a decision, reading a screen before acting).
"""

from __future__ import annotations


class HumanTimingManager:
    THINK_BASE = {"low": 0.3, "medium": 0.7, "high": 1.6, "very_high": 3.0}

    def __init__(self, read_wpm: tuple[float, float] = (200.0, 250.0)):
        self.read_wpm = read_wpm

    def thinking_delay(self, complexity: str, rng) -> float:
        base = self.THINK_BASE.get(complexity, 0.7)
        return max(0.05, rng.gauss(base, base * 0.25))

    def reading_delay(self, content, rng, complexity: float = 1.0) -> float:
        """``content`` may be a char count (int) or the text/string itself."""
        n = content if isinstance(content, int) else len(str(content))
        words = max(1.0, n / 5)
        wpm = rng.uniform(*self.read_wpm)
        seconds = (words / wpm) * 60 * complexity * rng.uniform(0.8, 1.25)
        return max(0.05, seconds)
