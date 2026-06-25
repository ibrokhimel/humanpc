"""HumanTimingManager — thinking, reading, and decision delays.

The mouse and typing engines own their own micro-timing; this manager covers the
*between*-action pauses: deliberating before a decision, reading a screen before
acting. Reading is modelled as eye **fixations + saccades + regressions** rather
than a flat words/WPM divide, and decisions follow the **Hick-Hyman law** (choice
time grows with the log of the number of alternatives).
"""

from __future__ import annotations

import math


class HumanTimingManager:
    THINK_BASE = {"low": 0.3, "medium": 0.7, "high": 1.6, "very_high": 3.0}

    def __init__(
        self,
        read_wpm: tuple[float, float] = (200.0, 250.0),
        fixation_dur: tuple[float, float] = (0.18, 0.28),
        fixations_per_word: float = 0.9,    # skilled readers skip ~25% of words
        regression_rate: float = 0.12,      # ~12% of saccades re-read
        scan_fixations_per_word: float = 0.35,  # scanning a UI, not reading prose
        hick_a: float = 0.20,
        hick_b: float = 0.16,
    ):
        self.read_wpm = read_wpm
        self.fixation_dur = fixation_dur
        self.fixations_per_word = fixations_per_word
        self.regression_rate = regression_rate
        self.scan_fixations_per_word = scan_fixations_per_word
        self.hick_a = hick_a
        self.hick_b = hick_b

    def thinking_delay(self, complexity: str, rng) -> float:
        base = self.THINK_BASE.get(complexity, 0.7)
        return max(0.05, rng.gauss(base, base * 0.25))

    def decision_delay(self, n_choices: int, rng) -> float:
        """Hick-Hyman: choice reaction time = a + b * log2(n + 1), with variance."""
        n = max(1, int(n_choices))
        mt = self.hick_a + self.hick_b * math.log2(n + 1)
        return max(0.05, mt * math.exp(rng.gauss(0.0, 0.2)))

    def reading_delay(self, content, rng, complexity: float = 1.0, *, scan: bool = False) -> float:
        """Time to read/scan ``content`` (a char count or the text itself).

        Modelled as fixations * fixation duration, inflated by regressions, then
        scaled by ``complexity``. Scanning a familiar UI uses far fewer fixations
        per word than reading novel prose.
        """
        n = content if isinstance(content, int) else len(str(content))
        words = max(1.0, n / 5)
        fpw = self.scan_fixations_per_word if scan else self.fixations_per_word
        fixations = words * fpw
        dur = rng.uniform(*self.fixation_dur)
        seconds = fixations * dur * (1.0 + self.regression_rate) * complexity
        seconds *= math.exp(rng.gauss(0.0, 0.18))  # right-skewed variation
        return max(0.05, seconds)
