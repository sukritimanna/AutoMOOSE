"""Score the AutoMOOSE eval-set runs against the G1-G5 gates (W6).

Standalone: reads each staged task dir (metadata.json + grain_growth.csv) and
applies the five objective success gates. No backend needed. Run on Perlmutter
(or anywhere the staging tree is) after the SLURM batch completes.

    python3 score_evalset.py --stage /pscratch/sd/s/smanna/autoMOOSE/evalset_staging \
        --evalset evalset_grain_growth_fast.json --out evalset_scores.json

CSV columns produced by the grain_growth plugin: time, DOFs, dt, grain_tracker, n_elements
  -> grain_tracker is the live grain count; time is simulated time.

Gates:
  G1 input_valid   : metadata.input_ok (agent produced a parseable input)
  G2 completed     : metadata.status == 'completed' (ran to completion, no divergence)
  G3 coarsened     : grain_tracker decreased (final < initial)
  G4 kinetics      : parabolic grain-growth fit R^2 >= 0.90
                     (mean grain AREA ~ linear in time:  (L^2) vs t, L ~ 1/sqrt(N))
  G5 positive_rate : fit slope k > 0
A task SUCCEEDS iff G1..G5 all pass.
"""
import json, argparse, glob, csv, math
from pathlib import Path

R2_MIN = 0.90


def _read_csv(path):
    t, n = [], []
    with open(path) as f:
        r = csv.DictReader(f)
        for row in r:
            try:
                ti = float(row["time"]); gn = float(row["grain_tracker"])
            except (KeyError, ValueError):
                continue
            if gn > 0:
                t.append(ti); n.append(gn)
    return t, n


def _parabolic_fit(t, n):
    """Grain growth: mean area A ~ 1/N ~ k*t (parabolic R(t)). Fit A=1/N vs t,
    return (R2, slope). Uses points after t=0."""
    pts = [(ti, 1.0 / ni) for ti, ni in zip(t, n) if ti > 0 and ni > 0]
    if len(pts) < 3:
        return None, None
    xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
    nN = len(xs); sx = sum(xs); sy = sum(ys)
    sxx = sum(x * x for x in xs); sxy = sum(x * y for x, y in zip(xs, ys))
    denom = nN * sxx - sx * sx
    if denom == 0:
        return None, None
    slope = (nN * sxy - sx * sy) / denom
    intercept = (sy - slope * sx) / nN
    ybar = sy / nN
    ss_tot = sum((y - ybar) ** 2 for y in ys)
    ss_res = sum((y - (slope * x + intercept)) ** 2 for x, y in zip(xs, ys))
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0
    return r2, slope


def score_task(d: Path):
    meta_p = d / "metadata.json"
    meta = json.loads(meta_p.read_text()) if meta_p.exists() else {}
    g1 = bool(meta.get("input_ok"))
    g2 = (meta.get("status") == "completed")

    csv_p = d / "grain_growth.csv"
    g3 = g4 = g5 = False
    n0 = nf = r2 = slope = None
    if csv_p.exists():
        t, n = _read_csv(csv_p)
        if len(n) >= 2:
            n0, nf = n[0], n[-1]
            g3 = nf < n0
            r2, slope = _parabolic_fit(t, n)
            g4 = (r2 is not None and r2 >= R2_MIN)
            g5 = (slope is not None and slope > 0)
    gates = {"G1_input_valid": g1, "G2_completed": g2, "G3_coarsened": g3,
             "G4_kinetics": g4, "G5_positive_rate": g5}
    return {"id": d.name, "regime": meta.get("regime", "?"),
            "gates": gates, "success": all(gates.values()),
            "grains_initial": n0, "grains_final": nf,
            "parabolic_R2": (round(r2, 4) if r2 is not None else None),
            "rate_k": (slope if slope is not None else None),
            "wall_time_s": meta.get("wall_time_s"),
            "status": meta.get("status")}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", default="/pscratch/sd/s/smanna/autoMOOSE/evalset_staging")
    ap.add_argument("--evalset", default="")
    ap.add_argument("--out", default="evalset_scores.json")
    a = ap.parse_args()

    dirs = sorted(Path(p).parent for p in glob.glob(f"{a.stage}/GG*/metadata.json"))
    if not dirs:
        dirs = sorted(d for d in Path(a.stage).glob("GG*") if d.is_dir())
    rows = [score_task(d) for d in dirs]

    succ = sum(r["success"] for r in rows)
    by_regime = {}
    for r in rows:
        s = by_regime.setdefault(r["regime"], [0, 0]); s[1] += 1; s[0] += int(r["success"])
    gate_pass = {g: sum(r["gates"][g] for r in rows) for g in
                 ["G1_input_valid","G2_completed","G3_coarsened","G4_kinetics","G5_positive_rate"]}

    report = {"n": len(rows), "n_success": succ,
              "success_rate": round(succ/len(rows), 3) if rows else 0,
              "by_regime": {k: f"{v[0]}/{v[1]}" for k,v in by_regime.items()},
              "gate_pass_counts": {k: f"{v}/{len(rows)}" for k,v in gate_pass.items()},
              "tasks": rows}
    Path(a.out).write_text(json.dumps(report, indent=2))

    print(f"\n=== AutoMOOSE eval-set: {succ}/{len(rows)} succeeded "
          f"({report['success_rate']*100:.0f}%) ===\n")
    print(f"{'ID':<6} {'regime':<16} {'G1':>3}{'G2':>3}{'G3':>3}{'G4':>3}{'G5':>3}  "
          f"{'N0->Nf':>10} {'R2':>6} {'ok':>4}")
    for r in rows:
        g = r["gates"]
        nn = f"{r['grains_initial']}->{r['grains_final']}" if r['grains_initial'] else "-"
        r2 = f"{r['parabolic_R2']}" if r['parabolic_R2'] is not None else "-"
        print(f"{r['id']:<6} {r['regime']:<16} "
              f"{int(g['G1_input_valid']):>3}{int(g['G2_completed']):>3}"
              f"{int(g['G3_coarsened']):>3}{int(g['G4_kinetics']):>3}{int(g['G5_positive_rate']):>3}  "
              f"{nn:>10} {r2:>6} {('YES' if r['success'] else 'no'):>4}")
    print("\nBy regime:", report["by_regime"])
    print("Gate pass:", report["gate_pass_counts"])
    print(f"\nWrote {a.out}")


if __name__ == "__main__":
    main()
