"""Generate the LaTeX table for W5 (ablation / SOTA baseline) from the harness JSON.

Reads w5_results.json (from ablation_w5.py) and emits a booktabs table comparing
AutoMOOSE's deterministic plugin against raw frontier-model prompting, on G1 input
validity, reported both strict and lenient (--allow-unused). All numbers come from
the real harness output -- nothing is hand-typed.

    python3 make_w5_table.py --results w5_results.json --out w5_table.tex
"""
import json, argparse
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default="w5_results.json")
    ap.add_argument("--out", default="w5_table.tex")
    a = ap.parse_args()
    d = json.loads(Path(a.results).read_text())
    n = len(d["tasks"])

    L = []
    L.append("%% Auto-generated from {} -- do not hand-edit numbers.".format(a.results))
    L.append("\\begin{table}[t]")
    L.append("\\centering\\small")
    L.append("\\caption{Ablation and baseline comparison on $n{=}" + str(n) + "$ "
             "core grain-growth tasks, scored on G1 (input validity via "
             "\\texttt{--check-input}). \\emph{AutoMOOSE} is the deterministic "
             "plugin; \\emph{raw} conditions prompt the bare model with the same "
             "task and no plugin scaffolding. \\emph{Strict} requires a clean parse; "
             "\\emph{lenient} (\\texttt{--allow-unused}) ignores deprecated-but-harmless "
             "parameters, matching the checking applied to AutoMOOSE's own benchmark runs.}")
    L.append("\\label{tab:w5_ablation}")
    L.append("\\begin{tabular}{lcc}")
    L.append("\\toprule")
    L.append("Condition & G1 strict & G1 lenient\\\\")
    L.append("\\midrule")
    L.append(f"AutoMOOSE plugin & \\textbf{{{d['plugin_G1_strict']}}} & "
             f"\\textbf{{{d['plugin_G1_lenient']}}}\\\\")
    L.append("\\midrule")
    for name, m in d["models"].items():
        prov = m.get("model", "")
        L.append(f"raw {name} ({prov}) & {m['raw_G1_strict']} & {m['raw_G1_lenient']}\\\\")
    L.append("\\bottomrule")
    L.append("\\end{tabular}")
    L.append("\\end{table}")
    Path(a.out).write_text("\n".join(L) + "\n")
    print(f"Wrote {a.out}")
    print(f"  AutoMOOSE plugin: {d['plugin_G1_strict']} strict, {d['plugin_G1_lenient']} lenient")
    for name, m in d["models"].items():
        print(f"  raw {name}: {m['raw_G1_strict']} strict, {m['raw_G1_lenient']} lenient")


if __name__ == "__main__":
    main()
