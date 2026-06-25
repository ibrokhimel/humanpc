"""Colored motor noise: 1/f (pink) wander + physiological tremor.

Real hand motor output is NOT white noise. It has two signatures a frequency
analysis of the cursor path can detect:

  * **1/f "pink" noise** — low-frequency wander that is *autocorrelated* (each
    sample is correlated with the last), unlike independent Gaussian draws whose
    power spectrum is flat.
  * **Physiological tremor** — a narrowband oscillation around 8-12 Hz at small,
    roughly constant amplitude.

``PinkNoise`` is the Voss-McCartney algorithm (sum of white sources updated at
octave-spaced rates). ``Tremor`` is a phase-randomised sinusoid. The jitter
injector combines them so the path has human-like colored noise instead of the
flat-spectrum white noise that synthetic-trace classifiers key on.
"""

from __future__ import annotations

import math


class PinkNoise:
    """Voss-McCartney 1/f noise. ``next()`` returns an autocorrelated sample."""

    def __init__(self, octaves: int = 5):
        self.octaves = max(1, octaves)
        self._rows = [0.0] * self.octaves
        self._counter = 0
        self._sum = 0.0

    def next(self, rng) -> float:
        self._counter += 1
        # Update the row selected by the trailing-zero count of the counter:
        # row 0 updates every call, row 1 every 2nd, row 2 every 4th, ...
        n = self._counter
        k = 0
        while k < self.octaves - 1 and (n & 1) == 0:
            n >>= 1
            k += 1
        self._sum -= self._rows[k]
        self._rows[k] = rng.gauss(0.0, 1.0)
        self._sum += self._rows[k]
        white = rng.gauss(0.0, 1.0)
        # Normalise roughly to unit std across the contributing sources.
        return (self._sum + white) / math.sqrt(self.octaves + 1)


class Tremor:
    """Narrowband physiological tremor (~8-12 Hz), small constant amplitude (px)."""

    def __init__(self, freq_range: tuple[float, float] = (8.0, 12.0), amplitude: float = 0.35):
        self.freq_range = freq_range
        self.amplitude = amplitude
        self.freq = sum(freq_range) / 2
        self.phase = 0.0

    def reset(self, rng) -> "Tremor":
        self.freq = rng.uniform(*self.freq_range)
        self.phase = rng.uniform(0.0, 2 * math.pi)
        return self

    def at(self, t: float) -> float:
        return self.amplitude * math.sin(2 * math.pi * self.freq * t + self.phase)
