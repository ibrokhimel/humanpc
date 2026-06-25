"""SessionState — cross-action temporal realism: warm-up, fatigue, distraction.

A real person doesn't act at a constant pace. They start a session a little slow
(**warm-up**), settle into a rhythm, then gradually slow and grow more error-prone
over minutes/hours (**fatigue / vigilance decrement**), and occasionally **get
distracted** for a beat. The old engines drew every action independently from a
fixed distribution, so none of this carried across actions — and the only fatigue
present reset on every keystroke call.

``SessionState`` lives on the Bot for the whole session. ``pace_multiplier``
combines warm-up and fatigue into a >1 slowdown applied to thinking/reading/typing;
``maybe_distraction`` occasionally injects an extra pause. Tier 4's persona scales
these baselines per individual.
"""

from __future__ import annotations

import math
import time


class SessionState:
    def __init__(
        self,
        *,
        warmup_amplitude: float = 0.25,   # +25% slower at the very start
        warmup_tau: float = 30.0,         # seconds for warm-up to fade
        fatigue_per_minute: float = 0.04,  # gradual slowdown per minute on task
        fatigue_cap: float = 0.6,         # max added slowdown from fatigue
        distraction_prob: float = 0.02,   # chance per action of a distraction
        distraction_range: tuple[float, float] = (1.5, 6.0),
        clock=time.monotonic,
    ):
        self.warmup_amplitude = warmup_amplitude
        self.warmup_tau = warmup_tau
        self.fatigue_per_minute = fatigue_per_minute
        self.fatigue_cap = fatigue_cap
        self.distraction_prob = distraction_prob
        self.distraction_range = distraction_range
        self._clock = clock
        self._start = clock()
        self.actions = 0

    def elapsed(self) -> float:
        return max(0.0, self._clock() - self._start)

    def warmup_factor(self, elapsed: float | None = None) -> float:
        e = self.elapsed() if elapsed is None else elapsed
        return 1.0 + self.warmup_amplitude * math.exp(-e / self.warmup_tau)

    def fatigue_factor(self, elapsed: float | None = None) -> float:
        e = self.elapsed() if elapsed is None else elapsed
        return 1.0 + min(self.fatigue_cap, self.fatigue_per_minute * (e / 60.0))

    def pace_multiplier(self, elapsed: float | None = None) -> float:
        """Combined warm-up * fatigue slowdown (>= 1.0)."""
        return self.warmup_factor(elapsed) * self.fatigue_factor(elapsed)

    def tick(self) -> None:
        """Record that an action happened (advances the action counter)."""
        self.actions += 1

    def maybe_distraction(self, rng) -> float:
        """Occasionally return an extra 'got distracted' pause (seconds), else 0."""
        if rng.random() < self.distraction_prob:
            return rng.uniform(*self.distraction_range)
        return 0.0
