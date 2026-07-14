"""
odds.py

The two-line arithmetic the whole engine turns on: converting a probability to
*odds* and back. We adjust baselines in odds space because odds multiply cleanly
(``adjusted_odds = baseline_odds x LR``) while probabilities do not.

Why the clip? A raw 0% or 100% cell (e.g. Allergy filing->approval = 100%, n=20)
has odds of 0 or +infinity, which would collapse or blow up every downstream
product. We clamp every probability into ``[MIN_PROB, MAX_PROB]`` (0.1%-99%, from
config) before taking odds, so the arithmetic stays finite and reversible.

    prob_to_odds(0.5) -> 1.0        odds_to_prob(1.0) -> 0.5
    prob_to_odds(0.8) -> 4.0        odds_to_prob(4.0) -> 0.8

These are exact inverses on the clipped range.
"""

from pos_engine.config import MAX_PROB, MIN_PROB


def clip_prob(p):
    """Clamp a probability into ``[MIN_PROB, MAX_PROB]``.

    Keeps 0% / 100% source cells from producing 0 or infinite odds.
    """
    if p < MIN_PROB:
        return MIN_PROB
    if p > MAX_PROB:
        return MAX_PROB
    return p


def prob_to_odds(p):
    """Convert a probability to odds ``p / (1 - p)``.

    ``p`` is clipped into ``[MIN_PROB, MAX_PROB]`` first, so the result is always a
    finite positive number.
    """
    p = clip_prob(p)
    return p / (1.0 - p)


def odds_to_prob(o):
    """Convert odds back to a probability ``o / (1 + o)``.

    Non-negative ``o`` maps into ``[0, 1)``; the caller clips into
    ``[MIN_PROB, MAX_PROB]`` when a strict open-interval result is required.
    """
    return o / (1.0 + o)


__all__ = ["clip_prob", "prob_to_odds", "odds_to_prob"]
