#!/usr/bin/env python3
"""test_recovery.py — validate the diagnosis + correction logic WITHOUT MOOSE.

This replays recovery.classify_failure() and recovery.apply_correction() against
your REAL run directories (local runs/ or a staging dir), so you can confirm the
failure classes and param corrections are sensible BEFORE running the full
closed loop on HPC.

Usage:
    # local synthetic check (no data needed):
    python test_recovery.py --selftest

    # against real run dirs (reads each run.log + metadata.json):
    python test_recovery.py --stage runs
    python test_recovery.py --stage /pscratch/sd/s/smanna/autoMOOSE/staging_prod

What it does per run dir:
    1. read the log (run.log or *.log) and metadata.json (params, status)
    2. if the run didn't complete -> classify from the log
    3. if it completed -> (optionally) load a falsification report to get the
       Skeptic verdict and classify from that
    4. print the diagnosis + the param correction that WOULD be applied

It never launches MOOSE; it only exercises the decision logic.
"""
import argparse, json, sys
from pathlib import Path

# import the recovery module (expects to run from repo root, or alongside it)
try:
    from automoose.agents import recovery
except Exception:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import recovery  # if you drop this next to recovery.py



def _reached_target(log_text: str, params: dict):
    """Best-effort (reached_time, target_time) from the log + params."""
    import re
    target = None
    try:
        target = float(params.get("end_time")) if params.get("end_time") is not None else None
    except Exception:
        target = None
    reached = None
    # MOOSE prints "Time Step N, time = X"; take the last
    times = re.findall(r"time\s*=\s*([0-9.eE+\-]+)", log_text or "")
    if times:
        try:
            reached = float(times[-1])
        except Exception:
            reached = None
    if reached is None and "Finished Executing" in (log_text or "") and target is not None:
        reached = target
    return reached, target


def _read_log(d: Path) -> str:
    for cand in (d / "run.log", d / f"{d.name}.log"):
        if cand.exists():
            return cand.read_text(errors="ignore")
    hits = sorted(d.glob("*.log"))
    return hits[0].read_text(errors="ignore") if hits else ""


def _read_meta(d: Path) -> dict:
    for cand in (d / "metadata.json", d / "record.json"):
        if cand.exists():
            try:
                return json.loads(cand.read_text())
            except Exception:
                pass
    return {}


def selftest():
    print("=== SELFTEST: synthetic logs ===")
    cases = [
        ("diverged, incomplete",
         "Time Step 12 ... Solve Did NOT Converge!\nAborting as solve did not converge",
         False, None),
        ("NaN, incomplete",
         "nonlinear residual = nan\n", False, None),
        ("completed, falsified T3 (parabolic)",
         "Finished Executing", True, {"credible": False, "falsified_by": ["T3_parabolic"]}),
        ("completed, falsified T1 (nucleation)",
         "Finished Executing", True, {"credible": False, "falsified_by": ["T1_monotonicity"]}),
        ("completed, credible",
         "Finished Executing", True, {"credible": True, "falsified_by": []}),
    ]
    base = {"dt0": 25.0, "dt_cutback": 0.5, "end_time": 4000.0,
            "nx": 24, "ny": 24, "uniform_refine": 1}
    for name, log, completed, sk in cases:
        diag = recovery.classify_failure(log, completed=completed, skeptic_verdict=sk)
        newp, change = recovery.apply_correction(base, diag)
        edits = {k: v["to"] for k, v in change["edits"].items()}
        print(f"\n[{name}]")
        print(f"  class    : {diag['class']}")
        print(f"  reason   : {diag['reason']}")
        print(f"  correction: {edits if edits else '(none)'}")
    print("\nSelftest done.")


def run_stage(stage: str, falsification_report: str | None):
    d = Path(stage)
    dirs = sorted(p for p in d.glob("GG*") if p.is_dir()) or \
           sorted(p for p in d.glob("*") if p.is_dir())
    if not dirs:
        print(f"No run dirs under {stage}"); return

    # optional: load a falsification report to get Skeptic verdicts by id
    verdicts = {}
    if falsification_report and Path(falsification_report).exists():
        rep = json.loads(Path(falsification_report).read_text())
        for r in rep.get("reports", []):
            verdicts[r["id"]] = r

    print(f"=== Replaying diagnosis/correction over {len(dirs)} runs in {stage} ===\n")
    for rd in dirs:
        log = _read_log(rd)
        if not log:
            # no solver log -> this is a backend run-record dir, not a MOOSE
            # output dir; skip rather than mis-scoring it as a failure.
            continue
        meta = _read_meta(rd)
        params = meta.get("params", {})
        status = str(meta.get("status", "")).lower()
        completed = status == "completed"
        sk = verdicts.get(rd.name)
        sk_verdict = {"credible": sk.get("credible"),
                      "falsified_by": sk.get("falsified_by", [])} if sk else None

        reached, target = _reached_target(log, params)
        diag = recovery.classify_failure(log, completed=completed,
                                         skeptic_verdict=sk_verdict,
                                         reached_time=reached, target_time=target)
        if diag["class"] == "NONE":
            print(f"{rd.name:6} OK (credible / nothing to correct)")
            continue
        newp, change = recovery.apply_correction(params, diag)
        edits = {k: f"{v['from']}->{v['to']}" for k, v in change["edits"].items()}
        print(f"{rd.name:6} class={diag['class']:24} "
              f"correction={edits if edits else '(no actionable edit)'}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--stage", default=None)
    ap.add_argument("--falsification-report", default=None,
                    help="optional skeptic report JSON to supply verdicts for completed runs")
    a = ap.parse_args()
    if a.selftest or not a.stage:
        selftest()
    if a.stage:
        run_stage(a.stage, a.falsification_report)
