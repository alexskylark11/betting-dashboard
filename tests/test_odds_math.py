"""Tests for odds conversion and EV math."""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils.odds_math import (
    american_to_decimal, decimal_to_american, american_to_implied_prob,
    remove_vig, parlay_american_odds, ev_from_american, calculate_overround,
)


def test_american_to_decimal():
    assert american_to_decimal(100) == 2.0
    assert american_to_decimal(200) == 3.0
    assert american_to_decimal(-200) == 1.5
    assert american_to_decimal(-100) == 2.0
    assert abs(american_to_decimal(500) - 6.0) < 0.01


def test_decimal_to_american():
    assert decimal_to_american(2.0) == 100
    assert decimal_to_american(3.0) == 200
    assert decimal_to_american(1.5) == -200


def test_implied_prob():
    assert abs(american_to_implied_prob(100) - 0.5) < 0.001
    assert abs(american_to_implied_prob(-200) - 0.6667) < 0.01
    assert abs(american_to_implied_prob(200) - 0.3333) < 0.01


def test_remove_vig():
    # Two-outcome market with 10% vig
    odds = {"Team A": -110, "Team B": -110}
    fair = remove_vig(odds)
    assert abs(fair["Team A"] - 0.5) < 0.01
    assert abs(fair["Team B"] - 0.5) < 0.01
    assert abs(sum(fair.values()) - 1.0) < 0.001


def test_overround():
    # Fair market
    assert abs(calculate_overround([100, 100]) - 1.0) < 0.001
    # Market with vig
    assert calculate_overround([-110, -110]) > 1.0


def test_ev():
    # Positive EV: model says 55% but implied is 50% at +100
    ev = ev_from_american(0.55, 100)
    assert ev > 0
    # Negative EV: model says 45% at -110
    ev2 = ev_from_american(0.45, -110)
    assert ev2 < 0


def test_parlay():
    # Two +100 legs = +300
    combined = parlay_american_odds([100, 100])
    assert combined == 300


if __name__ == "__main__":
    test_american_to_decimal()
    test_decimal_to_american()
    test_implied_prob()
    test_remove_vig()
    test_overround()
    test_ev()
    test_parlay()
    print("All tests passed!")
