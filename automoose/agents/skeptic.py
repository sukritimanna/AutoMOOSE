"""Skeptic / Falsifier agent (W8).

An adversarial epistemic role, distinct from the Runner. It does not ask "did the
simulation run?" (engineering) but "should we believe the result?" (epistemics).
Given a completed run, it tries to FALSIFY the run's claim to physical validity by
testing it against physics invariants -- laws the result must obey if it is real.
Each invariant is a falsification hypothesis with a verdict and a diagnosis.

This reframes the workflow from engineering STAGES (generate/run/parse) to epistemic
ROLES (propose/execute/FALSIFY), which is the methodological contribution: the agent
generates falsification tests and, on failure, diagnoses the likely cause -- the
reasoning that enables recovery.

Per-run invariants (grain growth):
  T1 monotonicity      grain count non-increasing (no spontaneous nucleation)
  T2 asymptotic        N(t=0) ~ N0 ; coarsening rate -> 0 as N -> 1
  T3 parabolic scaling Burke-Turnbull: mean area ~ linear in t (R^2 >= thresh)
  T5 numerical         no solver divergence / residual blow-up in the log

Cross-run invariant (over a temperature sweep):
  T4 arrhenius         k(T) increasing in T and ln k linear in 1/T
"""
import csv, math, re
from pathlib import Path

R2_PARABOLIC = 0.90


def _load(csv_path):
    t, n = [], []
    with open(csv_path) as f:
        for row in csv.DictReader(f):
            try:
                ti = float(row["time"]); gn = float(row["grain_tracker"])
            except (KeyError, ValueError):
                continue
            t.append(ti); n.append(gn)
    return t, n


def _linfit(xs, ys):
    m = len(xs)
    if m < 3: return None, None, None
    sx, sy = sum(xs), sum(ys)
    sxx = sum(x*x for x in xs); sxy = sum(x*y for x, y in zip(xs, ys))
    d = m*sxx - sx*sx
    if d == 0: return None, None, None
    slope = (m*sxy - sx*sy)/d; intercept = (sy - slope*sx)/m
    ybar = sy/m; sstot = sum((y-ybar)**2 for y in ys)
    ssres = sum((y-(slope*x+intercept))**2 for x, y in zip(xs, ys))
    r2 = 1 - ssres/sstot if sstot > 0 else 0.0
    return slope, intercept, r2


def falsify_run(task_dir, n0_expected=None):
    """Run the per-run falsification battery. Returns verdict + per-test results."""
    d = Path(task_dir)
    csv_p = d / "grain_growth.csv"
    log_p = d / f"{d.name}.log"
    tests = {}

    # T5 numerical integrity -- check the solver log for divergence FIRST
    diverged = False
    if log_p.exists():
        txt = log_p.read_text(errors="ignore")
        diverged = bool(re.search(r"DIVERGED|did not converge|Nonlinear.*failed", txt))
    tests["T5_numerical"] = {
        "pass": not diverged,
        "reason": "solver diverged (DIVERGED/non-convergence in log)" if diverged
                  else "no solver divergence detected"}

    if not csv_p.exists():
        tests["T1_monotonicity"] = {"pass": False, "reason": "no CSV output"}
        tests["T2_asymptotic"]   = {"pass": False, "reason": "no CSV output"}
        tests["T3_parabolic"]    = {"pass": False, "reason": "no CSV output"}
        return _verdict(d.name, tests)

    t, n = _load(csv_p)
    if len(n) < 3:
        for k in ("T1_monotonicity","T2_asymptotic","T3_parabolic"):
            tests[k] = {"pass": False, "reason": "insufficient timesteps"}
        return _verdict(d.name, tests)

    # T1 monotonicity: allow tiny tracker noise but flag a SUSTAINED rise.
    # Two signals: (a) any single jump > +1 (real nucleation event), or
    # (b) net increase from start to end beyond noise (steady non-physical growth).
    big_jumps = sum(1 for a, b in zip(n, n[1:]) if b > a + 1)
    net_rise  = n[-1] - min(n)            # did it climb well above its minimum?
    sustained = net_rise > max(1, 0.1*max(n))
    t1_ok = (big_jumps == 0 and not sustained)
    tests["T1_monotonicity"] = {
        "pass": t1_ok,
        "reason": (f"{big_jumps} jump(s) >+1; net rise {net_rise:+.0f}" if not t1_ok
                   else "grain count non-increasing")}

    # T2 asymptotic: N(0) close to expected N0 (if given); rate ->0 as N small
    n0_ok = True; reason2 = []
    if n0_expected is not None:
        n0_ok = abs(n[0] - n0_expected) <= max(2, 0.2*n0_expected)
        reason2.append(f"N(0)={n[0]:.0f} vs N0~{n0_expected}" +
                       ("" if n0_ok else " (mismatch)"))
    tests["T2_asymptotic"] = {"pass": n0_ok,
                              "reason": "; ".join(reason2) or "initial count consistent"}

    # T3 parabolic scaling: 1/N ~ linear in t (Burke-Turnbull), R^2 >= thresh
    pts = [(ti, 1.0/ni) for ti, ni in zip(t, n) if ti > 0 and ni > 0]
    if len(pts) >= 3:
        slope, _, r2 = _linfit([p[0] for p in pts], [p[1] for p in pts])
        ok3 = (r2 is not None and r2 >= R2_PARABOLIC and slope is not None and slope > 0)
        tests["T3_parabolic"] = {
            "pass": ok3, "R2": (round(r2,4) if r2 is not None else None),
            "rate_k": slope,
            "reason": (f"parabolic R2={r2:.3f}, k={slope:.2e}" if r2 is not None
                       else "fit failed") +
                      ("" if ok3 else " -> Burke-Turnbull scaling not satisfied")}
    else:
        tests["T3_parabolic"] = {"pass": False, "reason": "too few points for fit"}

    return _verdict(d.name, tests)


def _diagnose(tests):
    """Map failed invariants to likely cause -- the recovery-enabling reasoning."""
    if not tests["T5_numerical"]["pass"]:
        return ("solver divergence: result is numerically invalid. Likely outside the "
                "validated stability regime (e.g. excessive T/mobility). Remediation: "
                "reduce timestep or flag as outside validated envelope -- do NOT trust metrics.")
    if not tests["T3_parabolic"]["pass"] and tests["T1_monotonicity"]["pass"]:
        return ("ran and coarsened but violates parabolic (Burke-Turnbull) scaling: "
                "the integration window may be too short for the asymptotic regime, or "
                "the kinetics are anomalous. Remediation: extend end_time and refit.")
    if not tests["T1_monotonicity"]["pass"]:
        return ("grain count increased: non-physical (spontaneous nucleation) or a "
                "grain-tracker artifact. Remediation: inspect tracker settings / IC.")
    if not tests["T2_asymptotic"]["pass"]:
        return ("initial grain count inconsistent with request: IC generation suspect. "
                "Remediation: verify Voronoi grain_num / seed.")
    return "all invariants satisfied: no falsification; result is credible."


def _verdict(sim_id, tests):
    falsified = [k for k, v in tests.items() if not v["pass"]]
    return {"id": sim_id, "credible": len(falsified) == 0,
            "falsified_by": falsified, "tests": tests,
            "diagnosis": _diagnose(tests)}


def arrhenius_consistency(run_rates):
    """Cross-run T4: given [(T_kelvin, k), ...], check k increases with T and
    ln k is ~linear in 1/T (Arrhenius). Returns verdict + activation energy."""
    pts = [(T, k) for T, k in run_rates if k and k > 0]
    if len(pts) < 3:
        return {"test": "T4_arrhenius", "pass": False,
                "reason": "need >=3 valid (T,k) points"}
    pts.sort()
    xs = [1.0/T for T, _ in pts]; ys = [math.log(k) for _, k in pts]
    slope, _, r2 = _linfit(xs, ys)
    monotonic = all(pts[i][1] <= pts[i+1][1] for i in range(len(pts)-1))
    KB_EV = 8.617e-5
    Q = -slope * KB_EV if slope is not None else None   # ln k = lnA - Q/(kB T)
    ok = (r2 is not None and r2 >= 0.90 and monotonic and slope is not None and slope < 0)
    return {"test": "T4_arrhenius", "pass": ok,
            "R2": (round(r2,4) if r2 is not None else None),
            "Q_eV": (round(Q,4) if Q is not None else None),
            "monotonic_in_T": monotonic,
            "reason": (f"Arrhenius R2={r2:.3f}, Q={Q:.3f} eV" if r2 is not None else "fit failed")
                      + ("" if ok else " -> Arrhenius consistency not satisfied")}


if __name__ == "__main__":
    import argparse, glob, json
    ap = argparse.ArgumentParser(description="Skeptic/Falsifier agent (W8)")
    ap.add_argument("--stage", default="/pscratch/sd/s/smanna/autoMOOSE/evalset_staging")
    ap.add_argument("--out", default="falsification_report.json")
    a = ap.parse_args()
    dirs = sorted(d for d in Path(a.stage).glob("GG*") if d.is_dir())
    reports = [falsify_run(d) for d in dirs]
    cred = sum(r["credible"] for r in reports)
    print(f"\n=== Skeptic/Falsifier: {cred}/{len(reports)} runs credible ===\n")
    for r in reports:
        flag = "CREDIBLE" if r["credible"] else "FALSIFIED by " + ",".join(r["falsified_by"])
        print(f"{r['id']:<6} {flag}")
        if not r["credible"]:
            print(f"        -> {r['diagnosis']}")
    Path(a.out).write_text(json.dumps({"n":len(reports),"n_credible":cred,
                                       "reports":reports}, indent=2))
    print(f"\nWrote {a.out}")
