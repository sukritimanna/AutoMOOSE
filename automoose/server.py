"""
AutoMOOSE — Unified FastAPI Backend v2
One server, all physics plugins, metadata-rich run directories.
"""
import os, re, json, time, asyncio, threading, subprocess, socket
from pathlib import Path
from datetime import datetime
from typing import Optional, List
import anthropic
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import sys
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))
import plugin_registry as registry

app = FastAPI(title="AutoMOOSE", version="2.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])

ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
RUNS_DIR      = Path(os.environ.get("RUNS_DIR", "./runs"))
RUNS_DIR.mkdir(exist_ok=True)

_runs:      dict = {}
_processes: dict = {}

def _get_exec(plugin_id: str) -> str:
    return os.environ.get(registry.get_executable_key(plugin_id), "")

# ── Models ────────────────────────────────────────────────────────────────
class RunRequest(BaseModel):
    physics: str
    params:  dict = {}
    mpi:     int  = 1

class ChatRequest(BaseModel):
    message: str
    physics: str           = "grain_growth"
    run_id:  Optional[str] = None
    history: List[dict]    = []

# ── Helpers ───────────────────────────────────────────────────────────────
def make_run_id() -> str:
    return f"run_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')[:19]}"

def _save(run_id: str):
    rec  = _runs[run_id]
    rdir = Path(rec.get("run_dir", str(RUNS_DIR / run_id)))
    rdir.mkdir(parents=True, exist_ok=True)
    (rdir / "record.json").write_text(
        json.dumps(rec, indent=2, default=str))
    meta = rec.get("metadata", {})
    meta["status"]     = rec.get("status")
    meta["duration_s"] = rec.get("duration_s")
    (rdir / "metadata.json").write_text(
        json.dumps(meta, indent=2, default=str))

def _load_all():
    for p in sorted(RUNS_DIR.glob("*/record.json")):
        try:
            r = json.loads(p.read_text())
            _runs[r["run_id"]] = r
        except: pass

def _parse_csv(csv_path: str) -> dict:
    data = {}
    try:
        with open(csv_path) as f:
            headers = [h.strip() for h in f.readline().strip().split(",")]
            for h in headers: data[h] = []
            for line in f:
                if not line.strip(): continue
                for h, v in zip(headers, line.strip().split(",")):
                    try: data[h].append(float(v))
                    except: pass
    except Exception as e:
        print(f"CSV error: {e}")
    return data

def _parse_metrics(run_id: str):
    r        = _runs[run_id]
    csv_path = r.get("csv_path", "")
    if not csv_path or not Path(csv_path).exists(): return
    csv_data = _parse_csv(csv_path)
    try:    metrics = registry.parse_results(r["physics"], csv_data)
    except: metrics = {}
    _runs[run_id]["metrics"] = metrics
    _save(run_id)

def _generate_narrative(run_id: str):
    """Call Claude API to generate a scientific interpretation of the run."""
    if not ANTHROPIC_KEY:
        print(f"[{run_id}] Skipping narrative: ANTHROPIC_API_KEY not set")
        return
    r       = _runs[run_id]
    metrics = {k: v for k, v in r.get("metrics", {}).items()
               if "series" not in k}
    params  = r.get("params", {})
    if not metrics:
        print(f"[{run_id}] Skipping narrative: no metrics available")
        return

    system_prompt = """You are an expert in MOOSE phase-field simulation
and grain growth kinetics. Given simulation metrics, provide a concise
scientific interpretation (3-5 sentences) grounded in Burke-Turnbull
theory. Always comment on: (1) whether parabolic kinetics were recovered,
(2) the physical meaning of the rate constant trend with temperature,
(3) any anomalous behaviour at low temperature. Be quantitative."""

    user_msg = f"""Interpret these grain growth simulation results:
Temperature: {params.get('T', '?')} K
Initial grains: {metrics.get('grains_initial', '?')}
Final grains: {metrics.get('grains_final', '?')}
Grain reduction: {metrics.get('grain_reduction_pct', '?')}%
Parabolic fit R2: {metrics.get('parabolic_R2', 'N/A')}
Parabolic rate constant k_tilde: {metrics.get('parabolic_k', 'N/A')}
Total timesteps: {metrics.get('total_timesteps', '?')}
Final time: {metrics.get('final_time', '?')} ns"""

    try:
        client   = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
        response = client.messages.create(
            model      = "claude-sonnet-4-20250514",
            max_tokens = 400,
            system     = system_prompt,
            messages   = [{"role": "user", "content": user_msg}],
        )
        narrative = response.content[0].text
        _runs[run_id]["narrative"] = narrative
        _save(run_id)
        print(f"[{run_id}] Narrative generated ({len(narrative)} chars)")
    except Exception as e:
        print(f"[{run_id}] Narrative generation failed: {e}")

def _build_context(run_id: Optional[str]) -> str:
    if not run_id or run_id not in _runs: return "No simulation selected."
    r = _runs[run_id]
    m = {k: v for k, v in r.get("metrics", {}).items() if "series" not in k}
    ctx = (f"Physics: {r.get('physics')}\nRun: {run_id}\n"
           f"Status: {r.get('status')}\n"
           f"Params: {json.dumps(r.get('params', {}), indent=2)}\n"
           f"Metrics: {json.dumps(m, indent=2)}\n")
    if r.get("narrative"):
        ctx += f"Narrative:\n{r['narrative']}\n"
    lp = r.get("log_path", "")
    if lp and Path(lp).exists():
        ctx += "Log (last 20):\n" + \
            "\n".join(Path(lp).read_text(errors="replace").splitlines()[-20:])
    return ctx

@app.on_event("startup")
async def startup():
    registry.load_all(); _load_all()

# ── Simulation thread ─────────────────────────────────────────────────────
def _run_thread(run_id: str, physics: str, params: dict, mpi: int):
    plugin    = registry.get(physics) or {}
    exec_path = _get_exec(physics)
    t_start   = datetime.now()

    make_dir_name_fn = getattr(plugin.get("_module"), "make_run_dir_name", None)
    if make_dir_name_fn:
        dir_name = make_dir_name_fn(params, run_id)
    else:
        dir_name = run_id
    run_dir = RUNS_DIR / dir_name
    run_dir.mkdir(parents=True, exist_ok=True)
    _runs[run_id]["run_dir"] = str(run_dir)

    make_meta_fn = getattr(plugin.get("_module"), "make_metadata", None)
    if make_meta_fn:
        _runs[run_id]["metadata"] = make_meta_fn(params, run_id, exec_path)

    try:
        content = registry.generate_input(physics, params)
    except NotImplementedError:
        _runs[run_id].update({"status": "failed",
            "error": f"Plugin '{physics}' not yet implemented."})
        _save(run_id); return
    except Exception as e:
        _runs[run_id].update({"status": "failed", "error": str(e)})
        _save(run_id); return

    run_name   = params.get("run_name", physics)
    input_path = run_dir / f"{run_name}.i"
    log_path   = run_dir / "run.log"
    csv_path   = run_dir / f"{run_name}.csv"

    input_path.write_text(content)
    _runs[run_id].update({
        "status":     "running",
        "log_path":   str(log_path),
        "csv_path":   str(csv_path),
        "input_path": str(input_path),
        "start_time": t_start.isoformat(),
        "run_dir":    str(run_dir),
        "dir_name":   dir_name,
    })
    _save(run_id)

    if not exec_path or not Path(exec_path).exists():
        _runs[run_id].update({"status": "input_ready",
            "message": f"Input file saved. Set MOOSE_EXEC in config.env to run."})
        _save(run_id); return

    cmd = (["mpiexec", "-n", str(mpi), exec_path, "-i", input_path.name]
           if mpi > 1 else [exec_path, "-i", input_path.name])
    print(f"[{run_id}] {' '.join(str(c) for c in cmd)}")

    try:
        proc = subprocess.Popen(cmd, cwd=str(run_dir),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1)
        _processes[run_id] = proc
        with open(log_path, "w") as lf:
            for line in proc.stdout:
                lf.write(line); lf.flush()
        proc.wait()
        success = proc.returncode == 0
    except Exception as e:
        _runs[run_id].update({"status": "failed", "error": str(e)})
        _save(run_id); return

    duration = (datetime.now() - t_start).total_seconds()
    _runs[run_id].update({
        "status":     "done" if success else "failed",
        "end_time":   datetime.now().isoformat(),
        "duration_s": round(duration, 1),
    })

    _parse_metrics(run_id)

    # Generate narrative for successful runs only
    if _runs[run_id].get("status") == "done":
        _generate_narrative(run_id)

    _processes.pop(run_id, None)

# ── Sweep ─────────────────────────────────────────────────────────────────
def _launch_sweep(physics: str, sweep_param: str, values: list,
                  base_params: dict) -> list:
    results = []
    plugin  = registry.get(physics)
    defaults = plugin.get("params", {}) if plugin else {}
    for v in values:
        run_id = make_run_id()
        params = {**defaults, **base_params, sweep_param: v,
                  "run_name": f"{physics}_{sweep_param}{v}"}
        mpi    = int(base_params.get("mpi", 1))
        _runs[run_id] = {"run_id": run_id, "status": "pending",
            "physics": physics, "params": params, "metrics": {},
            "sweep": sweep_param}
        _save(run_id)
        threading.Thread(target=_run_thread,
            args=(run_id, physics, params, mpi), daemon=True).start()
        results.append({"run_id": run_id, sweep_param: v,
                        "run_name": params["run_name"]})
        time.sleep(0.5)
    return results

# ── Routes ────────────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    plugins = registry.all_plugins()
    execs   = {}
    for pid, p in plugins.items():
        key  = p.get("executable_key", "MOOSE_EXEC")
        path = os.environ.get(key, "")
        execs[pid] = {"key": key, "path": path,
                      "found": bool(path) and Path(path).exists()}
    return {"status": "ok", "api_key_set": bool(ANTHROPIC_KEY),
            "hostname": socket.gethostname(),
            "runs_dir": str(RUNS_DIR.resolve()), "executables": execs,
            "active_runs": [k for k, v in _runs.items()
                            if v.get("status") == "running"]}

@app.get("/plugins")
async def get_plugins():
    out = {}
    for pid, p in registry.all_plugins().items():
        exec_path = _get_exec(pid)
        out[pid] = {
            "id": pid, "label": p["label"], "icon": p["icon"],
            "description": p["description"], "status": p["status"],
            "ready": p["status"] == "ready" and bool(exec_path) and Path(exec_path).exists(),
            "params": p.get("params", {}), "presets": p.get("presets", {}),
            "sweepable": p.get("sweepable", []),
            "result_keys": p.get("result_keys", []),
        }
    return out

@app.post("/generate")
async def generate_only(req: RunRequest):
    plugin = registry.get(req.physics)
    if not plugin: raise HTTPException(400, f"Unknown physics: {req.physics}")
    if plugin["status"] == "stub":
        raise HTTPException(400, f"Plugin '{req.physics}' not implemented.")
    params  = {**plugin.get("params", {}), **req.params}
    content = registry.generate_input(req.physics, params)
    return {"input_file": content, "line_count": len(content.splitlines())}

@app.post("/run")
async def start_run(req: RunRequest, background_tasks: BackgroundTasks):
    plugin = registry.get(req.physics)
    if not plugin: raise HTTPException(400, f"Unknown physics: {req.physics}")
    if plugin["status"] == "stub":
        raise HTTPException(400, f"Plugin '{req.physics}' not implemented.")
    run_id = make_run_id()
    params = {**plugin.get("params", {}), **req.params}
    _runs[run_id] = {"run_id": run_id, "status": "pending",
                     "physics": req.physics, "params": params, "metrics": {}}
    _save(run_id)
    background_tasks.add_task(_run_thread, run_id, req.physics, params,
                               int(req.mpi or params.get("mpi", 1)))
    return {"run_id": run_id, "status": "pending"}

@app.get("/runs")
async def list_runs():
    _load_all()
    return sorted(_runs.values(),
        key=lambda r: r.get("start_time") or r["run_id"], reverse=True)

@app.get("/runs/{run_id}")
async def get_run(run_id: str):
    if run_id not in _runs: _load_all()
    if run_id not in _runs: raise HTTPException(404, "Run not found")
    return _runs[run_id]

@app.get("/runs/{run_id}/log")
async def stream_log(run_id: str):
    if run_id not in _runs: _load_all()
    if run_id not in _runs: raise HTTPException(404, "Run not found")
    r        = _runs[run_id]
    log_path = Path(r.get("log_path",
        str(RUNS_DIR / r.get("dir_name", run_id) / "run.log")))
    async def gen():
        sent = 0
        while True:
            status = _runs.get(run_id, {}).get("status", "")
            if log_path.exists():
                try:
                    lines = log_path.read_text(errors="replace").splitlines()
                    for line in lines[sent:]:
                        yield f"data: {json.dumps({'line': line})}\n\n"
                    sent = len(lines)
                except: pass
            if status in ("done", "failed", "stopped", "input_ready"):
                yield f"data: {json.dumps({'done': True, 'status': status})}\n\n"
                break
            await asyncio.sleep(0.5)
    return StreamingResponse(gen(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

@app.get("/runs/{run_id}/csv")
async def get_csv(run_id: str):
    if run_id not in _runs: _load_all()
    if run_id not in _runs: raise HTTPException(404, "Run not found")
    csv_path = _runs[run_id].get("csv_path", "")
    if not csv_path or not Path(csv_path).exists():
        raise HTTPException(404, "CSV not ready")
    return _parse_csv(csv_path)

@app.post("/stop/{run_id}")
async def stop_run(run_id: str):
    proc = _processes.get(run_id)
    if proc:
        proc.terminate(); _processes.pop(run_id, None)
        _runs[run_id]["status"] = "stopped"; _save(run_id)
        return {"status": "stopped"}
    raise HTTPException(400, "No active process")

@app.post("/chat")
async def chat(req: ChatRequest):
    if not ANTHROPIC_KEY: raise HTTPException(400, "ANTHROPIC_API_KEY not set")
    plugin = registry.get(req.physics)

    # sweep detection
    if plugin and plugin.get("sweepable"):
        for param in plugin["sweepable"]:
            m = re.search(
                rf"{param}\s*[:\-=]?\s*([\d\s,\.and]+)",
                req.message, re.IGNORECASE)
            if m:
                values = [float(x) for x in re.findall(r"[\d\.]+", m.group(1))]
                values = [v for v in values if v > 0]
                if len(values) > 1:
                    base = plugin.get("params", {})
                    runs = _launch_sweep(req.physics, param, values, base)
                    summary = "\n".join(
                        [f"  • `{r['run_name']}` → `{r['run_id']}`" for r in runs])
                    async def sweep_gen():
                        msg = (f"Launching **{len(runs)} runs** sweeping `{param}`:\n\n"
                               f"{summary}\n\nWatch progress in the sidebar.")
                        for word in msg.split(" "):
                            yield f"data: {json.dumps({'text': word + ' '})}\n\n"
                            await asyncio.sleep(0.01)
                        for r in runs:
                            yield f"data: {json.dumps({'run_triggered': True, 'run_id': r['run_id']})}\n\n"
                        yield f"data: {json.dumps({'done': True})}\n\n"
                    return StreamingResponse(sweep_gen(), media_type="text/event-stream")

    system   = registry.get_system_prompt(req.physics)
    context  = _build_context(req.run_id)
    messages = [m2 for m2 in req.history[-10:]
                if m2.get("role") in ("user", "assistant") and m2.get("content")]
    messages.append({"role": "user",
        "content": f"[Context]\n{context}\n\n[Message]\n{req.message}"})

    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)

    async def generate():
        with client.messages.stream(model="claude-sonnet-4-20250514",
                max_tokens=1500, system=system, messages=messages) as stream:
            for chunk in stream.text_stream:
                yield f"data: {json.dumps({'text': chunk})}\n\n"
        yield f"data: {json.dumps({'done': True})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")
