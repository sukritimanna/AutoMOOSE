"""Generate the LaTeX tables for response comment 1.2 directly from scorer output.

Reads evalset_scores.json (from score_evalset.py) and emits two booktabs tables:
  Table 1: per-regime summary (headline) with per-gate counts + tiered success
  Table 2: per-task detail (full 25 rows, for SI) with metrics + gate ticks

No numbers are typed by hand -- everything comes from the real scored JSON, so the
tables cannot contain fabricated values. Run after scoring the production suite:

    python3 make_1p2_tables.py --scores scores_prod.json --out tables_1p2.tex
"""
import json, argparse
from pathlib import Path

REGIME_ORDER = ["core", "resolution", "formulation", "robustness",
                "3d_stress", "high_T_stress", "resolution_stress"]
REGIME_LABEL = {
    "core": "Core ($T$, $N$ sweep)",
    "resolution": "Resolution / domain",
    "formulation": "Formulation (Lin.\\ Interface)",
    "robustness": "Robustness (seeds)",
    "3d_stress": "3D",
    "high_T_stress": "High-$T$ stress",
    "resolution_stress": "Density stress",
}
GATES = ["G1_input_valid", "G2_completed", "G3_coarsened",
         "G4_kinetics", "G5_positive_rate"]


def tick(b):
    return "\\checkmark" if b else "\\texttimes"


def per_regime_table(rows):
    # aggregate
    agg = {}
    for r in rows:
        reg = r["regime"]
        a = agg.setdefault(reg, {"n": 0, **{g: 0 for g in GATES},
                                 "core_ok": 0, "full_ok": 0})
        a["n"] += 1
        g = r["gates"]
        for k in GATES:
            a[k] += int(g[k])
        # tiered: core success = G1&G2&G3 (valid, runs, coarsens correctly)
        core_ok = g["G1_input_valid"] and g["G2_completed"] and g["G3_coarsened"]
        a["core_ok"] += int(core_ok)
        a["full_ok"] += int(r["success"])   # all five

    order = [k for k in REGIME_ORDER if k in agg] + \
            [k for k in agg if k not in REGIME_ORDER]
    N = sum(a["n"] for a in agg.values())
    tot = {k: sum(agg[r][k] for r in agg) for k in
           ["n", *GATES, "core_ok", "full_ok"]}

    L = []
    L.append("\\begin{table}[t]")
    L.append("\\centering\\small")
    L.append("\\caption{AutoMOOSE performance across the $n{=}25$ benchmark regimes. "
             "G1: valid input generated; G2: ran to completion; G3: coarsened "
             "($N_f<N_0$); G4: parabolic (Burke--Turnbull) kinetics ($R^2\\ge0.90$); "
             "G5: positive rate constant. \\emph{Valid \\& runs} counts G1--G3 "
             "(agent produced a valid, executing, physically-correct simulation); "
             "\\emph{Full} counts all five gates including quantitative kinetics.}")
    L.append("\\label{tab:benchmark_regime}")
    L.append("\\begin{tabular}{lcccccccc}")
    L.append("\\toprule")
    L.append("Regime & $n$ & G1 & G2 & G3 & G4 & G5 & Valid\\,\\&\\,runs & Full\\\\")
    L.append("\\midrule")
    for reg in order:
        a = agg[reg]
        L.append(f"{REGIME_LABEL.get(reg, reg)} & {a['n']} & "
                 f"{a['G1_input_valid']} & {a['G2_completed']} & {a['G3_coarsened']} & "
                 f"{a['G4_kinetics']} & {a['G5_positive_rate']} & "
                 f"{a['core_ok']}/{a['n']} & {a['full_ok']}/{a['n']}\\\\")
    L.append("\\midrule")
    L.append(f"\\textbf{{Total}} & \\textbf{{{tot['n']}}} & "
             f"\\textbf{{{tot['G1_input_valid']}}} & \\textbf{{{tot['G2_completed']}}} & "
             f"\\textbf{{{tot['G3_coarsened']}}} & \\textbf{{{tot['G4_kinetics']}}} & "
             f"\\textbf{{{tot['G5_positive_rate']}}} & "
             f"\\textbf{{{tot['core_ok']}/{tot['n']}}} & "
             f"\\textbf{{{tot['full_ok']}/{tot['n']}}}\\\\")
    L.append("\\bottomrule")
    L.append("\\end{tabular}")
    L.append("\\end{table}")
    return "\n".join(L)


def per_task_table(rows):
    L = []
    L.append("\\begin{table}[t]")
    L.append("\\centering\\footnotesize")
    L.append("\\caption{Per-task benchmark detail (all 25 tasks). "
             "Gates ordered G1--G5; $N_0\\!\\to\\!N_f$ is initial/final grain count; "
             "$R^2$ is the parabolic-kinetics fit. Dashes indicate metrics "
             "unavailable because the run did not complete.}")
    L.append("\\label{tab:benchmark_pertask}")
    L.append("\\begin{tabular}{llccccccc}")
    L.append("\\toprule")
    L.append("ID & Regime & $N_0\\!\\to\\!N_f$ & $R^2$ & "
             "G1 & G2 & G3 & G4 & G5\\\\")
    L.append("\\midrule")
    for r in sorted(rows, key=lambda x: x["id"]):
        g = r["gates"]
        n0 = r.get("grains_initial"); nf = r.get("grains_final")
        nn = f"{int(n0)}$\\to${int(nf)}" if (n0 is not None and nf is not None) else "--"
        r2 = r.get("parabolic_R2")
        r2s = f"{r2:.2f}" if isinstance(r2, (int, float)) else "--"
        L.append(f"{r['id']} & {r['regime']} & {nn} & {r2s} & "
                 f"{tick(g['G1_input_valid'])} & {tick(g['G2_completed'])} & "
                 f"{tick(g['G3_coarsened'])} & {tick(g['G4_kinetics'])} & "
                 f"{tick(g['G5_positive_rate'])}\\\\")
    L.append("\\bottomrule")
    L.append("\\end{tabular}")
    L.append("\\end{table}")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scores", default="scores_prod.json")
    ap.add_argument("--out", default="tables_1p2.tex")
    a = ap.parse_args()
    data = json.loads(Path(a.scores).read_text())
    rows = data["tasks"]
    header = ("%% Auto-generated from {} -- do not hand-edit numbers.\n"
              "%% Overall: {}/{} succeeded ({:.0f}%%)\n\n").format(
                  a.scores, data.get("n_success", 0), data.get("n", len(rows)),
                  100 * data.get("success_rate", 0))
    out = header + per_regime_table(rows) + "\n\n" + per_task_table(rows) + "\n"
    Path(a.out).write_text(out)
    print(f"Wrote {a.out}")
    print(f"Overall: {data.get('n_success')}/{data.get('n')} "
          f"({100*data.get('success_rate',0):.0f}%)")


if __name__ == "__main__":
    main()
