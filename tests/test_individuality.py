"""Tier 4 — variability & individuality: distinct, consistent personas + AR(1)."""

import random
import statistics

from humanpc import Bot
from humanpc.config import Config
from humanpc.hil.individual import ActionTempo, sample_individual


# --- between-person variance (each instance is a different person) ----------

def test_sampled_individuals_differ_across_seeds():
    people = [sample_individual(random.Random(s)) for s in range(50)]
    wpms = [p.base_wpm for p in people]
    errs = [p.error_rate for p in people]
    assert statistics.pstdev(wpms) > 5.0     # real spread across the population
    assert statistics.pstdev(errs) > 0.005
    assert len({round(p.base_wpm, 3) for p in people}) > 40  # not clones


def test_same_seed_same_person():
    a = sample_individual(random.Random(123))
    b = sample_individual(random.Random(123))
    assert a == b


def test_bot_has_a_stable_individual_within_session():
    bot = Bot(dry_run=True, config=Config(seed=7))
    first = bot.individual
    bot.type("hello")
    bot.move_to((100, 100))
    assert bot.individual is first  # identity does not re-roll between actions


def test_two_bots_are_different_people():
    a = Bot(dry_run=True, config=Config(seed=1)).individual
    b = Bot(dry_run=True, config=Config(seed=2)).individual
    assert a != b


def test_individuality_can_be_disabled():
    bot = Bot(dry_run=True, config=Config(seed=1, individuality=False))
    assert bot.individual is None


# --- correlated traits (no impossible humans) -------------------------------

def test_skill_correlates_speed_and_accuracy():
    people = [sample_individual(random.Random(s)) for s in range(400)]
    fast = [p for p in people if p.skill > 0.6]
    slow = [p for p in people if p.skill < -0.6]
    # Higher skill -> higher WPM and lower error rate (correlated, not independent).
    assert statistics.mean(p.base_wpm for p in fast) > statistics.mean(p.base_wpm for p in slow)
    assert statistics.mean(p.error_rate for p in fast) < statistics.mean(p.error_rate for p in slow)


def test_traits_stay_in_plausible_bounds():
    for s in range(500):
        p = sample_individual(random.Random(s))
        assert 20.0 <= p.base_wpm <= 120.0
        assert 0.005 <= p.error_rate <= 0.18
        assert 0.04 <= p.dwell_median <= 0.16


# --- within-person autocorrelation (AR(1) tempo) ----------------------------

def test_action_tempo_is_autocorrelated():
    tempo = ActionTempo(rho=0.7)
    rng = random.Random(0)
    xs = []
    for _ in range(4000):
        tempo.advance(rng)
        xs.append(tempo.x)
    n = len(xs)
    mean = sum(xs) / n
    var = sum((x - mean) ** 2 for x in xs) / n or 1e-9
    lag1 = sum((xs[i] - mean) * (xs[i - 1] - mean) for i in range(1, n)) / n / var
    assert lag1 > 0.5   # consecutive actions are correlated (a streaky rhythm)


def test_action_tempo_centers_near_one():
    tempo = ActionTempo()
    rng = random.Random(1)
    vals = [tempo.advance(rng) for _ in range(3000)]
    assert 0.8 < statistics.median(vals) < 1.25
