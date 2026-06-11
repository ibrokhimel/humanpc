import random

from humanpc.hil.scroll import plan_scroll


def test_deltas_sum_to_amount_down():
    events = plan_scroll(10, random.Random(0))
    assert sum(d for d, _ in events) == 10


def test_deltas_sum_to_amount_up():
    events = plan_scroll(-6, random.Random(1))
    assert sum(d for d, _ in events) == -6


def test_zero_is_noop():
    assert plan_scroll(0, random.Random(2)) == []


def test_has_burst_pauses_for_large_scroll():
    events = plan_scroll(30, random.Random(3))
    assert any(d == 0 for d, _ in events)  # pauses between bursts
    assert all(dt >= 0 for _, dt in events)


def test_single_direction():
    events = [d for d, _ in plan_scroll(15, random.Random(4)) if d != 0]
    assert all(d > 0 for d in events)
