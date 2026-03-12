# AutoMOOSE MCP Server

Exposes AutoMOOSE as a **Model Context Protocol (MCP) tool server**, allowing
Claude Desktop, Claude Code, and any MCP-compatible client to drive MOOSE
phase-field simulations directly from a chat interface — no browser required.

## Architecture

```
Claude Desktop / Claude Code
        │  MCP (stdio or SSE)
        ▼
  mcp_server.py          ← this file
        │  HTTP REST
        ▼
  server.py (FastAPI)    ← existing AutoMOOSE backend
        │
        ▼
  MOOSE Executable       ← phase_field-opt / ferro-opt
```

## Quick Start

### 1. Install dependencies
```bash
pip install mcp httpx
```

### 2. Start the AutoMOOSE backend
```bash
cd AutoMOOSE/backend
uvicorn server:app --reload --port 8000
```

### 3a. Claude Desktop (stdio mode)
Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "automoose": {
      "command": "python",
      "args": ["/path/to/AutoMOOSE/backend/mcp_server.py"],
      "env": {
        "AUTOMOOSE_URL": "http://localhost:8000"
      }
    }
  }
}
```
Restart Claude Desktop. AutoMOOSE tools will appear automatically.

### 3b. SSE mode (Claude Code / remote)
```bash
python mcp_server.py --transport sse --port 8001
```
Then connect any MCP client to `http://localhost:8001/sse`.

---

## Available Tools

| Tool | Description |
|------|-------------|
| `health_check` | Verify backend is up and MOOSE executables are found |
| `list_plugins` | List all physics plugins with params and sweep fields |
| `generate_input` | Preview a MOOSE `.i` file without running |
| `run_simulation` | Launch a single simulation, returns `run_id` |
| `run_sweep` | Launch parallel sweep over a parameter list |
| `get_run_status` | Poll status: pending / running / done / failed |
| `get_results` | Retrieve metrics (N(t), R², dN/dt, etc.) |
| `list_runs` | Browse run history with optional filters |
| `get_log_tail` | Read last N lines of MOOSE stdout log |
| `stop_run` | Terminate an active simulation |

---

## Example Chat Session (Claude Desktop)

> **User:** Run a grain growth simulation at T=450K with 20 grains on a 2D mesh.
>
> **Claude:** *(calls `run_simulation` with physics="grain_growth", params={T:450, num_grains:20, dim:2})*
> Launched run `run_20260303_143022`. I'll check on it in a moment...
> *(calls `get_run_status`)* Still running — 45s elapsed.
> *(calls `get_results` after completion)* Done in 142s! Grain count dropped 18%,
> parabolic fit R²=0.997, rate constant k=1.24×10⁻⁴ μm²/s.

> **User:** Now sweep T from 300 to 800 K in steps of 100.
>
> **Claude:** *(calls `run_sweep` with values=[300,400,500,600,700,800])*
> Launched 6 parallel runs. I'll aggregate the results once they finish...

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `AUTOMOOSE_URL` | `http://localhost:8000` | AutoMOOSE FastAPI backend URL |
| `ANTHROPIC_API_KEY` | — | Only needed if backend Chat is used |
