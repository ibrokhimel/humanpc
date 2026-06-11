"""Typo model.

Two error shapes, both chosen because they net back to the correct text with a
single backspace (so self-correction is exact and verifiable):

  * substitution: type a neighbouring key instead of the intended one
                  -> backspace -> type intended
  * insertion:    type the intended key plus an extra neighbour
                  -> backspace the extra

The engine owns whether a correction is emitted (see ``always_correct``); this
class only decides *if* and *which*.
"""

from __future__ import annotations


class ErrorModel:
    def __init__(self, probability: float = 0.05):
        self.probability = probability

    def should_error(self, ch: str, rng) -> bool:
        # Only fumble real letters; never corrupt digits, spaces, or punctuation.
        return ch.isalpha() and rng.random() < self.probability

    def kind(self, rng) -> str:
        return rng.choice(("substitution", "insertion"))
