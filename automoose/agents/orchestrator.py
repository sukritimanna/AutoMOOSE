"""Headless f1-f5 orchestrator (W7b).

Runs the full AutoMOOSE pipeline as an explicit Python loop against the existing
FastAPI backend, using the provider-agnostic llm/ client for the reasoning steps.
Because reasoning goes through llm/, the WHOLE pipeline runs on whatever model
config.env names (Claude, Qwen, Llama, ...) with no code change — which is what
makes the model-agnosticism capability table real: each backend drives an actual
generate -> run -> parse cycle, not just a chat prompt.

Pipeline:
  f1 Architect      prompt + params -> validated structured params      [LLM]
  f2 InputWriter    POST /generate  -> MOOSE input file                 [HTTP]
  f3 Runner         POST /run, poll GET /runs/{id} until terminal       [HTTP]
  f4 Reviewer       GET /runs/{id}/csv -> LLM judges physical validity  [LLM]
  f5 Report         assemble run record + per-backend capability row

Usage:
    python -m automoose.agents.orchestrator --physics grain_growth \
        --params '{"T": 800, "n_grains": 50}' --backend-name "Qwen2.5-32B"

Reads BACKEND_URL (default http://localhost:8000) for the AutoMOOSE backend, and
the usual LLM_* env vars for the model. Emits one JSON capability row to stdout.
"""
from __future__ import annotations
import os, sys, json, time, argparse
from urllib import request as _rq, error as _err

from automoose.llm import get_client
from automoose.agents import skeptic
from automoose.agents import recovery

BACKEND = os.environ.get("BACKEND_URL", "http://localhost:8000").rstrip("/")
POLL_S = float(os.environ.get("ORCH_POLL_S", "3"))
TIMEOUT_S = float(os.environ.get("ORCH_TIMEOUT_S", "1800"))
TERMINAL = {"done", "failed", "stopped"}


def _http(method: str, path: str, body: dict | None = None) -> dict:
    url = f"{BACKEND}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = _rq.Request(url, data=data, method=method,
                      headers={"Content-Type": "application/json"})
    with _rq.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode())


# ── f1 Architect ────────────────────────────────────────────────────────────
def f1_architect(physics: str, params: dict) -> dict:
    """Validate/structure params. LLM confirms physical sanity; params are
    authoritative for the demonstration (deterministic case)."""
    llm = get_client()
    sys_p = ("You are a phase-field simulation architect. Given physics and "
             "parameters, reply with one short sentence confirming they are "
             "physically reasonable, or naming any concern. Do not restate them.")
    note = llm.complete(system=sys_p,
                        messages=[{"role": "user",
                                   "content": f"physics={physics} params={params}"}],
                        max_tokens=80)
    return {"params": params, "architect_note": note.strip(),
            "usage_f1": get_client().last_usage.__dict__.copy()}


# ── f2 InputWriter ──────────────────────────────────────────────────────────
def f2_input(physics: str, params: dict) -> dict:
    out = _http("POST", "/generate", {"physics": physics, "params": params})
    return {"line_count": out.get("line_count", 0),
            "input_ok": out.get("line_count", 0) > 0}


# ── f3 Runner ───────────────────────────────────────────────────────────────
def f3_run(physics: str, params: dict) -> dict:
    started = _http("POST", "/run", {"physics": physics, "params": params})
    run_id = started["run_id"]
    t0 = time.time()
    status = started.get("status", "pending")
    while status not in TERMINAL and time.time() - t0 < TIMEOUT_S:
        time.sleep(POLL_S)
        status = _http("GET", f"/runs/{run_id}").get("status", "")
    return {"run_id": run_id, "status": status,
            "wall_s": round(time.time() - t0, 1),
            "completed": status == "done"}


# ── f4 Reviewer ─────────────────────────────────────────────────────────────
def f4_review(run_id: str) -> dict:
    try:
        rec = _http("GET", f"/runs/{run_id}")
    except Exception as e:
        return {"valid": False, "review": f"could not fetch run: {e}"}
    metrics = {k: v for k, v in rec.get("metrics", {}).items() if "series" not in k}
    llm = get_client()
    sys_p = ("You are reviewing a grain-growth phase-field result. In one "
             "sentence, state whether the metrics indicate a physically valid "
             "run (parabolic kinetics, grain reduction). Be terse.")
    review = llm.complete(system=sys_p,
                          messages=[{"role": "user", "content": f"metrics={metrics}"}],
                          max_tokens=80)
    return {"metrics": metrics, "review": review.strip(),
            "usage_f4": get_client().last_usage.__dict__.copy()}


# ── f5 Report (capability row) ──────────────────────────────────────────────
# -- f6 Skeptic (physics-grounded falsification) -----------------------------
def f6_skeptic(run_id: str, physics: str, params: dict) -> dict:
    """Adversarially falsify the completed run against physics invariants.
    Distinct from the Reviewer (f4): f4 asks 'does this look valid?' (LLM);
    f6 applies exact/quantitative physics laws and returns a verdict."""
    try:
        rec = _http("GET", f"/runs/{run_id}")
    except Exception as e:
        return {"credible": None, "skeptic_error": f"could not fetch run: {e}"}
    task_dir = rec.get("run_dir")
    if not task_dir:
        return {"credible": None, "skeptic_error": "run_dir not in run record"}
    n0 = params.get("n_grains") or params.get("grain_num") or params.get("N0")
    try:
        if physics == "spinodal":
            verdict = skeptic.falsify(task_dir, physics="spinodal")
        else:
            verdict = skeptic.falsify(task_dir, physics="grain_growth", n0_expected=n0)
    except Exception as e:
        return {"credible": None, "skeptic_error": f"{type(e).__name__}: {e}"}
    return {"credible": verdict.get("credible"),
            "falsified_by": verdict.get("falsified_by", []),
            "skeptic_diagnosis": verdict.get("diagnosis", "")}


def orchestrate(physics: str, params: dict, backend_name: str) -> dict:
    t0 = time.time()
    row = {"backend": backend_name,
           "model": os.environ.get("LLM_MODEL", "?"),
           "provider": os.environ.get("LLM_PROVIDER", "anthropic"),
           "physics": physics, "params": params}
    try:
        a = f1_architect(physics, params); row.update(architect_note=a["architect_note"])
        i = f2_input(physics, params);      row.update(input_ok=i["input_ok"],
                                                       input_lines=i["line_count"])
        if not i["input_ok"]:
            row.update(completed=False, valid=False, stage_failed="f2_input")
            return _finish(row, t0)
        r = f3_run(physics, params);        row.update(run_id=r["run_id"],
                                                       completed=r["completed"],
                                                       run_status=r["status"],
                                                       wall_s=r["wall_s"])
        if not r["completed"]:
            row.update(valid=False, stage_failed="f3_run")
            return _finish(row, t0)
        v = f4_review(r["run_id"])
        row.update(review=v.get("review", ""),
                   valid="valid" in v.get("review", "").lower(),
                   metrics=v.get("metrics", {}))

        # f6 Skeptic: physics-grounded falsification of the completed run
        sk_res = f6_skeptic(r["run_id"], physics, params)
        row.update(credible=sk_res.get("credible"),
                   falsified_by=sk_res.get("falsified_by", []),
                   skeptic_diagnosis=sk_res.get("skeptic_diagnosis", ""))
    except Exception as e:
        row.update(completed=False, valid=False, error=f"{type(e).__name__}: {e}")
    return _finish(row, t0)



def _fetch_log(run_id: str) -> str:
    """Best-effort read of the run's solver log for failure diagnosis."""
    try:
        rec = _http("GET", f"/runs/{run_id}")
    except Exception:
        return ""
    import os
    lp = rec.get("log_path") or ""
    if lp and os.path.exists(lp):
        try:
            return open(lp, errors="ignore").read()
        except Exception:
            return ""
    rd = rec.get("run_dir") or ""
    if rd and os.path.isdir(rd):
        from pathlib import Path as _P
        for cand in (_P(rd) / "run.log",):
            if cand.exists():
                return cand.read_text(errors="ignore")
        hits = sorted(_P(rd).glob("*.log"))
        if hits:
            return hits[0].read_text(errors="ignore")
    return ""



def orchestrate_with_recovery(physics: str, params: dict,
                              backend_name: str) -> dict:
    """Closed-loop variant: generate -> run -> verify, and on failure diagnose
    the cause, correct the params, and retry up to recovery.MAX_ATTEMPTS.

    Honest contract: a task is reported credible ONLY if a generated+run input
    passes the Skeptic. If attempts are exhausted, the task is flagged
    outside_envelope=True with the full correction history, never silently
    reported as valid."""
    t0 = time.time()
    row = {"backend": backend_name,
           "model": os.environ.get("LLM_MODEL", "?"),
           "provider": os.environ.get("LLM_PROVIDER", "anthropic"),
           "physics": physics, "params0": dict(params),
           "recovery": True}
    history = []
    params_try = dict(params)
    final = {"credible": None, "completed": False}

    try:
        f1_architect(physics, params_try)  # plan once; corrections are param-level
        for attempt in range(recovery.MAX_ATTEMPTS):
            attempt_rec = {"attempt": attempt, "params": dict(params_try)}

            # generate
            i = f2_input(physics, params_try)
            if not i["input_ok"]:
                diag = {"class": "GENERATION_FAILED",
                        "evidence": "f2 produced no input", "reason": "generation failed"}
                params_try, change = recovery.apply_correction(params_try, diag)
                attempt_rec.update(stage="f2_input", diagnosis=diag, change=change)
                history.append(attempt_rec)
                if recovery.correction_exhausted(history):
                    break
                continue

            # run
            r = f3_run(physics, params_try)
            if not r["completed"]:
                log = _fetch_log(r["run_id"])
                diag = recovery.classify_failure(log, completed=False)
                params_try, change = recovery.apply_correction(params_try, diag)
                attempt_rec.update(stage="f3_run", run_id=r["run_id"],
                                   diagnosis=diag, change=change)
                history.append(attempt_rec)
                if recovery.correction_exhausted(history):
                    break
                continue

            # verify (Skeptic is the binding check)
            sk = f6_skeptic(r["run_id"], physics, params_try)
            if sk.get("credible") is True:
                attempt_rec.update(stage="credible", run_id=r["run_id"], diagnosis=None)
                history.append(attempt_rec)
                final = {"credible": True, "completed": True, "run_id": r["run_id"]}
                break

            # completed but falsified -> diagnose from the physics verdict
            log = _fetch_log(r["run_id"])
            diag = recovery.classify_failure(log, completed=True, skeptic_verdict=sk)
            params_try, change = recovery.apply_correction(params_try, diag)
            attempt_rec.update(stage="f6_skeptic", run_id=r["run_id"],
                               falsified_by=sk.get("falsified_by", []),
                               diagnosis=diag, change=change)
            history.append(attempt_rec)
            if recovery.correction_exhausted(history):
                break

        row.update(attempts=len(history),
                   correction_history=history,
                   credible=final["credible"],
                   completed=final["completed"],
                   outside_envelope=(final.get("credible") is not True),
                   params_final=params_try)
    except Exception as e:
        row.update(error=f"{type(e).__name__}: {e}",
                   correction_history=history, credible=None,
                   outside_envelope=True)
    return _finish(row, t0)


def _finish(row: dict, t0: float) -> dict:
    row["total_wall_s"] = round(time.time() - t0, 1)
    return row


def main():
    ap = argparse.ArgumentParser(description="AutoMOOSE headless orchestrator (W7b)")
    ap.add_argument("--physics", default="grain_growth")
    ap.add_argument("--params", default='{"T": 800, "n_grains": 50}')
    ap.add_argument("--backend-name", default=os.environ.get("LLM_MODEL", "model"))
    a = ap.parse_args()
    row = orchestrate(a.physics, json.loads(a.params), a.backend_name)
    print(json.dumps(row, indent=2))


if __name__ == "__main__":
    main()
