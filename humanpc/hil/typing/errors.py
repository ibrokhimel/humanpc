"""Typo model.

Four error shapes, each reversible with backspaces so self-correction is exact
and verifiable (the engine owns whether a correction is emitted via
``always_correct``):

  * substitution: a neighbouring key instead of the intended one
                  -> backspace -> intended
  * insertion:    the intended key plus an extra neighbour
                  -> backspace the extra
  * transposition: the next character typed before the current one (the single
                   most common real typo) -> two backspaces -> retype in order
  * doubling:     the intended key struck twice -> backspace the repeat

This class only decides *if* an error happens and *which* kind.
"""

from __future__ import annotations

# Relative likelihood of each kind. Transpositions dominate real typing.
_KINDS = ("transposition", "substitution", "insertion", "doubling")
_WEIGHTS = (0.4, 0.3, 0.15, 0.15)


class ErrorModel:
    def __init__(self, probability: float = 0.05):
        self.probability = probability

    def should_error(self, ch: str, rng) -> bool:
        # Only fumble real letters; never corrupt digits, spaces, or punctuation.
        return ch.isalpha() and rng.random() < self.probability

    def kind(self, rng) -> str:
        return rng.choices(_KINDS, weights=_WEIGHTS)[0]
