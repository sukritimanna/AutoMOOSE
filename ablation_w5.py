"""W5 — Ablation + SOTA baseline over the core grain-growth tasks.

Compares, on the same tasks and the same objective gate (G1: does the produced
MOOSE input parse with --check-input?), three conditions per model:

  full   : AutoMOOSE pipeline (f1 architect refines params -> f2 /generate plugin)
  noarch : plugin only (f2 /generate), no LLM architect step
  raw    : the model prompted directly for a MOOSE input, NO plugin scaffolding

across one or more models (Claude / GPT / Qwen) selected by config blocks. The
discriminating signal is the `raw` column: with no plugin, can the bare model
emit a *parseable* MOOSE input at all? G1 needs no simulation, so the whole
ablation runs locally in minutes.

Usage:
  python ablation_w5.py --tasks core8.json --moose "$MOOSE_EXEC" \
      --backend-url http://127.0.0.1:8000 --out w5_results.json
Models are configured via repeated --model NAME:PROVIDER:MODEL[:BASE_URL] flags,
or default to whatever LLM_* is in the environment (single model).
"""
import os, json, argparse, subprocess, tempfile, time
from pathlib import Path
from urllib import request as _rq

# ---- the 8 core tasks (T, num_grains) -- mirrors evalset core regime ----
CORE8 = [
    {"id": "C1", "T": 450, "num_grains": 20},
    {"id": "C2", "T": 475, "num_grains": 20},
    {"id": "C3", "T": 500, "num_grains": 50},
    {"id": "C4", "T": 525, "num_grains": 50},
    {"id": "C5", "T": 550, "num_grains": 50},
    {"id": "C6", "T": 500, "num_grains": 100},
    {"id": "C7", "T": 450, "num_grains": 100},
    {"id": "C8", "T": 525, "num_grains": 100},
]

RAW_PROMPT = (
    "Write a complete MOOSE finite-element input file for a 2D polycrystalline "
    "grain-growth phase-field simulation using the phase_field module's GBEvolution "
    "model with a PolycrystalVoronoi initial condition. Parameters: {n} initial grains, "
    "temperature {T} K, a periodic square domain, and adaptive time stepping. The input "
    "must be directly runnable by a MOOSE phase_field executable. Output ONLY the input "
    "file text, no commentary, no markdown fences."
)


def _check_input(moose_exec: str, text: str) -> dict:
    """G1: does this input parse? Returns {strict, lenient} where lenient uses
    --allow-unused (matching how the real benchmark runs treat AutoMOOSE's own
    inputs), so raw models are not failed on deprecated-but-ignorable params."""
    out = {"strict": False, "lenient": False}
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / "t.i"; f.write_text(text)
        for mode, extra in (("strict", []), ("lenient", ["--allow-unused"])):
            try:
                r = subprocess.run([moose_exec, "-i", str(f), "--check-input"] + extra,
                                   capture_output=True, text=True, timeout=120)
                out[mode] = "Syntax OK" in (r.stdout + r.stderr)
            except Exception:
                out[mode] = False
    return out


def _post(url, path, body):
    req = _rq.Request(url.rstrip("/") + path, data=json.dumps(body).encode(),
                      method="POST", headers={"Content-Type": "application/json"})
    with _rq.urlopen(req, timeout=180) as r:
        return json.loads(r.read().decode())


def _plugin_generate(backend_url, params):
    """f2: deterministic plugin generation via the backend."""
    out = _post(backend_url, "/generate", {"physics": "grain_growth", "params": params})
    return out.get("input_file") or out.get("input") or ""


def _raw_model(client_mod, model_cfg, task):
    """raw: ask the bare model for a MOOSE input, no plugin."""
    # set env for the provider-agnostic client, then call it
    for k in ("LLM_PROVIDER", "LLM_MODEL", "LLM_BASE_URL", "LLM_API_KEY"):
        os.environ.pop(k, None)
    os.environ["LLM_PROVIDER"] = model_cfg["provider"]
    os.environ["LLM_MODEL"] = model_cfg["model"]
    if model_cfg.get("base_url"):
        os.environ["LLM_BASE_URL"] = model_cfg["base_url"]
    if model_cfg.get("api_key"):
        os.environ["LLM_API_KEY"] = model_cfg["api_key"]
    client = client_mod.LLMClient()
    prompt = RAW_PROMPT.format(n=task["num_grains"], T=task["T"])
    txt = client.complete(
        system="You are an expert MOOSE phase-field engineer.",
        messages=[{"role": "user", "content": prompt}])
    # strip accidental markdown fences
    if "```" in txt:
        parts = txt.split("```")
        txt = max(parts, key=len)
        if txt.lstrip().lower().startswith(("moose", "ini", "text")):
            txt = txt.split("\n", 1)[1] if "\n" in txt else txt
    return txt


def run(tasks, moose_exec, backend_url, models, client_mod, out_path):
    results = {"tasks": [t["id"] for t in tasks], "models": {}, "per_task": []}

    # full + noarch use the plugin (model-independent for G1) -> compute once
    plugin_g1 = {}
    for t in tasks:
        params = {"dim": 2, "formulation": "GBEvolution", "T": t["T"],
                  "num_grains": t["num_grains"], "nx": 40, "ny": 40}
        txt = _plugin_generate(backend_url, params)
        chk = _check_input(moose_exec, txt)
        plugin_g1[t["id"]] = chk
        print(f"  plugin {t['id']}: strict={'OK' if chk['strict'] else 'X'} "
              f"lenient={'OK' if chk['lenient'] else 'X'}")

    plugin_strict = sum(v['strict'] for v in plugin_g1.values())
    plugin_lenient = sum(v['lenient'] for v in plugin_g1.values())
    results["plugin_G1_strict"] = f"{plugin_strict}/{len(tasks)}"
    results["plugin_G1_lenient"] = f"{plugin_lenient}/{len(tasks)}"

    # raw per model
    for m in models:
        name = m["name"]
        print(f"\n=== RAW baseline: {name} ({m['provider']}/{m['model']}) ===")
        raw_g1 = {}
        for t in tasks:
            try:
                txt = _raw_model(client_mod, m, t)
                chk = _check_input(moose_exec, txt)
            except Exception as e:
                chk = {"strict": False, "lenient": False, "error": f"{type(e).__name__}: {e}"}
                print(f"  {t['id']} error: {type(e).__name__}: {e}")
            raw_g1[t["id"]] = chk
            print(f"  raw {name} {t['id']}: strict={'OK' if chk['strict'] else 'X'} "
                  f"lenient={'OK' if chk['lenient'] else 'X'}")
        results["models"][name] = {
            "provider": m["provider"], "model": m["model"],
            "raw_G1_strict": f"{sum(v.get('strict') for v in raw_g1.values())}/{len(tasks)}",
            "raw_G1_lenient": f"{sum(v.get('lenient') for v in raw_g1.values())}/{len(tasks)}",
            "raw_detail": raw_g1,
        }

    for t in tasks:
        row = {"id": t["id"], "T": t["T"], "n": t["num_grains"],
               "plugin_strict": plugin_g1[t["id"]]["strict"],
               "plugin_lenient": plugin_g1[t["id"]]["lenient"]}
        for m in models:
            d = results["models"][m["name"]]["raw_detail"][t["id"]]
            row[f"raw_{m['name']}_strict"] = d.get("strict")
            row[f"raw_{m['name']}_lenient"] = d.get("lenient")
        results["per_task"].append(row)

    Path(out_path).write_text(json.dumps(results, indent=2))
    print("\n===== W5 ABLATION SUMMARY (G1 input validity) =====")
    print(f"{'condition':<22} {'strict':>8} {'lenient':>8}")
    print(f"{'AutoMOOSE plugin':<22} {results['plugin_G1_strict']:>8} {results['plugin_G1_lenient']:>8}")
    for name, d in results["models"].items():
        print(f"{'raw '+name:<22} {d['raw_G1_strict']:>8} {d['raw_G1_lenient']:>8}")
    print(f"\nWrote {out_path}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--moose", default=os.environ.get("MOOSE_EXEC", ""))
    ap.add_argument("--backend-url", default="http://127.0.0.1:8000")
    ap.add_argument("--out", default="w5_results.json")
    ap.add_argument("--model", action="append", default=[],
                    help="NAME:PROVIDER:MODEL[:BASE_URL]  (repeatable)")
    ap.add_argument("--client", default="automoose/llm/client.py")
    a = ap.parse_args()

    import importlib.util, sys
    spec = importlib.util.spec_from_file_location("llmclient", a.client)
    client_mod = importlib.util.module_from_spec(spec); sys.modules["llmclient"] = client_mod
    spec.loader.exec_module(client_mod)

    models = []
    for spec_str in a.model:
        parts = spec_str.split(":")
        m = {"name": parts[0], "provider": parts[1], "model": parts[2]}
        if len(parts) > 3:
            m["base_url"] = ":".join(parts[3:])  # rejoin in case URL had a colon
        # api key pulled from env per-provider name (e.g. CLAUDE_KEY / GPT_KEY / QWEN_KEY)
        m["api_key"] = os.environ.get(parts[0].upper() + "_KEY")
        models.append(m)
    if not models:  # single model from current env
        models = [{"name": "model", "provider": os.environ.get("LLM_PROVIDER", "anthropic"),
                   "model": os.environ.get("LLM_MODEL", "?"),
                   "base_url": os.environ.get("LLM_BASE_URL"),
                   "api_key": os.environ.get("LLM_API_KEY")}]

    run(CORE8, a.moose, a.backend_url, models, client_mod, a.out)


if __name__ == "__main__":
    main()
