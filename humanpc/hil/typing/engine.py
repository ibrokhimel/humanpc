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
from .keys import neighbor
from .pause import PauseModel
from .speed import SpeedModel


@dataclass
class KeyEvent:
    kind: str    # "char" | "key"
    value: str   # the character, or a key name like "backspace"
    delay: float  # seconds to wait BEFORE performing this event
    dwell: float = 0.0  # seconds to HOLD the key down (down -> hold -> up)


class HumanTypingEngine:
    def __init__(
        self,
        errors_enabled: bool = True,
        always_correct: bool = True,
        error_probability: float = 0.05,
        notice_probability: float = 1.0,
        reaction: tuple[float, float] = (0.18, 0.42),
        correction: tuple[float, float] = (0.05, 0.13),
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
        """Build a KeyEvent, attaching a realistic key-hold (dwell) time."""
        return KeyEvent(kind, value, delay, self.dwell.hold(value, rng))

    def plan(self, text: str, rng, base_wpm: float = 72.0) -> list[KeyEvent]:
        events: list[KeyEvent] = []
        prev = None
        for i, ch in enumerate(text):
            word = self._word_at(text, i)
            delay = self.speed.char_delay(ch, prev, word, i, base_wpm, rng)
            delay += self.pause.extra_pause(prev, rng)

            if self.errors_enabled and self.errors.should_error(ch, rng):
                corrected = self.always_correct or rng.random() < self.notice_probability
                if self.errors.kind(rng) == "substitution":
                    events.append(self._ev("char", neighbor(ch, rng), delay, rng))
                    if corrected:
                        events.append(self._ev("key", "backspace", rng.uniform(*self.reaction), rng))
                        events.append(self._ev("char", ch, rng.uniform(*self.correction), rng))
                else:  # insertion
                    events.append(self._ev("char", ch, delay, rng))
                    events.append(self._ev("char", neighbor(ch, rng), rng.uniform(*self.correction), rng))
                    if corrected:
                        events.append(self._ev("key", "backspace", rng.uniform(*self.reaction), rng))
            else:
                events.append(self._ev("char", ch, delay, rng))

            prev = ch
        return events
