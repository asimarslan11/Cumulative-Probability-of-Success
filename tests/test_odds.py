"""
test_odds.py

The prob <-> odds primitives (pos_engine/odds.py): trivial-case conversions, the
round-trip identity, and the 0% / 100% clipping that keeps the arithmetic finite.

Run with:  python -m pytest tests/test_odds.py -v
"""

import pytest

from pos_engine.config import MAX_PROB, MIN_PROB
from pos_engine.odds import clip_prob, odds_to_prob, prob_to_odds


# --- trivial conversions ---------------------------------------------------

@pytest.mark.parametrize("p, o", [
    (0.5, 1.0),
    (0.2, 0.25),
    (0.8, 4.0),
])
def test_prob_to_odds_known_values(p, o):
    assert prob_to_odds(p) == pytest.approx(o)


@pytest.mark.parametrize("o, p", [
    (1.0, 0.5),
    (0.25, 0.2),
    (4.0, 0.8),
])
def test_odds_to_prob_known_values(o, p):
    assert odds_to_prob(o) == pytest.approx(p)


# --- round trip ------------------------------------------------------------

@pytest.mark.parametrize("p", [0.01, 0.1, 0.25, 0.5, 0.63, 0.8, 0.95])
def test_round_trip_identity(p):
    """odds_to_prob(prob_to_odds(p)) == p for any p inside the clip range."""
    assert odds_to_prob(prob_to_odds(p)) == pytest.approx(p)


# --- clipping --------------------------------------------------------------

def test_clip_prob_clamps_zero_and_one():
    assert clip_prob(0.0) == MIN_PROB
    assert clip_prob(1.0) == MAX_PROB
    assert clip_prob(-5.0) == MIN_PROB
    assert clip_prob(5.0) == MAX_PROB


def test_clip_prob_leaves_interior_untouched():
    assert clip_prob(0.42) == 0.42


def test_prob_to_odds_is_finite_at_the_extremes():
    """0% and 100% cells (e.g. Allergy filing->approval = 100%) must not blow up."""
    zero_odds = prob_to_odds(0.0)
    one_odds = prob_to_odds(1.0)
    assert zero_odds == pytest.approx(MIN_PROB / (1 - MIN_PROB))
    assert one_odds == pytest.approx(MAX_PROB / (1 - MAX_PROB))
    # Both finite and positive.
    assert 0 < zero_odds < one_odds < float("inf")


def test_prob_to_odds_clips_before_dividing():
    """A 100% probability clips to MAX_PROB rather than dividing by zero."""
    assert prob_to_odds(1.0) == pytest.approx(prob_to_odds(MAX_PROB))
    assert prob_to_odds(0.0) == pytest.approx(prob_to_odds(MIN_PROB))
