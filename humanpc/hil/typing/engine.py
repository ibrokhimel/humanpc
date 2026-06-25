"""HumanTypingEngine — turns text into a stream of ``KeyEvent``s (chars + the odd
backspace) with human timing.

Reliability note: with ``always_correct=True`` (the default) every injected typo is
immediately followed by its correction, so applying the event stream always
reproduces the input text exactly. This gives human-looking hesitation/backspacing
without ever risking a wrong value in a form field. Set ``always_correct=False``
(and ``notice_probability < 1``) only for evasion scenarios where leaving the
occasional uncorrected typo is acceptable.
"""

from __future__ import annotations

from dataclasses import dataclass

from .dwell import DwellModel
from .errors import ErrorModel
from .keys import needs_shift, neighbor
from .pause import PauseModel
from .speed import SpeedModel


@dataclass
class KeyEvent:
    kind: str    # "char" | "key"
    value: str   # the character, or a key name like "backspace"
    delay: float  # seconds to wait BEFORE performing this event
    dwell: float = 0.0  # seconds to HOLD the key down (down -> hold -> up)
    modifiers: tuple = ()  # held modifier keys, e.g. ("shift",) for a capital


class HumanTypingEngine:
    def __init__(
        self,
        errors_enabled: bool = True,
        always_correct: bool = True,
        error_probability: float = 0.05,
        notice_probability: float = 1.0,
        reaction: tuple[float, float] = (0.18, 0.42),
        correction: tuple[float, float] = (0.05, 0.13),
        model_shift: bool = True,
    ):
        self.speed = SpeedModel()
        self.pause = PauseModel()
        self.dwell = DwellModel()
        self.errors = ErrorModel(error_probability)
        self.errors_enabled = errors_enabled
        self.always_correct = always_correct
        self.notice_probability = notice_probability
        self.reaction = reaction
        self.correction = correction
        self.model_shift = model_shift

    @staticmethod
    def _word_at(text: str, i: int) -> str:
        start = i
        while start > 0 and not text[start - 1].isspace():
            start -= 1
        end = i
        while end < len(text) and not text[end].isspace():
            end += 1
        return text[start:end]

    def _ev(self, kind: str, value: str, delay: float, rng) -> KeyEvent:
        """Build a KeyEvent with a realistic key-hold (dwell) and shift modifier."""
        mods = ("shift",) if (kind == "char" and self.model_shift and needs_shift(value)) else ()
        return KeyEvent(kind, value, delay, self.dwell.hold(value, rng), mods)

    def _reaction(self, rng) -> float:
        return rng.uniform(*self.reaction)

    def _correction(self, rng) -> float:
        return rng.uniform(*self.correction)

    def plan(self, text: str, rng, base_wpm: float = 72.0, session_fatigue: float = 1.0) -> list[KeyEvent]:
        events: list[KeyEvent] = []
        prev = None
        i, n = 0, len(text)
        while i < n:
            ch = text[i]
            word = self._word_at(text, i)
            delay = self.speed.char_delay(ch, prev, word, i, base_wpm, rng, session_fatigue)
            delay += self.pause.extra_pause(prev, rng)

            handled = False
            if self.errors_enabled and self.errors.should_error(ch, rng):
                corrected = self.always_correct or rng.random() < self.notice_probability
                kind = self.errors.kind(rng)

                if kind == "transposition" and i + 1 < n and text[i + 1].isalpha():
                    nxt = text[i + 1]
                    events.append(self._ev("char", nxt, delay, rng))            # next typed early
                    events.append(self._ev("char", ch, self._correction(rng), rng))
                    if corrected:
                        events.append(self._ev("key", "backspace", self._reaction(rng), rng))
                        events.append(self._ev("key", "backspace", self._correction(rng), rng))
                        events.append(self._ev("char", ch, self._correction(rng), rng))
                        events.append(self._ev("char", nxt, self._correction(rng), rng))
                    prev = nxt
                    i += 2
                    continue
                elif kind == "doubling":
                    events.append(self._ev("char", ch, delay, rng))
                    events.append(self._ev("char", ch, self._correction(rng), rng))  # accidental repeat
                    if corrected:
                        events.append(self._ev("key", "backspace", self._reaction(rng), rng))
                    handled = True
                elif kind == "substitution":
                    events.append(self._ev("char", neighbor(ch, rng), delay, rng))
                    if corrected:
                        events.append(self._ev("key", "backspace", self._reaction(rng), rng))
                        events.append(self._ev("char", ch, self._correction(rng), rng))
                    handled = True
                elif kind == "insertion":
                    events.append(self._ev("char", ch, delay, rng))
                    events.append(self._ev("char", neighbor(ch, rng), self._correction(rng), rng))
                    if corrected:
                        events.append(self._ev("key", "backspace", self._reaction(rng), rng))
                    handled = True

            if not handled:
                events.append(self._ev("char", ch, delay, rng))

            prev = ch
            i += 1
        return events
