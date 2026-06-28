"""Skeptic invariants on toy trajectories.

The Skeptic's quantitative invariants rest on a least-squares fit (``_linfit``)
used for the Burke--Turnbull parabolic check (R^2 >= 0.90) and the cross-run
Arrhenius consistency test. These exercise that machinery on synthetic
good/bad data without needing a real MOOSE run directory.
"""
import math

from automoose.agents.skeptic import _linfit, arrhenius_consistency


def test_linfit_recovers_a_perfect_line():
    xs = [0, 1, 2, 3, 4]
    ys = [1, 3, 5, 7, 9]  # y = 2x + 1
    slope, intercept, r2 = _linfit(xs, ys)
    assert abs(slope - 2.0) < 1e-9
    assert abs(intercept - 1.0) < 1e-9
    assert r2 > 0.999


def test_linfit_flags_a_poor_fit_below_threshold():
    xs = [0, 1, 2, 3, 4]
    ys = [0, 1, 0, 1, 0]  # zig-zag, not linear
    _, _, r2 = _linfit(xs, ys)
    assert r2 < 0.90  # would fail the T3 parabolic invariant


def test_linfit_needs_at_least_three_points():
    assert _linfit([0, 1], [0, 1]) == (None, None, None)


def _arrhenius_rates(Q_eV=0.5, A=1e6):
    kB = 8.617e-5
    temps = [600.0, 700.0, 800.0, 900.0, 1000.0]
    return [(T, A * math.exp(-Q_eV / (kB * T))) for T in temps]


def test_arrhenius_consistency_passes_on_arrhenius_data():
    result = arrhenius_consistency(_arrhenius_rates())
    assert result["pass"] is True
    assert result["R2"] >= 0.90
    assert result["monotonic_in_T"] is True
    assert result["Q_eV"] is not None and result["Q_eV"] > 0


def test_arrhenius_consistency_fails_on_non_monotonic_data():
    bad = [(600.0, 5.0), (700.0, 2.0), (800.0, 9.0)]  # rate dips at 700 K
    result = arrhenius_consistency(bad)
    assert result["pass"] is False


def test_arrhenius_consistency_needs_three_points():
    result = arrhenius_consistency([(600.0, 1.0), (700.0, 2.0)])
    assert result["pass"] is False
