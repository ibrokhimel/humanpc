"""Thinking pauses inserted at word / sentence / paragraph boundaries.

The pause before a character depends on the *previous* character (the boundary we
just crossed): a space gives a short word pause, sentence punctuation a longer one,
a newline the longest.
"""

from __future__ import annotations


class PauseModel:
    def __init__(
        self,
        word_mean: float = 0.18,
        word_std: float = 0.07,
        sentence_mean: float = 0.55,
        sentence_std: float = 0.18,
        paragraph_mean: float = 1.2,
        paragraph_std: float = 0.4,
    ):
        self.word_mean = word_mean
        self.word_std = word_std
        self.sentence_mean = sentence_mean
        self.sentence_std = sentence_std
        self.paragraph_mean = paragraph_mean
        self.paragraph_std = paragraph_std

    def extra_pause(self, prev_char, rng) -> float:
        if not prev_char:
            return 0.0
        if prev_char == "\n":
            return max(0.1, rng.gauss(self.paragraph_mean, self.paragraph_std))
        if prev_char in ".!?":
            return max(0.1, rng.gauss(self.sentence_mean, self.sentence_std))
        if prev_char in ",;:":
            return max(0.0, rng.gauss(self.word_mean * 1.3, self.word_std))
        if prev_char == " ":
            return max(0.0, rng.gauss(self.word_mean, self.word_std))
        return 0.0
