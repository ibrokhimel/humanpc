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
    def move_to(self, target) -> "Bot":
        point = to_point(target)
        self._begin("move_to")
        sx, sy = self.position()
        steps = max(1, self.config.move_steps)
        duration = self._persona.move_duration * self._persona.speed_multiplier
        per_step = duration / steps
        for i in range(1, steps + 1):
            self.killswitch.check()
            t = i / steps
            ease = t * t * (3 - 2 * t)  # smoothstep; HIL replaces this in Phase 1
            x = sx + (point.x - sx) * ease
            y = sy + (point.y - sy) * ease
            self.driver.move(round(x), round(y))
            self._sleep(per_step)
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
        self.driver.scroll(0, int(amount))
        self._end("scroll", amount=int(amount))
        return self

    # --- keyboard ---------------------------------------------------------
    def type(self, text: str) -> "Bot":
        self._begin("type")
        base = 1.0 / max(0.1, self._persona.type_cps)
        for ch in text:
            self.killswitch.check()
            self.driver.write_char(ch)
            self._sleep(max(0.0, self._rng.gauss(base, base * 0.3)))
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
