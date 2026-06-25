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
DEFAULT_DT_START = 25.0   # plugin IterationAdaptiveDT default dt


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
        # Skeptic established no time advance (T5) even without an explicit
        # DIVERGED string: the first solve failed and the run never advanced.
        # Checked before the loose mesh-keyword heuristic below (the word "Mesh"
        # appears in ordinary setup output and must not mask a divergence).
        if skeptic_verdict and skeptic_verdict.get("credible") is False:
            fb = set(skeptic_verdict.get("falsified_by", []))
            t5 = skeptic_verdict.get("tests", {}).get("T5_numerical", {})
            if "T5_numerical" in fb and (
                    "no time advance" in str(t5.get("reason", "")).lower()
                    or t5.get("reached_time", None) == 0.0
                    or (reached_time is not None and reached_time == 0.0)):
                return {"class": "SOLVER_DIVERGENCE",
                        "evidence": "no time advance; Skeptic T5 on an incomplete run",
                        "reason": "first solve failed to converge; run never advanced past t=0"}
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
        # Reduce the initial timestep. The grain_growth plugin always uses
        # IterationAdaptiveDT with dt = dt_start (default 25.0), so even tasks
        # that did not set dt_start explicitly ran at dt_start=25. Inject and
        # halve it so the correction has real effect.
        if "dt_start" in params:
            dt0 = float(params["dt_start"])
        elif "dt0" in params:
            dt0 = float(params["dt0"])
        else:
            dt0 = float(DEFAULT_DT_START)   # plugin default
        new_dt0 = max(MIN_DT0, dt0 / 2.0)
        if new_dt0 < dt0:
            _set("dt_start", new_dt0, "reduce initial timestep to regain convergence")
        cutback = float(params.get("dt_cutback", 0.5))
        new_cb = max(0.25, cutback - 0.1)
        if new_cb < cutback:
            _set("dt_cutback", new_cb, "more aggressive cutback on failed steps")
        # for the ill-conditioned linearized-interface solver, also allow more
        # nonlinear iterations before declaring failure
        if params.get("formulation") == "LinearizedInterface":
            nlmax = int(params.get("nl_max_its", 20))
            if nlmax < 50:
                _set("nl_max_its", 50, "allow more nonlinear iterations for stiff LI solve")

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


# ── CLI: diagnose a run dir and emit corrected params as JSON ────────────────
def _cli():
    import argparse, json, sys
    from pathlib import Path
    ap = argparse.ArgumentParser(description="Diagnose a failed run and emit corrected params.")
    ap.add_argument("--diagnose", required=True, help="run directory to diagnose")
    ap.add_argument("--params", default=None, help="JSON file or string of current params")
    ap.add_argument("--skeptic", default=None, help="optional skeptic verdict JSON (string or file)")
    a = ap.parse_args()

    d = Path(a.diagnose)
    # find log
    log = ""
    for c in (d / "run.log", d / f"{d.name}.log"):
        if c.exists(): log = c.read_text(errors="ignore"); break
    if not log:
        hits = sorted(d.glob("*.log"))
        if hits: log = hits[0].read_text(errors="ignore")

    # current params: from --params, else metadata.json
    def _load(x):
        if x is None: return None
        p = Path(x)
        return json.loads(p.read_text()) if p.exists() else json.loads(x)
    params = _load(a.params)
    if params is None:
        for c in (d / "metadata.json", d / "record.json"):
            if c.exists():
                params = (json.loads(c.read_text()).get("params", {})); break
    params = params or {}

    sk = _load(a.skeptic)

    # completion-aware: read end_time + reached time
    reached, target = None, None
    try:
        target = float(params.get("end_time")) if params.get("end_time") is not None else None
    except Exception:
        target = None
    import re
    times = re.findall(r"time\s*=\s*([0-9.eE+\-]+)", log)
    if times:
        try: reached = float(times[-1])
        except Exception: reached = None

    completed = ("Finished Executing" in log)
    diag = classify_failure(log, completed=completed, skeptic_verdict=sk,
                            reached_time=reached, target_time=target)
    new_params, change = apply_correction(params, diag)
    print(json.dumps({"diagnosis": diag, "change": change,
                      "corrected_params": new_params}, indent=2))


if __name__ == "__main__":
    _cli()
