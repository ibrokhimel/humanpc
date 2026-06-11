"""Human scroll planning: wheel input arrives in bursts of a few clicks separated
by short pauses, not one smooth sweep.

Returns a list of ``(delta, dt)`` where ``delta`` is wheel clicks (0 marks a pause
between bursts) and ``dt`` is the wait after that event. The signed total of all
deltas equals the requested ``amount``.
"""

from __future__ import annotations


def plan_scroll(amount: int, rng) -> list[tuple[int, float]]:
    amount = int(amount)
    if amount == 0:
        return []
    sign = 1 if amount > 0 else -1
    remaining = abs(amount)
    events: list[tuple[int, float]] = []
    while remaining > 0:
        burst = rng.randint(2, 5)
        for _ in range(burst):
            if remaining <= 0:
                break
            step = min(remaining, rng.randint(1, 3))
            events.append((sign * step, rng.uniform(0.03, 0.09)))
            remaining -= step
        if remaining > 0:
            events.append((0, rng.uniform(0.18, 0.45)))  # pause between bursts
    return events
