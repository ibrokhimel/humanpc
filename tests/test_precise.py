import time

from humanpc.hil.precise import (
    begin_high_resolution,
    end_high_resolution,
    high_resolution_timer,
    precise_sleep,
)


def test_precise_sleep_zero_returns_immediately():
    t = time.perf_counter()
    precise_sleep(0)
    precise_sleep(-1)
    assert time.perf_counter() - t < 0.01


def test_precise_sleep_waits_at_least_the_duration():
    t = time.perf_counter()
    precise_sleep(0.05)
    elapsed = time.perf_counter() - t
    assert elapsed >= 0.045  # accurate to within the spin window


def test_high_resolution_timer_context_yields_bool():
    with high_resolution_timer() as active:
        assert isinstance(active, bool)


def test_high_resolution_begin_end_are_safe_to_call():
    # On non-Windows these are no-ops; on Windows they adjust the timer tick.
    active = begin_high_resolution()
    assert isinstance(active, bool)
    end_high_resolution()  # must not raise even if begin was a no-op
