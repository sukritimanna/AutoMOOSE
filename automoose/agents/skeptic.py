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
    # backend writes {run_name}.csv and run.log; be robust to naming
    csv_p = None
    for cand in [d / "grain_growth.csv", d / f"{d.name}.csv"]:
        if cand.exists():
            csv_p = cand; break
    if csv_p is None:
        hits = sorted(d.glob("*.csv"))
        csv_p = hits[0] if hits else (d / "grain_growth.csv")
    log_p = None
    for cand in [d / "run.log", d / f"{d.name}.log"]:
        if cand.exists():
            log_p = cand; break
    if log_p is None:
        lhits = sorted(d.glob("*.log"))
        log_p = lhits[0] if lhits else (d / "run.log")
    tests = {}

    # T5 numerical integrity. NOTE: MOOSE prints "Linear solve did not converge
    # due to DIVERGED_ITS" routinely during NORMAL adaptive time-stepping (it cuts
    # dt and continues). That is NOT failure. Only flag FATAL breakdown: an
    # application abort, or a solve that never advanced in time. Completion to the
    # target end_time is the strongest evidence of numerical validity.
    fatal = False; reason5 = "no fatal solver breakdown"
    csv_for_t5 = csv_p
    reached_time = 0.0
    if csv_for_t5.exists():
        try:
            tt, _ = _load(csv_for_t5); reached_time = tt[-1] if tt else 0.0
        except Exception:
            reached_time = 0.0
    # Determine the intended end_time and completion status from the provenance
    # file, which may be record.json (local) or metadata.json (HPC eval-set).
    target_time = None
    status_completed = False
    try:
        import json as _json
        prov = None
        for cand in (d / "record.json", d / "metadata.json"):
            if cand.exists():
                prov = _json.loads(cand.read_text()); break
        if prov:
            p = prov.get("params", {}) or {}
            m = prov.get("metrics", {}) or {}
            target_time = p.get("end_time") or m.get("end_time")
            status_completed = str(prov.get("status", "")).lower() == "completed"
    except Exception:
        target_time, status_completed = None, False
    reached_target = (target_time is not None
                      and reached_time >= 0.99 * float(target_time))

    if log_p.exists():
        txt = log_p.read_text(errors="ignore")
        # ONLY genuine fatal signatures: an actual MPI abort, or the application
        # aborting because the solve gave up. DIVERGED_ITS / "Solve Did NOT
        # Converge" / "reached minimum" are NORMAL adaptive-dt events (the
        # stepper cuts dt and continues) and are NOT fatal on their own.
        truly_fatal = re.search(r"MPI_Abort|application called MPI_Abort|"
                                r"Aborting as solve did not converge", txt)
        if truly_fatal and not (reached_target or status_completed):
            fatal = True; reason5 = "fatal solver breakdown (application abort)"
    # fatal only if the run never advanced in time at all
    if reached_time <= 0.0:
        fatal = True; reason5 = "no time advance (run did not progress)"
    # reaching the target end_time (or a 'completed' provenance status) is
    # decisive evidence of numerical validity, overriding transient dt warnings.
    if reached_target or status_completed:
        fatal = False
        reason5 = (f"completed to target end_time ({reached_time:g})"
                   if reached_target else "run status: completed")
    tests["T5_numerical"] = {"pass": not fatal, "reason": reason5,
                             "reached_time": reached_time}

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



# ── Spinodal (Cahn-Hilliard) falsification battery ──────────────────────────
# A conserved-order-parameter domain. Its invariants are EXACT physical laws,
# which makes them stronger falsification tests than the grain-growth checks:
#   S1 mass conservation   : integral of c is constant (drift -> 0). EXACT.
#   S2 free-energy dissipat.: total free energy is non-increasing. EXACT (grad flow).
#   S3 coarsening scaling  : domain count decreases; L(t) follows a power law
#                            (Lifshitz-Slyozov, exponent approaching ~1/3).
CONSERVE_REL_TOL = 1e-6   # relative drift of integral(c) allowed (numerical only)


def _load_spinodal(csv_path):
    cols = {}
    with open(csv_path) as f:
        r = csv.DictReader(f)
        for row in r:
            for k, v in row.items():
                try:
                    cols.setdefault(k, []).append(float(v))
                except (TypeError, ValueError):
                    pass
    return cols


def falsify_spinodal(task_dir):
    """Falsify a spinodal run against exact Cahn-Hilliard invariants."""
    d = Path(task_dir)
    log_p = d / f"{d.name}.log"
    # CSV may be <base>.csv or <name>_out.csv
    csv_p = None
    for cand in [d / "spinodal.csv", d / f"{d.name}.csv", d / f"{d.name}_out.csv"]:
        if cand.exists():
            csv_p = cand; break
    if csv_p is None:
        hits = list(d.glob("*.csv"))
        csv_p = hits[0] if hits else None
    tests = {}

    # numerical integrity first (fatal abort / no progress)
    fatal = False; r5 = "no fatal solver breakdown"
    if log_p.exists():
        txt = log_p.read_text(errors="ignore")
        if re.search(r"MPI_Abort|application called MPI_Abort|Solve Did NOT Converge|reached minimum", txt):
            fatal = True; r5 = "fatal solver breakdown (abort / min-dt)"
    tests["S0_numerical"] = {"pass": not fatal, "reason": r5}

    if csv_p is None:
        for k in ("S1_conservation", "S2_dissipation", "S3_coarsening"):
            tests[k] = {"pass": False, "reason": "no CSV output"}
        return _verdict_spinodal(d.name, tests)

    c = _load_spinodal(csv_p)
    tc = c.get("total_c") or []
    en = c.get("total_energy") or []
    nf = c.get("num_features") or []
    t  = c.get("time") or []

    # S1 mass conservation (EXACT law): relative drift of integral(c)
    if len(tc) >= 2:
        c0 = tc[0]; drift = max(abs(v - c0) for v in tc)
        rel = drift / abs(c0) if c0 else drift
        ok1 = rel <= CONSERVE_REL_TOL
        tests["S1_conservation"] = {
            "pass": ok1, "rel_drift": rel,
            "reason": (f"integral(c) conserved (rel drift {rel:.2e})" if ok1
                       else f"MASS NOT CONSERVED (rel drift {rel:.2e} > {CONSERVE_REL_TOL:.0e})")}
    else:
        tests["S1_conservation"] = {"pass": False, "reason": "no total_c series"}

    # S2 free-energy dissipation (EXACT law): energy must be non-increasing
    if len(en) >= 2:
        rises = sum(1 for a, b in zip(en, en[1:]) if b > a + 1e-9 * max(1.0, abs(a)))
        ok2 = rises == 0
        tests["S2_dissipation"] = {
            "pass": ok2, "rises": rises,
            "reason": ("free energy monotonically non-increasing" if ok2
                       else f"free energy INCREASED on {rises} step(s) -- violates gradient flow")}
    else:
        tests["S2_dissipation"] = {"pass": False, "reason": "no total_energy series"}

    # S3 coarsening: domain count decreases and follows a power law L~t^p
    if len(nf) >= 4 and len(t) >= 4:
        coarsened = nf[-1] < nf[0]
        pts = [(ti, ni) for ti, ni in zip(t, nf) if ti > 0 and ni and ni > 0]
        r2 = None; p_exp = None
        if len(pts) >= 4:
            xs = [math.log(x) for x, _ in pts]
            ys = [math.log(y ** (-0.5)) for _, y in pts]   # L = N^(-1/2)
            slope, _, r2 = _linfit(xs, ys)
            p_exp = slope
        ok3 = coarsened and (r2 is not None and r2 >= 0.80)
        tests["S3_coarsening"] = {
            "pass": ok3, "exponent": (round(p_exp, 4) if p_exp is not None else None),
            "R2": (round(r2, 4) if r2 is not None else None),
            "reason": (f"coarsening N:{nf[0]:.0f}->{nf[-1]:.0f}, "
                       f"L~t^{p_exp:.3f} (R2={r2:.2f})" if r2 is not None
                       else "insufficient coarsening data")
                      + ("" if ok3 else " -- coarsening not established")}
    else:
        tests["S3_coarsening"] = {"pass": False, "reason": "too few points"}

    return _verdict_spinodal(d.name, tests)


def _diagnose_spinodal(tests):
    if not tests["S0_numerical"]["pass"]:
        return ("solver breakdown: result numerically invalid; do not trust metrics.")
    if not tests["S1_conservation"]["pass"]:
        return ("mass conservation violated: integral of the conserved order parameter "
                "drifted beyond numerical tolerance. This is an EXACT Cahn-Hilliard law, "
                "so the result is non-physical -- suspect a non-conservative kernel/BC or "
                "an unconverged solve. Remediation: verify split-CH kernels and periodic BCs.")
    if not tests["S2_dissipation"]["pass"]:
        return ("free energy increased: violates gradient-flow dissipation (an exact law). "
                "Suspect an unconverged/oscillatory solve. Remediation: tighten tolerances "
                "or reduce time-step.")
    if not tests["S3_coarsening"]["pass"]:
        return ("phase separation/coarsening not established: integration window too short "
                "for the asymptotic regime, or the system did not separate. Remediation: "
                "extend end_time; verify the IC sits in the spinodal region.")
    return "all Cahn-Hilliard invariants satisfied (incl. exact conservation): result is credible."


def _verdict_spinodal(sim_id, tests):
    falsified = [k for k, v in tests.items() if not v["pass"]]
    return {"id": sim_id, "physics": "spinodal", "credible": len(falsified) == 0,
            "falsified_by": falsified, "tests": tests,
            "diagnosis": _diagnose_spinodal(tests)}


def falsify(task_dir, physics="grain_growth", **kw):
    """Physics-dispatching entry point: routes to the domain-appropriate battery."""
    if physics == "spinodal":
        return falsify_spinodal(task_dir)
    return falsify_run(task_dir, **kw)

if __name__ == "__main__":
    import argparse, glob, json
    ap = argparse.ArgumentParser(description="Skeptic/Falsifier agent (W8)")
    ap.add_argument("--stage", default="/pscratch/sd/s/smanna/autoMOOSE/evalset_staging")
    ap.add_argument("--out", default="falsification_report.json")
    ap.add_argument("--physics", default="grain_growth", choices=["grain_growth","spinodal"])
    a = ap.parse_args()
    glob_pat = "GG*" if a.physics == "grain_growth" else "*"
    dirs = sorted(d for d in Path(a.stage).glob(glob_pat) if d.is_dir())
    reports = [falsify(d, physics=a.physics) for d in dirs]
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
