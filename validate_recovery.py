#!/usr/bin/env python3
"""validate_recovery.py — live HPC validation of the closed-loop recovery.

Runs a small set of KNOWN-FAILING grain-growth tasks through
orchestrate_with_recovery() and records, for each, the full attempt history:
the failure diagnosed, the correction applied, and whether the corrected rerun
passed the Skeptic. This produces the honest, citable data for the paper:

    "Of N genuinely-failing tasks, the closed loop recovered K via automated
     diagnosis and correction; M fell outside the correction envelope and were
     flagged rather than silently reported."

It does NOT fabricate anything: each task is actually generated, run on MOOSE,
and verified by the Skeptic. Outcomes (recovered / not recovered) are whatever
the physics gives.

Prereqs (same environment the benchmark used):
  - FastAPI backend reachable (the orchestrator's _http target)
  - MOOSE app available to the backend (real runs will execute)
  - recovery.py + the orchestrate_with_recovery() patch applied

Usage:
    python validate_recovery.py --out recovery_validation.json
    python validate_recovery.py --tasks tasks.json --out recovery_validation.json

Define tasks as known failures. The defaults below are deliberately STIFF
cases (high T, fine mesh) chosen because the local replay showed they diverge
at the default dt_start; adjust to match the genuinely-failing cases in your
own benchmark.
"""
import argparse, json, time, os, sys
from pathlib import Path

# import the patched orchestrator
try:
    from automoose.agents import orchestrator
except Exception as e:
    print(f"ERROR importing orchestrator: {e}")
    print("Run from the AutoMOOSE repo root with the backend running.")
    sys.exit(1)

if not hasattr(orchestrator, "orchestrate_with_recovery"):
    print("ERROR: orchestrate_with_recovery not found. Apply apply_recovery_patch.py first.")
    sys.exit(1)


# Known-failing task configs. Each must be a case that FAILS at default settings
# so the loop has something real to recover. Tune T/mesh to your failing cases.
DEFAULT_TASKS = [
    {"label": "highT_fine_A",
     "params": {"run_name": "rec_highT_A", "dim": 2, "formulation": "GBEvolution",
                "ic_type": "Voronoi", "nx": 40, "ny": 40, "num_grains": 20,
                "T": 800, "end_time": 4000, "dt_start": 25, "dt_cutback": 0.5,
                "uniform_refine": 1, "rand_seed": 42}},
    {"label": "highT_fine_B",
     "params": {"run_name": "rec_highT_B", "dim": 2, "formulation": "GBEvolution",
                "ic_type": "Voronoi", "nx": 40, "ny": 40, "num_grains": 20,
                "T": 750, "end_time": 4000, "dt_start": 25, "dt_cutback": 0.5,
                "uniform_refine": 1, "rand_seed": 7}},
]


def summarize(result: dict) -> dict:
    """Pull the decision trail out of an orchestrate_with_recovery() result."""
    hist = result.get("correction_history", [])
    trail = []
    for h in hist:
        d = h.get("diagnosis") or {}
        c = h.get("change") or {}
        edits = {k: v.get("to") for k, v in (c.get("edits") or {}).items()}
        trail.append({"attempt": h.get("attempt"),
                      "stage": h.get("stage"),
                      "class": d.get("class"),
                      "edits": edits})
    return {"attempts": result.get("attempts"),
            "credible": result.get("credible"),
            "outside_envelope": result.get("outside_envelope"),
            "trail": trail,
            "params_final": result.get("params_final")}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", default=None, help="JSON list of {label, params}")
    ap.add_argument("--out", default="recovery_validation.json")
    ap.add_argument("--backend", default=os.environ.get("LLM_MODEL", "configured"))
    a = ap.parse_args()

    tasks = DEFAULT_TASKS
    if a.tasks and Path(a.tasks).exists():
        tasks = json.loads(Path(a.tasks).read_text())

    print(f"=== Closed-loop recovery validation: {len(tasks)} task(s) ===\n")
    results = []
    for t in tasks:
        label = t.get("label", "task")
        params = t["params"]
        print(f"--- {label}: starting (T={params.get('T')}, "
              f"{params.get('nx')}x{params.get('ny')}, dt_start={params.get('dt_start')}) ---")
        t0 = time.time()
        res = orchestrator.orchestrate_with_recovery("grain_growth", params, a.backend)
        summ = summarize(res)
        summ["label"] = label
        summ["wall_s"] = round(time.time() - t0, 1)
        results.append(summ)
        verdict = ("RECOVERED" if summ["credible"] is True
                   else "NOT RECOVERED (flagged outside envelope)")
        print(f"    -> {verdict} after {summ['attempts']} attempt(s)")
        for step in summ["trail"]:
            print(f"       attempt {step['attempt']}: {step['stage']} "
                  f"class={step['class']} edits={step['edits']}")
        print()

    n = len(results)
    k = sum(1 for r in results if r["credible"] is True)
    report = {"n_tasks": n, "n_recovered": k,
              "n_outside_envelope": n - k, "results": results}
    Path(a.out).write_text(json.dumps(report, indent=2))
    print(f"=== {k}/{n} tasks recovered by the closed loop ===")
    print(f"Wrote {a.out}")
    print("\nHONEST REPORTING NOTE: recovered = a corrected rerun PASSED the Skeptic.")
    print("Tasks not recovered are flagged outside_envelope, never reported as valid.")


if __name__ == "__main__":
    main()
