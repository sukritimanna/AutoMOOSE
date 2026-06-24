"""Semi-automated W6: generate the eval-set MOOSE inputs via AutoMOOSE, stage for HPC.

For each task in the eval set, call AutoMOOSE's /generate endpoint (the f1->f2 agent
step) to produce a MOOSE input file, and write it into a per-sim directory matching
the Perlmutter layout:  staging/<TASK_ID>/<TASK_ID>.i  + metadata.json

This is the AGENT contribution (intent -> validated input) done locally and fast,
with no MOOSE execution. The resulting staging/ tree is scp'd to Perlmutter and run
as a SLURM batch; results are scored afterward with run_evalset's G1-G5 gates.

Usage:
    export BACKEND_URL=http://127.0.0.1:8000
    python stage_inputs.py --evalset validation/evalset_grain_growth_fast.json \
        --out staging --backend-name Claude
"""
import os, sys, json, argparse, time
from pathlib import Path
from urllib import request as _rq

BACKEND = os.environ.get("BACKEND_URL", "http://127.0.0.1:8000").rstrip("/")


def _post(path, body):
    req = _rq.Request(f"{BACKEND}{path}", data=json.dumps(body).encode(),
                      method="POST", headers={"Content-Type": "application/json"})
    with _rq.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--evalset", default="validation/evalset_grain_growth_fast.json")
    ap.add_argument("--out", default="staging")
    ap.add_argument("--backend-name", default="Claude")
    a = ap.parse_args()

    es = json.loads(Path(a.evalset).read_text())
    outroot = Path(a.out); outroot.mkdir(parents=True, exist_ok=True)
    manifest = []

    for t in es["tasks"]:
        tid = t["id"]
        d = outroot / tid; d.mkdir(exist_ok=True)
        try:
            gen = _post("/generate", {"physics": t["physics"], "params": t["params"]})
            text = gen.get("input_file") or gen.get("input") or ""
            lines = gen.get("line_count", text.count("\n") + 1 if text else 0)
            ok = bool(text) and lines > 0
            (d / f"{tid}.i").write_text(text)
            status = "input_generated" if ok else "generate_failed"
        except Exception as e:
            text = ""; lines = 0; ok = False; status = f"error: {type(e).__name__}: {e}"

        meta = {"sim_id": tid, "prompt": t["prompt"], "regime": t["regime"],
                "physics": t["physics"], "params": t["params"],
                "backend_name": a.backend_name, "input_ok": ok,
                "input_line_count": lines, "status": status,
                "staged_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        (d / "metadata.json").write_text(json.dumps(meta, indent=2))
        manifest.append({"id": tid, "regime": t["regime"], "input_ok": ok,
                         "lines": lines, "status": status})
        print(f"{tid:<6} input_ok={int(ok)} lines={lines:<4} {status}")

    (outroot / "manifest.json").write_text(json.dumps(
        {"evalset": es["name"], "n": len(manifest),
         "n_input_ok": sum(m["input_ok"] for m in manifest),
         "tasks": manifest}, indent=2))
    ok = sum(m["input_ok"] for m in manifest)
    print(f"\nStaged {ok}/{len(manifest)} inputs successfully into {outroot}/")
    print(f"Next: scp -r {outroot}/ perlmutter:/pscratch/sd/s/smanna/automoose_evalset/")


if __name__ == "__main__":
    main()
