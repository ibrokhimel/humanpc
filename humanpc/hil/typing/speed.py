"""Per-character delay model: base WPM with variance, fatigue, word difficulty,
and bigram acceleration."""

from __future__ import annotations

from .keys import COMMON_BIGRAMS, COMMON_WORDS


class SpeedModel:
    def __init__(
        self,
        wpm_std: float = 10.0,
        fatigue_factor: float = 1.0004,
        common_word_boost: float = 0.7,
        complex_word_penalty: float = 1.3,
        bigram_boost: float = 0.55,
    ):
        self.wpm_std = wpm_std
        self.fatigue_factor = fatigue_factor
        self.common_word_boost = common_word_boost
        self.complex_word_penalty = complex_word_penalty
        self.bigram_boost = bigram_boost

    def char_delay(self, ch, prev, word, typed_count, base_wpm, rng) -> float:
        cpm = base_wpm * 5  # ~5 chars per word
        delay = 60.0 / cpm
        delay *= max(0.3, rng.gauss(1.0, self.wpm_std / base_wpm))
        delay *= self.fatigue_factor ** typed_count

        if word:
            lw = word.lower()
            if lw in COMMON_WORDS:
                delay *= self.common_word_boost
            elif len(word) > 8 or any(c in lw for c in "qxzj"):
                delay *= self.complex_word_penalty

        if prev and (prev + ch).lower() in COMMON_BIGRAMS:
            delay *= self.bigram_boost

        return max(0.012, delay)
