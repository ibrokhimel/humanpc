"""Key-hold (dwell) time model.

Dwell time — how long a key is physically held down — is a primary signal in
keystroke-dynamics biometrics (alongside the flight time *between* keys). The
atomic Unicode-injection path emits a key-down immediately followed by a key-up,
giving a constant ~0 ms dwell that is trivially non-human. This model produces a
realistic per-key hold that the Bot inserts between the down and up events.

Human dwell times cluster around ~70–110 ms and are right-skewed (lognormal-ish),
with slightly longer holds for modifier / edit keys (backspace, enter, shift).
Values are in seconds.
"""

from __future__ import annotations

import math

# Keys typically held a little longer than a letter tap.
_LONG_KEYS = frozenset(
    {"backspace", "enter", "return", "tab", "space", "delete", "del", "shift"}
)


class DwellModel:
    def __init__(
        self,
        median: float = 0.085,
        sigma: float = 0.30,
        long_key_factor: float = 1.25,
        min_hold: float = 0.025,
        max_hold: float = 0.30,
    ):
        self.median = median
        self.sigma = sigma
        self.long_key_factor = long_key_factor
        self.min_hold = min_hold
        self.max_hold = max_hold

    def hold(self, value: str, rng) -> float:
        """A realistic key-hold time (seconds) for a char or named key.

        Lognormal around ``median``: draw a normal in log-space and exponentiate,
        so the distribution is right-skewed like real key holds.
        """
        mu = math.log(max(1e-4, self.median))
        sample = math.exp(rng.gauss(mu, self.sigma))
        if value and value.lower() in _LONG_KEYS:
            sample *= self.long_key_factor
        return max(self.min_hold, min(self.max_hold, sample))
