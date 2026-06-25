"""Individual — a sampled, persisted behavioural fingerprint.

The gap this closes: the engines drew every action from the *same* hardcoded
distributions, so (a) every bot instance was the same statistical "average human"
and (b) there was no within-session consistency — each action was an independent
re-roll. Real variability is the opposite: HIGH variance *between* people (stable
traits) but LOW, *autocorrelated* variance *within* one person.

This module provides both halves:

  * ``Individual`` — a trait vector sampled ONCE from a population and reused for
    every action, so each bot is a distinct, consistent person. Traits are
    **correlated** through a latent skill factor (a faster typist tends to make
    fewer errors and hold keys more briefly) — independent draws would produce
    impossible humans.
  * ``ActionTempo`` — an AR(1) process so consecutive actions are correlated: the
    bot drifts into fast/slow streaks instead of re-rolling tempo each time.

Tier 4 layers on top of Tier 3's ``SessionState`` (warm-up/fatigue drift) and the
coarse ``Persona`` presets (config.py): persona = category, Individual = identity.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .mouse import (
    BezierPathGenerator,
    JitterInjector,
    MouseTrajectoryEngine,
    OvershootSimulator,
    VelocityProfile,
)
from .typing import DwellModel, HumanTypingEngine


@dataclass(frozen=True)
class Individual:
    base_wpm: float
    error_rate: float
    dwell_median: float
    reaction: float
    curve_strength: float
    jitter_scale: float
    overshoot_prob: float
    move_speed: float       # multiplies movement time (<1 = faster)
    skill: float            # latent factor, kept for reference

    def build_mouse_engine(self) -> MouseTrajectoryEngine:
        return MouseTrajectoryEngine(
            bezier=BezierPathGenerator(curve_strength=self.curve_strength),
            velocity=VelocityProfile(),
            jitter=JitterInjector(
                base_amplitude=0.6 * self.jitter_scale,
                tremor_amplitude=0.35 * self.jitter_scale,
            ),
            overshoot=OvershootSimulator(probability=self.overshoot_prob),
        )

    def build_typing_engine(self, *, errors_enabled: bool = True, always_correct: bool = True) -> HumanTypingEngine:
        eng = HumanTypingEngine(
            errors_enabled=errors_enabled,
            always_correct=always_correct,
            error_probability=self.error_rate,
            reaction=(self.reaction * 0.8, self.reaction * 1.6),
        )
        eng.dwell = DwellModel(median=self.dwell_median)
        return eng


def sample_individual(rng) -> Individual:
    """Draw one person from the population. Traits correlate via a latent skill z."""
    z = rng.gauss(0.0, 1.0)  # latent skill / speed (higher = faster, cleaner)
    base_wpm = min(120.0, max(20.0, 52.0 + 16.0 * z + rng.gauss(0.0, 6.0)))
    error_rate = min(0.18, max(0.005, math.exp(math.log(0.045) - 0.3 * z + rng.gauss(0.0, 0.3))))
    dwell_median = min(0.16, max(0.04, 0.095 - 0.014 * z + rng.gauss(0.0, 0.012)))
    reaction = min(0.5, max(0.12, 0.26 - 0.04 * z + rng.gauss(0.0, 0.04)))
    curve_strength = min(0.6, max(0.12, 0.30 + rng.gauss(0.0, 0.08)))
    jitter_scale = min(1.8, max(0.4, rng.gauss(1.0, 0.25)))
    overshoot_prob = min(0.7, max(0.1, 0.35 + rng.gauss(0.0, 0.12)))
    move_speed = min(1.8, max(0.5, 1.0 - 0.12 * z + rng.gauss(0.0, 0.12)))
    return Individual(
        base_wpm=base_wpm,
        error_rate=error_rate,
        dwell_median=dwell_median,
        reaction=reaction,
        curve_strength=curve_strength,
        jitter_scale=jitter_scale,
        overshoot_prob=overshoot_prob,
        move_speed=move_speed,
        skill=z,
    )


class ActionTempo:
    """AR(1) tempo: each action's pace correlates with the previous one.

    ``value`` is a lognormal multiplier around 1.0; advancing it produces
    fast/slow streaks (autocorrelation) rather than independent re-rolls.
    """

    def __init__(self, rho: float = 0.7, sigma: float = 0.18):
        self.rho = rho
        self.sigma = sigma
        self.x = 0.0
        self.value = 1.0

    def advance(self, rng) -> float:
        self.x = self.rho * self.x + math.sqrt(1.0 - self.rho ** 2) * rng.gauss(0.0, self.sigma)
        self.value = math.exp(self.x)
        return self.value
