"""Human scroll planning.

Wheel input arrives in **flings**: a burst of clicks that starts fast and
*decelerates* (momentum), separated by pauses — and the reader periodically stops
longer to actually read the newly revealed content (**reading coupling**). Real
scrolling also occasionally **overshoots** and corrects back (opt-in here, since
it reverses direction).

Returns a list of ``(delta, dt)`` where ``delta`` is wheel clicks (0 marks a
pause) and ``dt`` is the wait after that event. The signed total of all deltas
equals the requested ``amount``.
"""

from __future__ import annotations


def plan_scroll(
    amount: int,
    rng,
    *,
    momentum: bool = True,
    read_pause_prob: float = 0.35,
    overshoot_prob: float = 0.0,
) -> list[tuple[int, float]]:
    amount = int(amount)
    if amount == 0:
        return []
    sign = 1 if amount > 0 else -1
    remaining = abs(amount)
    events: list[tuple[int, float]] = []

    while remaining > 0:
        burst = rng.randint(2, 5)
        peak = rng.randint(2, 3)  # a fling starts fast...
        for k in range(burst):
            if remaining <= 0:
                break
            if momentum:
                # ...and decelerates: step magnitude decays over the fling.
                mag = max(1, round(peak * (0.7 ** k)))
            else:
                mag = rng.randint(1, 3)
            step = min(remaining, mag)
            events.append((sign * step, rng.uniform(0.03, 0.09)))
            remaining -= step
        if remaining > 0:
            # Periodically pause longer to read what just scrolled into view.
            if rng.random() < read_pause_prob:
                events.append((0, rng.uniform(0.6, 1.6)))
            else:
                events.append((0, rng.uniform(0.18, 0.45)))

    # Optional overshoot: sail a couple clicks past, then correct back (net 0).
    if overshoot_prob and rng.random() < overshoot_prob:
        over = rng.randint(1, 2)
        events.append((sign * over, rng.uniform(0.04, 0.09)))
        events.append((0, rng.uniform(0.12, 0.3)))
        events.append((-sign * over, rng.uniform(0.05, 0.12)))
    return events
