"""The Bot facade: the synchronous, script-facing public API.

Phase 0 implements raw-coordinate actions with a simple smoothstep-eased, stepped
move. This is intentionally a placeholder: Phase 1 swaps the movement/timing here
for the Human Interaction Layer (Bezier paths, Fitts-law velocity, typing rhythm),
and Phase 2 adds string/image *targets* on top of the coordinate primitives below.

Every action funnels through ``_begin`` (safety precheck) and ``_end`` (audit), so
the kill-switch, action cap, and audit trail apply uniformly.
"""

from __future__ import annotations

import random
import time
from contextlib import contextmanager

from .config import Config, Persona, get_persona
from .geometry import Point, to_point
from .hil import (
    HumanTimingManager,
    HumanTypingEngine,
    MouseTrajectoryEngine,
    plan_scroll,
)
from .input import NullDriver, default_driver
from .perception.dpi import set_dpi_awareness
from .safety import AuditLog, KillSwitch, SafetyGuard


class Bot:
    def __init__(
        self,
        persona: str = "default",
        *,
        dry_run: bool = False,
        config: Config | None = None,
        driver=None,
        audit: AuditLog | None = None,
        killswitch: KillSwitch | None = None,
        arm: bool = True,
    ):
        self.config = config or Config()
        if persona:
            self.config.persona = persona
        self.dry_run = dry_run or self.config.dry_run

        self._persona: Persona = get_persona(self.config.persona)
        self._rng = random.Random(self.config.seed)
        self.dpi_mode = set_dpi_awareness()

        self.audit = audit if audit is not None else AuditLog(
            path=self.config.audit_path, enabled=self.config.audit_enabled
        )
        self.killswitch = killswitch if killswitch is not None else KillSwitch(
            hotkey=self.config.kill_hotkey
        )
        self.guard = SafetyGuard(self.killswitch, max_actions=self.config.max_actions)

        # Human Interaction Layer engines (pure planners; cheap to construct).
        self._mouse = MouseTrajectoryEngine()
        self._typing = HumanTypingEngine(
            errors_enabled=self.config.typing_errors,
            always_correct=self.config.always_correct_typing,
        )
        self._timing = HumanTimingManager()

        # Dry-run never touches the OS. Real driver is created lazily on first use.
        self._driver = NullDriver() if self.dry_run else driver

        if arm and not self.dry_run:
            self.killswitch.start()

    # --- properties -------------------------------------------------------
    @property
    def driver(self):
        if self._driver is None:
            self._driver = default_driver(failsafe=self.config.failsafe)
        return self._driver

    @property
    def current_persona(self) -> Persona:
        return self._persona

    def position(self) -> tuple[int, int]:
        return self.driver.position()

    # --- internals --------------------------------------------------------
    def _begin(self, action: str) -> None:
        self.guard.precheck(action)

    def _end(self, action: str, **fields) -> None:
        self.audit.record(
            action, persona=self._persona.name, dry_run=self.dry_run, **fields
        )

    def _sleep(self, seconds: float) -> None:
        if self.dry_run or seconds <= 0:
            return
        time.sleep(seconds)

    # --- personas ---------------------------------------------------------
    @contextmanager
    def persona(self, name: str):
        """Temporarily switch persona: ``with bot.persona("careful"): ...``"""
        previous = self._persona
        self._persona = get_persona(name)
        try:
            yield self
        finally:
            self._persona = previous

    # --- mouse ------------------------------------------------------------
    def move_to(self, target, *, target_size: tuple[int, int] = (20, 20)) -> "Bot":
        point = to_point(target)
        self._begin("move_to")
        start = Point(*self.position())
        plan = self._mouse.plan(
            start,
            point,
            rng=self._rng,
            target_size=target_size,
            speed_multiplier=self._persona.speed_multiplier,
        )
        for step in plan:
            self.killswitch.check()
            self.driver.move(*step.point.as_int())
            self._sleep(step.dt)
        self._end("move_to", x=round(point.x), y=round(point.y))
        return self

    def click(self, target=None, *, button: str = "left", clicks: int = 1) -> "Bot":
        if target is not None:
            self.move_to(target)
        self._begin("click")
        for n in range(clicks):
            self.killswitch.check()
            self.driver.mouse_down(button)
            self._sleep(self._rng.uniform(*self._persona.click_dwell))
            self.driver.mouse_up(button)
            if n < clicks - 1:
                self._sleep(self._rng.uniform(0.08, 0.18))
        self._end("click", button=button, clicks=clicks)
        return self

    def double_click(self, target=None, *, button: str = "left") -> "Bot":
        return self.click(target, button=button, clicks=2)

    def right_click(self, target=None) -> "Bot":
        return self.click(target, button="right", clicks=1)

    def scroll(self, amount: int, *, at=None) -> "Bot":
        if at is not None:
            self.move_to(at)
        self._begin("scroll")
        for delta, dt in plan_scroll(amount, self._rng):
            self.killswitch.check()
            if delta:
                self.driver.scroll(0, delta)
            self._sleep(dt)
        self._end("scroll", amount=int(amount))
        return self

    # --- keyboard ---------------------------------------------------------
    def type(self, text: str) -> "Bot":
        self._begin("type")
        base_wpm = max(20.0, self._persona.type_cps * 12)  # cps -> wpm (~5 chars/word)
        for event in self._typing.plan(text, self._rng, base_wpm=base_wpm):
            self.killswitch.check()
            self._sleep(event.delay)
            if event.kind == "char":
                self.driver.write_char(event.value)
            else:
                self.driver.tap(event.value)
        self._end("type", length=len(text))
        return self

    def press(self, *keys: str) -> "Bot":
        for key in keys:
            self._begin("press")
            self.killswitch.check()
            self.driver.key_down(key)
            self._sleep(self._rng.uniform(0.03, 0.09))
            self.driver.key_up(key)
            self._end("press", key=key)
            self._sleep(self._rng.uniform(0.05, 0.12))
        return self

    def hotkey(self, *keys: str) -> "Bot":
        """Chord: press keys in order, release in reverse (e.g. ctrl+c)."""
        self._begin("hotkey")
        for key in keys:
            self.driver.key_down(key)
            self._sleep(self._rng.uniform(0.02, 0.06))
        self._sleep(self._rng.uniform(0.03, 0.08))
        for key in reversed(keys):
            self.driver.key_up(key)
        self._end("hotkey", keys=list(keys))
        return self

    # --- deliberation -----------------------------------------------------
    def think(self, complexity: str = "medium") -> "Bot":
        """Pause as if deciding. complexity: low | medium | high | very_high."""
        self._begin("think")
        self._sleep(self._timing.thinking_delay(complexity, self._rng))
        self._end("think", complexity=complexity)
        return self

    def read(self, content, *, complexity: float = 1.0) -> "Bot":
        """Pause as if reading. ``content`` may be text or a character count."""
        self._begin("read")
        self._sleep(self._timing.reading_delay(content, self._rng, complexity))
        chars = content if isinstance(content, int) else len(str(content))
        self._end("read", chars=chars)
        return self
