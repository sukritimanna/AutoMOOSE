"""
recovery.py — closed-loop auto-correction for AutoMOOSE.

Drop this module in automoose/agents/ alongside orchestrator.py. It adds:
  - classify_failure(log_text, completed, skeptic_verdict) -> diagnosis
  - apply_correction(params, diagnosis) -> new_params  (bounded, logged)
  - the building blocks orchestrate_with_recovery() uses.

Design principles (kept honest):
  * Failure CLASSES are detected from REAL MOOSE log signatures (grep-able),
    not invented. If a signature isn't present, the class isn't claimed.
  * CORRECTIONS edit only real plugin params (dt0, dt_cutback, end_time,
    nx/ny, uniform_refine) — the same knobs the grain_growth plugin exposes.
  * Every correction is BOUNDED (caps below) so the loop cannot wander into
    nonsense, and is LOGGED so the recovery is fully auditable.
  * The loop has a hard MAX_ATTEMPTS cap; if exhausted, the task is flagged
    as "outside the validated envelope" rather than silently reported.
"""
from __future__ import annotations
import re
from pathlib import Path

MAX_ATTEMPTS = 3            # total generate->run->verify attempts per task
MIN_DT0      = 1.0         # ns, do not reduce initial dt below this
MAX_REFINE   = 4           # do not refine uniform_refine beyond this
MAX_NX       = 96          # do not grow mesh beyond this per dimension
MAX_END_TIME = 16000.0    # ns, do not extend integration beyond this


# ── failure classification ──────────────────────────────────────────────────
def _looks_completed(log_text: str, completed_flag: bool,
                     reached_time=None, target_time=None) -> bool:
    """Decide completion from the strongest available evidence, NOT a stale
    status field. A log that says 'Finished Executing', or a run that reached
    (essentially) its target end_time, is completed regardless of transient
    DIVERGED_ITS adaptive-dt messages."""
    if completed_flag:
        return True
    txt = log_text or ""
    if "Finished Executing" in txt:
        return True
    try:
        if (reached_time is not None and target_time is not None
                and float(reached_time) >= 0.99 * float(target_time)):
            return True
    except Exception:
        pass
    return False


def classify_failure(log_text: str,
                     completed: bool,
                     skeptic_verdict: dict | None = None,
                     reached_time=None, target_time=None) -> dict:
    """Return {'class', 'evidence', 'reason'} from real signatures.

    Completion is decided defensively: a log that finished executing (or a run
    that reached its target end_time) is treated as completed even if the
    caller's 'completed' flag is stale, so a successful run is never
    'corrected'. Order: incomplete runs are triaged from the log; completed
    runs that the Skeptic falsified are triaged from the physics verdict.
    """
    txt = log_text or ""
    is_done = _looks_completed(txt, completed, reached_time, target_time)

    # --- run did not complete: read the solver log ---
    if not is_done:
        if re.search(r"nan|inf(?!o)|not a number", txt, re.I):
            return {"class": "NAN_DETECTED",
                    "evidence": "NaN/Inf in residual stream",
                    "reason": "non-finite residual; step too large for the stiffness"}
        if re.search(r"Aborting as solve did not converge|"
                     r"Solve Did NOT Converge|DIVERGED", txt):
            return {"class": "SOLVER_DIVERGENCE",
                    "evidence": "solve did not converge / diverged before completion",
                    "reason": "Newton/Krylov failed to converge at the chosen timestep"}
        if re.search(r"Mesh|element.*too|under-?resolv|refine", txt, re.I):
            return {"class": "MESH_RESOLUTION",
                    "evidence": "mesh/resolution message in log",
                    "reason": "interface under-resolved by the mesh"}
        if not txt.strip():
            return {"class": "NO_LOG",
                    "evidence": "no solver log available",
                    "reason": "cannot diagnose without a log; not treated as a failure"}
        return {"class": "INCOMPLETE_UNKNOWN",
                "evidence": "run did not reach end_time; no recognized signature",
                "reason": "did not complete for an unclassified reason"}

    # --- run completed but Skeptic falsified it: read the physics verdict ---
    if skeptic_verdict and skeptic_verdict.get("credible") is False:
        fb = set(skeptic_verdict.get("falsified_by", []))
        if "T1_monotonicity" in fb:
            return {"class": "NONPHYSICAL_NUCLEATION",
                    "evidence": "grain count increased (Skeptic T1)",
                    "reason": "spontaneous nucleation / tracker artifact; step or mesh too coarse"}
        if "T3_parabolic" in fb:
            return {"class": "KINETICS_NOT_ASYMPTOTIC",
                    "evidence": "parabolic R2 below threshold (Skeptic T3)",
                    "reason": "integration window too short to reach the asymptotic regime"}
        if "T5_numerical" in fb:
            return {"class": "SOLVER_DIVERGENCE",
                    "evidence": "numerical-integrity failure (Skeptic T5)",
                    "reason": "late-stage solver breakdown despite reaching some output"}
        return {"class": "FALSIFIED_OTHER",
                "evidence": f"Skeptic falsified_by={sorted(fb)}",
                "reason": "physics invariant violated"}

    return {"class": "NONE", "evidence": "", "reason": "no failure to correct"}


# ── correction policy (params-level, bounded, logged) ───────────────────────
def apply_correction(params: dict, diagnosis: dict) -> tuple[dict, dict]:
    """Return (new_params, change_record). Pure: does not mutate input."""
    p = dict(params)
    cls = diagnosis.get("class", "NONE")
    change: dict = {"class": cls, "edits": {}}

    def _set(key, val, why):
        change["edits"][key] = {"from": params.get(key), "to": val, "why": why}
        p[key] = val

    if cls in ("SOLVER_DIVERGENCE", "NAN_DETECTED"):
        # halve the initial timestep (down to a floor); use the real param name
        dt_key = "dt_start" if "dt_start" in params else (
                 "dt0" if "dt0" in params else None)
        if dt_key is not None:
            dt0 = float(params[dt_key])
            new_dt0 = max(MIN_DT0, dt0 / 2.0)
            if new_dt0 < dt0:
                _set(dt_key, new_dt0, "reduce initial timestep to regain convergence")
        cutback = float(params.get("dt_cutback", 0.5))
        new_cb = max(0.25, cutback - 0.1)
        if new_cb < cutback:
            _set("dt_cutback", new_cb, "more aggressive cutback on failed steps")

    elif cls == "KINETICS_NOT_ASYMPTOTIC":
        # extend integration so the asymptotic (parabolic) regime develops
        et = float(params.get("end_time", 4000.0))
        new_et = min(MAX_END_TIME, et * 2.0)
        if new_et > et:
            _set("end_time", new_et, "extend integration to reach asymptotic regime")

    elif cls == "NONPHYSICAL_NUCLEATION":
        # refine mesh and/or reduce dt to suppress tracker artifacts
        ur = int(params.get("uniform_refine", 1))
        if ur < MAX_REFINE:
            _set("uniform_refine", ur + 1, "refine mesh to suppress nucleation artifact")
        dt_key = "dt_start" if "dt_start" in params else (
                 "dt0" if "dt0" in params else None)
        if dt_key is not None:
            dt0 = float(params[dt_key])
            new_dt0 = max(MIN_DT0, dt0 / 2.0)
            if new_dt0 < dt0:
                _set(dt_key, new_dt0, "reduce timestep to suppress spurious grains")

    elif cls == "MESH_RESOLUTION":
        dim = int(params.get("dim", 2))
        axes = ("nx", "ny", "nz") if dim == 3 else ("nx", "ny")
        for ax in axes:
            if ax in params:
                cur = int(params[ax])
                new = min(MAX_NX, int(cur * 1.5))
                if new > cur:
                    _set(ax, new, "increase mesh resolution to resolve interface")

    # else NONE / INCOMPLETE_UNKNOWN / FALSIFIED_OTHER: no automatic edit
    change["applied"] = bool(change["edits"])
    return p, change


def correction_exhausted(change_history: list) -> bool:
    """True if the last attempt produced no actionable edit (loop should stop)."""
    return bool(change_history) and not change_history[-1].get("applied", False)
