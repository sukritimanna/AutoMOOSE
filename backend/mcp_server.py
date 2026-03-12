"""
AutoMOOSE — MCP Server
======================
Exposes AutoMOOSE simulation capabilities as MCP tools so any MCP client
(Claude Desktop, Claude Code, etc.) can drive MOOSE simulations directly.

Usage:
  python mcp_server.py                    # stdio mode (Claude Desktop)
  python mcp_server.py --transport sse    # SSE mode on port 8001

Requires:
  pip install mcp httpx

The AutoMOOSE FastAPI backend must be running at AUTOMOOSE_URL (default http://localhost:8000).
"""

import os
import sys
import json
import asyncio
import argparse
from typing import Any

import httpx
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.server.sse import SseServerTransport
from mcp.types import (
    Tool, TextContent, CallToolResult, ListToolsResult,
)

# ── Config ─────────────────────────────────────────────────────────────────
AUTOMOOSE_URL = os.environ.get("AUTOMOOSE_URL", "http://localhost:8000")
SERVER_NAME   = "automoose"
SERVER_VERSION = "1.0.0"

# ── Server instance ─────────────────────────────────────────────────────────
server = Server(SERVER_NAME)


# ── Tool definitions ────────────────────────────────────────────────────────
TOOLS = [
    Tool(
        name="list_plugins",
        description=(
            "List all available AutoMOOSE physics plugins with their status, "
            "parameters, and sweepable fields. Use this first to discover "
            "what simulations are available."
        ),
        inputSchema={
            "type": "object",
            "properties": {},
            "required": [],
        },
    ),
    Tool(
        name="generate_input",
        description=(
            "Generate a MOOSE .i input file for a given physics plugin and "
            "parameter set WITHOUT running it. Returns the full file content. "
            "Useful for previewing or debugging before execution."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "physics": {
                    "type": "string",
                    "description": "Plugin ID, e.g. 'grain_growth', 'ferro'",
                },
                "params": {
                    "type": "object",
                    "description": (
                        "Simulation parameters. For grain_growth: T (temperature K), "
                        "num_grains, nx, ny, xmax, ymax, end_time, GBenergy, GBmob0, "
                        "op_num, adaptivity, periodic_bc, dim (2 or 3)."
                    ),
                    "default": {},
                },
            },
            "required": ["physics"],
        },
    ),
    Tool(
        name="run_simulation",
        description=(
            "Launch a MOOSE simulation and return a run_id. The simulation "
            "executes asynchronously in the background. Use get_run_status "
            "to poll progress and get_results when done."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "physics": {
                    "type": "string",
                    "description": "Plugin ID, e.g. 'grain_growth'",
                },
                "params": {
                    "type": "object",
                    "description": "Simulation parameters (see generate_input).",
                    "default": {},
                },
                "mpi": {
                    "type": "integer",
                    "description": "Number of MPI ranks (default 1).",
                    "default": 1,
                },
            },
            "required": ["physics"],
        },
    ),
    Tool(
        name="run_sweep",
        description=(
            "Launch a parameter sweep — multiple simulations varying one parameter "
            "across a list of values. Returns a list of run_ids. All runs execute "
            "in parallel threads."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "physics": {
                    "type": "string",
                    "description": "Plugin ID",
                },
                "sweep_param": {
                    "type": "string",
                    "description": "The parameter to sweep, e.g. 'T' or 'num_grains'",
                },
                "values": {
                    "type": "array",
                    "items": {"type": "number"},
                    "description": "List of values to sweep over, e.g. [300, 450, 600, 800]",
                },
                "base_params": {
                    "type": "object",
                    "description": "Other fixed parameters to apply to all runs.",
                    "default": {},
                },
                "mpi": {
                    "type": "integer",
                    "description": "MPI ranks per run (default 1).",
                    "default": 1,
                },
            },
            "required": ["physics", "sweep_param", "values"],
        },
    ),
    Tool(
        name="get_run_status",
        description=(
            "Get the current status and metadata of a simulation run. "
            "Status values: pending | running | done | failed | stopped | input_ready."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "run_id": {
                    "type": "string",
                    "description": "Run ID returned by run_simulation or run_sweep",
                },
            },
            "required": ["run_id"],
        },
    ),
    Tool(
        name="get_results",
        description=(
            "Get quantitative results and metrics for a completed simulation. "
            "For grain_growth returns: grain_count series, parabolic_fit (R², k, d0), "
            "grain_reduction_pct, dN_dt series, DOF evolution. "
            "Returns an error if the run is not yet done."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "run_id": {
                    "type": "string",
                    "description": "Run ID of a completed simulation",
                },
            },
            "required": ["run_id"],
        },
    ),
    Tool(
        name="list_runs",
        description=(
            "List all simulation runs (past and current) with their status, "
            "physics type, parameters, and key metrics. Sorted newest-first."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "physics_filter": {
                    "type": "string",
                    "description": "Optional: filter by physics type, e.g. 'grain_growth'",
                },
                "status_filter": {
                    "type": "string",
                    "description": "Optional: filter by status, e.g. 'done' or 'running'",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max number of runs to return (default 20)",
                    "default": 20,
                },
            },
            "required": [],
        },
    ),
    Tool(
        name="get_log_tail",
        description=(
            "Get the last N lines of a simulation's MOOSE stdout log. "
            "Useful for debugging failures or checking solver convergence."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "run_id": {
                    "type": "string",
                    "description": "Run ID",
                },
                "lines": {
                    "type": "integer",
                    "description": "Number of tail lines to return (default 30)",
                    "default": 30,
                },
            },
            "required": ["run_id"],
        },
    ),
    Tool(
        name="stop_run",
        description="Stop (terminate) an actively running simulation.",
        inputSchema={
            "type": "object",
            "properties": {
                "run_id": {
                    "type": "string",
                    "description": "Run ID of the running simulation to stop",
                },
            },
            "required": ["run_id"],
        },
    ),
    Tool(
        name="health_check",
        description=(
            "Check if the AutoMOOSE backend is reachable and which MOOSE "
            "executables are configured and found on disk."
        ),
        inputSchema={
            "type": "object",
            "properties": {},
            "required": [],
        },
    ),
]


# ── HTTP helpers ─────────────────────────────────────────────────────────────
async def _get(path: str) -> dict:
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(f"{AUTOMOOSE_URL}{path}")
        r.raise_for_status()
        return r.json()

async def _post(path: str, body: dict) -> dict:
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(f"{AUTOMOOSE_URL}{path}", json=body)
        r.raise_for_status()
        return r.json()

def _text(data: Any) -> CallToolResult:
    return CallToolResult(
        content=[TextContent(type="text", text=json.dumps(data, indent=2, default=str))],
        isError=False,
    )

def _error(msg: str) -> CallToolResult:
    return CallToolResult(
        content=[TextContent(type="text", text=f"Error: {msg}")],
        isError=True,
    )


# ── Tool handlers ─────────────────────────────────────────────────────────────
@server.list_tools()
async def handle_list_tools() -> ListToolsResult:
    return ListToolsResult(tools=TOOLS)


@server.call_tool()
async def handle_call_tool(name: str, arguments: dict) -> CallToolResult:
    try:
        # ── list_plugins ──────────────────────────────────────────────────
        if name == "list_plugins":
            data = await _get("/plugins")
            # Slim down for readability
            summary = {}
            for pid, p in data.items():
                summary[pid] = {
                    "label":      p["label"],
                    "status":     p["status"],
                    "ready":      p["ready"],
                    "sweepable":  p.get("sweepable", []),
                    "params":     p.get("params", {}),
                    "presets":    list(p.get("presets", {}).keys()),
                }
            return _text(summary)

        # ── generate_input ────────────────────────────────────────────────
        elif name == "generate_input":
            physics = arguments["physics"]
            params  = arguments.get("params", {})
            data    = await _post("/generate", {"physics": physics, "params": params, "mpi": 1})
            return _text({
                "physics":    physics,
                "line_count": data["line_count"],
                "input_file": data["input_file"],
            })

        # ── run_simulation ────────────────────────────────────────────────
        elif name == "run_simulation":
            physics = arguments["physics"]
            params  = arguments.get("params", {})
            mpi     = arguments.get("mpi", 1)
            data    = await _post("/run", {"physics": physics, "params": params, "mpi": mpi})
            return _text({
                "run_id":  data["run_id"],
                "status":  data["status"],
                "message": (
                    f"Simulation launched. Poll with get_run_status('{data['run_id']}') "
                    f"and retrieve metrics with get_results('{data['run_id']}') when done."
                ),
            })

        # ── run_sweep ─────────────────────────────────────────────────────
        elif name == "run_sweep":
            physics     = arguments["physics"]
            sweep_param = arguments["sweep_param"]
            values      = arguments["values"]
            base_params = arguments.get("base_params", {})
            mpi         = arguments.get("mpi", 1)

            run_ids = []
            for v in values:
                params = {**base_params, sweep_param: v,
                          "run_name": f"{physics}_{sweep_param}{v}", "mpi": mpi}
                data   = await _post("/run", {"physics": physics, "params": params, "mpi": mpi})
                run_ids.append({"run_id": data["run_id"], sweep_param: v})
                await asyncio.sleep(0.3)

            return _text({
                "sweep_param": sweep_param,
                "n_runs":      len(run_ids),
                "runs":        run_ids,
                "message":     (
                    f"Launched {len(run_ids)} runs sweeping '{sweep_param}' = {values}. "
                    "Use get_run_status(run_id) to track each run."
                ),
            })

        # ── get_run_status ────────────────────────────────────────────────
        elif name == "get_run_status":
            run_id = arguments["run_id"]
            data   = await _get(f"/runs/{run_id}")
            # Return a clean summary
            return _text({
                "run_id":     data["run_id"],
                "status":     data.get("status"),
                "physics":    data.get("physics"),
                "params":     data.get("params", {}),
                "start_time": data.get("start_time"),
                "duration_s": data.get("duration_s"),
                "run_dir":    data.get("run_dir"),
                "error":      data.get("error"),
                "message":    data.get("message"),
            })

        # ── get_results ───────────────────────────────────────────────────
        elif name == "get_results":
            run_id = arguments["run_id"]
            data   = await _get(f"/runs/{run_id}")
            status = data.get("status")
            if status not in ("done", "input_ready"):
                return _error(
                    f"Run '{run_id}' is '{status}' — results only available when done. "
                    "Use get_run_status to check progress."
                )
            metrics = data.get("metrics", {})
            # Summarize series to avoid huge payloads
            summary = {}
            for k, v in metrics.items():
                if isinstance(v, list) and len(v) > 10:
                    summary[k] = {
                        "n_points": len(v),
                        "first":    v[:3],
                        "last":     v[-3:],
                        "min":      min(v),
                        "max":      max(v),
                    }
                else:
                    summary[k] = v
            return _text({
                "run_id":     run_id,
                "physics":    data.get("physics"),
                "status":     status,
                "duration_s": data.get("duration_s"),
                "params":     data.get("params", {}),
                "metrics":    summary,
            })

        # ── list_runs ─────────────────────────────────────────────────────
        elif name == "list_runs":
            physics_filter = arguments.get("physics_filter")
            status_filter  = arguments.get("status_filter")
            limit          = arguments.get("limit", 20)

            all_runs = await _get("/runs")

            # Apply filters
            filtered = []
            for r in all_runs:
                if physics_filter and r.get("physics") != physics_filter:
                    continue
                if status_filter and r.get("status") != status_filter:
                    continue
                m = r.get("metrics", {})
                filtered.append({
                    "run_id":            r["run_id"],
                    "status":            r.get("status"),
                    "physics":           r.get("physics"),
                    "params":            r.get("params", {}),
                    "start_time":        r.get("start_time"),
                    "duration_s":        r.get("duration_s"),
                    "grain_reduction":   m.get("grain_reduction_pct"),
                    "parabolic_R2":      m.get("parabolic_fit", {}).get("R2"),
                })

            return _text({
                "total_shown": min(len(filtered), limit),
                "total_found": len(filtered),
                "runs":        filtered[:limit],
            })

        # ── get_log_tail ──────────────────────────────────────────────────
        elif name == "get_log_tail":
            run_id = arguments["run_id"]
            n      = arguments.get("lines", 30)
            data   = await _get(f"/runs/{run_id}")
            log_path = data.get("log_path", "")

            if not log_path:
                return _error(f"No log path found for run '{run_id}'")
            try:
                from pathlib import Path
                lines = Path(log_path).read_text(errors="replace").splitlines()
                tail  = lines[-n:]
                return _text({
                    "run_id":      run_id,
                    "status":      data.get("status"),
                    "total_lines": len(lines),
                    "showing":     len(tail),
                    "log":         "\n".join(tail),
                })
            except FileNotFoundError:
                return _error(f"Log file not yet created for run '{run_id}'")

        # ── stop_run ──────────────────────────────────────────────────────
        elif name == "stop_run":
            run_id = arguments["run_id"]
            data   = await _post(f"/stop/{run_id}", {})
            return _text({"run_id": run_id, "status": data.get("status")})

        # ── health_check ──────────────────────────────────────────────────
        elif name == "health_check":
            data = await _get("/health")
            return _text({
                "backend_url":  AUTOMOOSE_URL,
                "status":       data.get("status"),
                "api_key_set":  data.get("api_key_set"),
                "hostname":     data.get("hostname"),
                "runs_dir":     data.get("runs_dir"),
                "executables":  data.get("executables", {}),
                "active_runs":  data.get("active_runs", []),
            })

        else:
            return _error(f"Unknown tool: {name}")

    except httpx.ConnectError:
        return _error(
            f"Cannot connect to AutoMOOSE backend at {AUTOMOOSE_URL}. "
            "Make sure the backend is running: cd backend && uvicorn server:app"
        )
    except httpx.HTTPStatusError as e:
        return _error(f"Backend returned {e.response.status_code}: {e.response.text}")
    except Exception as e:
        return _error(f"Unexpected error: {type(e).__name__}: {e}")


# ── Entry point ───────────────────────────────────────────────────────────────
async def main_stdio():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream,
                         server.create_initialization_options())

async def main_sse(port: int):
    from starlette.applications import Starlette
    from starlette.routing import Route, Mount
    import uvicorn

    sse = SseServerTransport("/messages")

    async def handle_sse(request):
        async with sse.connect_sse(request.scope, request.receive, request._send) as (r, w):
            await server.run(r, w, server.create_initialization_options())

    starlette_app = Starlette(routes=[
        Route("/sse", endpoint=handle_sse),
        Mount("/messages", app=sse.handle_post_message),
    ])

    print(f"AutoMOOSE MCP server listening on http://0.0.0.0:{port}/sse")
    config = uvicorn.Config(starlette_app, host="0.0.0.0", port=port, log_level="info")
    await uvicorn.Server(config).serve()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AutoMOOSE MCP Server")
    parser.add_argument("--transport", choices=["stdio", "sse"], default="stdio")
    parser.add_argument("--port", type=int, default=8001)
    parser.add_argument("--backend", default=AUTOMOOSE_URL,
                        help="AutoMOOSE FastAPI backend URL")
    args = parser.parse_args()

    AUTOMOOSE_URL = args.backend

    if args.transport == "sse":
        asyncio.run(main_sse(args.port))
    else:
        asyncio.run(main_stdio())
