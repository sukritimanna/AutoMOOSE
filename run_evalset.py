"""Run the AutoMOOSE evaluation set end-to-end and score it (W6).

Loops the headless orchestrator (W7b) over every task in evalset_grain_growth.json,
applies the objective G1-G5 pass criteria to each result, and writes a scored
report + summary. Run under each backend (config.env) to compare models.

    python run_evalset.py --evalset evalset_grain_growth.json --backend-name Claude

WARNING: each task is a full MOOSE run (minutes each). 25 tasks = hours of wall
time. Intended as a launch-and-collect job, not interactive. Use --limit to smoke
test a few first.
"""
import json, argparse, time, sys
from pathlib import Path

# import the orchestrator's single-task entry point
sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    from automoose.agents.orchestrator import orchestrate
except Exception:
    orchestrate = None  # allow --dry-run without the package


def score(row: dict) -> dict:
    """Apply G1-G5 objective gates to one orchestrator result row."""
    m = row.get("metrics", {}) or {}
    gi = m.get("grains_initial"); gf = m.get("grains_final")
    r2 = m.get("parabolic_R2");   k  = m.get("parabolic_k")
    g1 = bool(row.get("input_ok"))
    g2 = bool(row.get("completed"))
    g3 = (gi is not None and gf is not None and gf < gi)
    g4 = (isinstance(r2, (int, float)) and r2 >= 0.90)
    g5 = (isinstance(k, (int, float)) and k > 0)
    gates = {"G1_input_valid": g1, "G2_completed": g2, "G3_coarsened": g3,
             "G4_kinetics": g4, "G5_positive_rate": g5}
    return {"gates": gates, "success": all(gates.values())}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--evalset", default="evalset_grain_growth.json")
    ap.add_argument("--backend-name", default="model")
    ap.add_argument("--limit", type=int, default=0, help="run only first N tasks (smoke test)")
    ap.add_argument("--out", default="evalset_results.json")
    ap.add_argument("--dry-run", action="store_true", help="list tasks without running")
    a = ap.parse_args()

    es = json.loads(Path(a.evalset).read_text())
    tasks = es["tasks"][: a.limit] if a.limit else es["tasks"]

    if a.dry_run or orchestrate is None:
        for t in tasks:
            print(f"{t['id']:<6} [{t['regime']:<16}] T={t['params'].get('T'):<4} "
                  f"n={t['params'].get('num_grains'):<4} :: {t['prompt'][:60]}")
        print(f"\n{len(tasks)} tasks. (dry-run: not executed)")
        return

    results, t0 = [], time.time()
    for i, t in enumerate(tasks, 1):
        print(f"[{i}/{len(tasks)}] {t['id']} {t['regime']} ...", flush=True)
        try:
            row = orchestrate(t["physics"], t["params"], a.backend_name)
        except Exception as e:
            row = {"error": f"{type(e).__name__}: {e}", "completed": False, "input_ok": False}
        s = score(row)
        results.append({"id": t["id"], "regime": t["regime"], "prompt": t["prompt"],
                        "row": row, **s})
        print(f"      success={s['success']}  gates={ {g:int(v) for g,v in s['gates'].items()} }")

    succ = sum(r["success"] for r in results)
    by_regime = {}
    for r in results:
        d = by_regime.setdefault(r["regime"], [0, 0])
        d[1] += 1; d[0] += int(r["success"])
    report = {
        "backend": a.backend_name, "evalset": es["name"], "n_tasks": len(results),
        "n_success": succ, "success_rate": round(succ / len(results), 3),
        "by_regime": {k: f"{v[0]}/{v[1]}" for k, v in by_regime.items()},
        "wall_minutes": round((time.time() - t0) / 60, 1),
        "results": results,
    }
    Path(a.out).write_text(json.dumps(report, indent=2))
    print(f"\n=== {a.backend_name}: {succ}/{len(results)} succeeded "
          f"({report['success_rate']*100:.0f}%) in {report['wall_minutes']} min ===")
    for k, v in report["by_regime"].items():
        print(f"  {k:<18} {v}")
    print(f"\nWrote {a.out}")


if __name__ == "__main__":
    main()
