"""Idle mouse drift.

Real users nudge the cursor while reading or thinking; a frozen cursor between
actions is a strong bot signal. ``IdleDriftLoop`` runs on a daemon thread and,
during idle periods, performs small subtle drifts. The planner
(``IdleMovementGenerator``) is pure; the loop's ``tick()`` is directly testable
without threads.
"""

from __future__ import annotations

import threading
import time

from ..geometry import Point


class IdleMovementGenerator:
    def __init__(self, drift_range: float = 18.0, steps: int = 16,
                 step_delay: tuple[float, float] = (0.03, 0.08)):
        self.drift_range = drift_range
        self.steps = steps
        self.step_delay = step_delay

    def drift_target(self, current: Point, rng) -> Point:
        return Point(
            current.x + rng.gauss(0, self.drift_range),
            current.y + rng.gauss(0, self.drift_range),
        )

    def subtle_path(self, start: Point, target: Point, rng) -> list[tuple[Point, float]]:
        n = max(2, self.steps)
        out = []
        for i in range(1, n + 1):
            t = i / n
            ease = t * t * (3 - 2 * t)  # smoothstep
            out.append((
                Point(start.x + (target.x - start.x) * ease,
                      start.y + (target.y - start.y) * ease),
                rng.uniform(*self.step_delay),
            ))
        return out


class IdleDriftLoop:
    def __init__(
        self,
        driver,
        idle_seconds,
        rng,
        *,
        gen: IdleMovementGenerator | None = None,
        threshold: float = 2.0,
        probability: float = 0.4,
        check_interval: tuple[float, float] = (0.5, 2.0),
        sleep=time.sleep,
    ):
        self.driver = driver
        self.idle_seconds = idle_seconds  # callable -> seconds since last action
        self.rng = rng
        self.gen = gen or IdleMovementGenerator()
        self.threshold = threshold
        self.probability = probability
        self.check_interval = check_interval
        self._sleep = sleep
        self._stop = threading.Event()
        self._thread = None

    def tick(self) -> bool:
        """One idle check. Drifts (and returns True) if idle long enough."""
        if self.idle_seconds() >= self.threshold and self.rng.random() < self.probability:
            self._drift()
            return True
        return False

    def _drift(self) -> None:
        current = Point(*self.driver.position())
        target = self.gen.drift_target(current, self.rng)
        for point, dt in self.gen.subtle_path(current, target, self.rng):
            if self._stop.is_set():
                return
            self.driver.move(*point.as_int())
            self._sleep(dt)

    def start(self) -> "IdleDriftLoop":
        if self._thread and self._thread.is_alive():
            return self
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return self

    def _run(self) -> None:
        while not self._stop.is_set():
            if self._stop.wait(self.rng.uniform(*self.check_interval)):
                break
            try:
                self.tick()
            except Exception:
                pass  # never let the idle thread crash the app

    def stop(self, timeout: float = 2.0) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=timeout)
            self._thread = None
