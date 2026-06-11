import random
import time

from humanpc.geometry import Point
from humanpc.hil.idle import IdleDriftLoop, IdleMovementGenerator
from humanpc.input import NullDriver


def test_drift_target_stays_bounded():
    gen = IdleMovementGenerator(drift_range=10)
    rng = random.Random(0)
    offsets = [abs(gen.drift_target(Point(100, 100), rng).x - 100) for _ in range(300)]
    assert max(offsets) < 70  # ~7 sigma headroom


def test_subtle_path_ends_on_target():
    gen = IdleMovementGenerator(steps=10)
    path = gen.subtle_path(Point(0, 0), Point(20, 10), random.Random(1))
    assert len(path) == 10
    last = path[-1][0]
    assert abs(last.x - 20) < 1e-6 and abs(last.y - 10) < 1e-6


def test_tick_drifts_when_idle():
    d = NullDriver()
    loop = IdleDriftLoop(d, idle_seconds=lambda: 100.0, rng=random.Random(0),
                         threshold=2.0, probability=1.0)
    assert loop.tick() is True
    assert any(e[0] == "move" for e in d.events)


def test_tick_skips_when_busy():
    d = NullDriver()
    loop = IdleDriftLoop(d, idle_seconds=lambda: 0.0, rng=random.Random(0),
                         threshold=2.0, probability=1.0)
    assert loop.tick() is False
    assert d.events == []


def test_start_stop_lifecycle_produces_movement():
    d = NullDriver()
    loop = IdleDriftLoop(
        d, idle_seconds=lambda: 100.0, rng=random.Random(0),
        threshold=2.0, probability=1.0, check_interval=(0.01, 0.02),
        sleep=lambda s: None,
    )
    loop.start()
    time.sleep(0.1)
    loop.stop()
    assert any(e[0] == "move" for e in d.events)
