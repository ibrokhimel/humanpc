"""Per-character delay model: base WPM with lognormal variance, fatigue, word
difficulty, and digraph (bigram / hand / finger) structure.

Inter-key intervals in real typing are lognormal (right-skewed, heavy-tailed),
not Gaussian, and depend on the specific key pair: same-finger digraphs are slow,
alternating-hand digraphs are fast (rollover). ``session_fatigue`` lets the Bot
pass an accumulated, cross-action slowdown (see the persona/session model)."""

from __future__ import annotations

import math

from .keys import COMMON_BIGRAMS, COMMON_WORDS, alternating_hands, same_finger


class SpeedModel:
    def __init__(
        self,
        log_sigma: float = 0.22,
        fatigue_factor: float = 1.0004,
        common_word_boost: float = 0.7,
        complex_word_penalty: float = 1.3,
        bigram_boost: float = 0.55,
        same_finger_penalty: float = 1.4,
        alt_hand_boost: float = 0.85,
    ):
        self.log_sigma = log_sigma
        self.fatigue_factor = fatigue_factor
        self.common_word_boost = common_word_boost
        self.complex_word_penalty = complex_word_penalty
        self.bigram_boost = bigram_boost
        self.same_finger_penalty = same_finger_penalty
        self.alt_hand_boost = alt_hand_boost

    def char_delay(self, ch, prev, word, typed_count, base_wpm, rng, session_fatigue=1.0) -> float:
        cpm = base_wpm * 5  # ~5 chars per word
        delay = 60.0 / cpm
        # Lognormal multiplier: right-skewed, heavy-tailed like real IKIs.
        delay *= math.exp(rng.gauss(0.0, self.log_sigma))
        delay *= self.fatigue_factor ** typed_count  # within-action fatigue
        delay *= max(0.5, session_fatigue)            # cross-action fatigue (persona/session)

        if word:
            lw = word.lower()
            if lw in COMMON_WORDS:
                delay *= self.common_word_boost
            elif len(word) > 8 or any(c in lw for c in "qxzj"):
                delay *= self.complex_word_penalty

        if prev:
            if (prev + ch).lower() in COMMON_BIGRAMS:
                delay *= self.bigram_boost
            if same_finger(prev, ch):
                delay *= self.same_finger_penalty
            elif alternating_hands(prev, ch):
                delay *= self.alt_hand_boost

        return max(0.012, delay)
