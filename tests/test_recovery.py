"""Recovery policy: bounded, numerical-only, pure corrections.

The article claims recovery edits only numerical and discretization controls
(time step, cutback, nonlinear iterations, mesh refinement, integration
window), never physical parameters, and that corrections are bounded and
logged. These tests pin those guarantees to ``recovery.py``.
"""
from automoose.agents import recovery


def test_policy_constants():
    assert recovery.MAX_ATTEMPTS == 3
    assert recovery.MIN_DT0 == 1.0
    assert recovery.MAX_REFINE == 4
    assert recovery.MAX_END_TIME == 16000.0


def test_apply_correction_is_pure():
    params = {"dt_start": 25.0, "end_time": 1000.0}
    snapshot = dict(params)
    new_params, _ = recovery.apply_correction(params, {"class": "SOLVER_DIVERGENCE"})
    assert params == snapshot, "input params must not be mutated"
    assert new_params is not params


def test_dt_start_is_floored_at_min_dt0():
    # Halving 1.5 would give 0.75; the floor must keep it at MIN_DT0.
    new_params, _ = recovery.apply_correction({"dt_start": 1.5}, {"class": "NAN_DETECTED"})
    assert new_params["dt_start"] >= recovery.MIN_DT0


def test_divergence_correction_reduces_timestep():
    new_params, change = recovery.apply_correction(
        {"dt_start": 25.0}, {"class": "SOLVER_DIVERGENCE"})
    assert new_params["dt_start"] < 25.0
    assert "dt_start" in change["edits"]


def test_corrections_never_touch_physical_parameters():
    physical = {"GBenergy": 0.708, "GBmob0": 2.5e-6, "T": 800.0,
                "gbmob": 100.0, "gamma_asymm": 1.5}
    params = dict(physical, dt_start=25.0, end_time=1000.0, uniform_refine=2)
    for cls in ("SOLVER_DIVERGENCE", "NAN_DETECTED",
                "KINETICS_NOT_ASYMPTOTIC", "NONPHYSICAL_NUCLEATION"):
        new_params, _ = recovery.apply_correction(dict(params), {"class": cls})
        for key, value in physical.items():
            assert new_params.get(key) == value, f"{cls} altered physical param {key}"


def test_correction_exhausted_logic():
    assert recovery.correction_exhausted([]) is False
    assert recovery.correction_exhausted([{"applied": True}]) is False
    assert recovery.correction_exhausted([{"applied": False}]) is True
