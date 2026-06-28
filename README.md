<p align="center">
  <img src="docs/_static/AutoMOOSE.png" alt="AutoMOOSE Logo" width="220"/>
</p>

<h1 align="center">AutoMOOSE</h1>

<p align="center">
  <b>An LLM-driven agentic framework for automated MOOSE phase-field simulations</b>
</p>

<p align="center">
  From a natural-language prompt to an executed, screened, and physics-checked simulation —
  <br/>with detection deliberately separated from correction.
</p>

<p align="center">
  <a href="https://github.com/sukritimanna/AutoMOOSE/actions/workflows/ci.yml">
    <img src="https://github.com/sukritimanna/AutoMOOSE/actions/workflows/ci.yml/badge.svg" alt="CI"/>
  </a>
  <a href="https://automoose.readthedocs.io/en/latest/?badge=latest">
    <img src="https://readthedocs.org/projects/automoose/badge/?version=latest" alt="Documentation Status"/>
  </a>
  <img src="https://img.shields.io/badge/python-3.10%2B-blue?style=flat-square" alt="Python 3.10+"/>
  <img src="https://img.shields.io/badge/MOOSE-phase--field-orange?style=flat-square" alt="MOOSE"/>
  <img src="https://img.shields.io/badge/license-MIT-green?style=flat-square" alt="License MIT"/>
</p>

<p align="center">
  <a href="#overview">Overview</a> &nbsp;•&nbsp;
  <a href="#architecture">Architecture</a> &nbsp;•&nbsp;
  <a href="#quick-start">Quick Start</a> &nbsp;•&nbsp;
  <a href="#plugin-development">Plugins</a> &nbsp;•&nbsp;
  <a href="#mcp-interface">MCP</a> &nbsp;•&nbsp;
  <a href="#testing">Testing</a> &nbsp;•&nbsp;
  <a href="#citation">Citation</a>
</p>

---

## Overview

**AutoMOOSE** is an agentic AI framework that automates the full lifecycle of [MOOSE](https://mooseframework.inl.gov/) phase-field simulations — from a natural-language problem specification through mesh and input-file construction, job execution, screening, **physics-grounded falsification**, closed-loop recovery, and visualization.

#### Highlights

- 🧠 &nbsp;**Natural language in, simulation out** — describe the physics; AutoMOOSE writes the MOOSE `.i` file, runs it, and reports back. No manual input authoring.
- 🔬 &nbsp;**Six-agent pipeline** with cleanly separated responsibilities — planning, input generation, execution, screening, falsification, and interpretation.
- 🛡️ &nbsp;**Detection separated from correction** — the Skeptic falsifies against physics invariants; a distinct recovery module acts on its verdict.
- ♻️ &nbsp;**Bounded closed-loop recovery** — numerical-only corrections, capped at `MAX_ATTEMPTS = 3`, with a `{from, to, why}` record for every edit and physical parameters left untouched.
- 🔌 &nbsp;**Plugin registry** — add a new physics domain without changing the agents, backend, MCP server, or UI.
- 🔗 &nbsp;**Programmatic interfaces** — a Model Context Protocol (MCP) server with ten tools, a FastAPI REST API, and a React frontend.
- 🧩 &nbsp;**Model-agnostic** — Claude, Qwen, or a self-hosted open-weights model behind an OpenAI-compatible endpoint; a config change, not a code change.

#### The six-agent pipeline

Formally, `S = f₅ ∘ f₆ ∘ f₄ ∘ f₃ ∘ f₂ ∘ f₁(U)` — read right-to-left, the run-time order is `f₁ → f₂ → f₃ → f₄ → f₆ → f₅`.

| Agent | Symbol | Role |
|-------|:------:|------|
| Architect | `f₁` | Decomposes user intent into a structured simulation plan |
| Input Writer | `f₂` | Generates the MOOSE `.i` input file via six sub-agents |
| Runner | `f₃` | Executes the simulation and monitors it to a terminal state |
| Reviewer | `f₄` | **Screens** the run — *did it complete and look valid?* |
| Skeptic | `f₆` | **Adversarially falsifies** the result against physics invariants |
| Visualization | `f₅` | Extracts observables and writes a natural-language interpretation |

Detection is deliberately separated from correction: the Skeptic falsifies, and a distinct closed-loop module (`recovery.py`) acts on its verdict — classifying the failure and applying a bounded correction before re-running. Recovery is bounded in three ways: a hard cap of `MAX_ATTEMPTS = 3` per task; corrections that touch only numerical and discretization controls (the time step, floored at `MIN_DT0`; the mesh refinement; the integration window) and never the physical parameters; and a `{from, to, why}` change record for every edit. A corrected run is accepted only if it re-completes **and** the Skeptic re-admits it.

The scientific validation of the framework (a pre-registered grain-growth benchmark, an ensemble Arrhenius analysis, and a second conserved-dynamics domain) is reported in the companion article (see [Citation](#citation)).

---

## Architecture

```
User Query
    │
    ▼
f₁ Architect ──► Plugin Registry
    │                   │
    ▼                   ▼
f₂ Input Writer  ◄── generate_input(**params)
  ├── Meshing
  ├── Variables
  ├── Kernels
  ├── Materials
  ├── Postprocessors
  └── Executioner
    │
    ▼
f₃ Runner ──► Execution Backend (local | HPC/SLURM) ──► MOOSE Executable
    │
    ▼
f₄ Reviewer        screen: did it run and look valid?
    │
    ▼
f₆ Skeptic ──► physics-grounded falsification (verdict)
    │
    ▼  (on a falsified, recoverable failure)
recovery.py ──► classify failure → bounded correction → re-run pipeline
    │
    ▼
f₅ Visualization ──► parse_results(csv_data) → figures + interpretation
```

#### Interfaces

| Surface | Tech | Port | Notes |
|---------|------|:----:|-------|
| REST API | FastAPI | `8000` | Agent sequencing, SSE log streaming, run records |
| MCP server | Starlette/uvicorn | `8001` | Ten tools, stdio + SSE transports |
| Frontend | Vite / React | `5173` | Chat, configuration, live logs, results (optional) |

---

## Quick Start

### Prerequisites

- Python 3.10+
- MOOSE framework compiled (set `MOOSE_EXEC` in `config.env`)
- Node.js 18+ (for the optional frontend)

### Installation

```bash
git clone https://github.com/sukritimanna/AutoMOOSE.git
cd AutoMOOSE

# Backend
pip install -r requirements.txt
cp config.env.example config.env   # set MOOSE_EXEC and the LLM backend

# Frontend (optional)
cd frontend && npm install && cd ..
```

### Running

```bash
# Start the FastAPI backend (port 8000) and the frontend
bash start.sh

# MCP server — stdio (Claude Desktop) or SSE (remote / Claude Code)
python automoose/mcp_server.py                              # stdio
python automoose/mcp_server.py --transport sse --port 8001  # SSE
```

The pipeline is **model-agnostic**: the provider, model, and endpoint are read from `config.env`, so the same agents run on Claude, Qwen, or a self-hosted open-weights model behind an OpenAI-compatible endpoint — a configuration change, not a code change.

---

## Plugin Development

A physics plugin is a directory under `automoose/plugins/<name>/` containing a `plugin.py` that exposes a `PLUGIN` metadata dict and a module-level `generate_input(**params)`. The registry (`plugin_registry.py`) auto-discovers it at start-up — no change to the agents, backend, MCP server, or UI:

```python
# automoose/plugins/myphysics/plugin.py

PLUGIN = {
    "label":          "My Physics",
    "status":         "ready",          # "ready" | "stub"
    "params":         {...},            # name -> {default, range, ...}
    "sweepable":      ["T", "..."],     # parameters a sweep may vary
    "executable_key": "MOOSE_EXEC",     # env var holding the solver path
}

def generate_input(**params) -> str:
    """Return a complete MOOSE .i input file as a string."""
    ...

def parse_results(csv_data) -> dict:    # optional
    """Map MOOSE postprocessor CSV output to a metrics dict."""
    ...
```

### Registered plugins

| Plugin | Physics domain | Status | Key parameters |
|--------|----------------|:------:|----------------|
| `grain_growth` | Allen–Cahn grain growth | **ready** | `num_grains`, `T`, `GBenergy`, `GBmob0`, `op_num` |
| `spinodal` | Cahn–Hilliard phase separation | **ready** | `c0`, `kappa`, `M`, `W`, `noise`, `end_time` |
| `solidification` | dendritic solidification | stub | — |
| `ferro` | ferroelectric (Landau–Devonshire) | stub | — |

A `stub` plugin is an extension template: its `generate_input` raises `NotImplementedError`, and the backend rejects any generate/run request for it with an HTTP 400 before the pipeline starts.

---

## MCP Interface

The backend exposes a **Model Context Protocol** server (`automoose/mcp_server.py`) with ten tools, so an external optimizer or active-learning loop can drive AutoMOOSE programmatically:

```
health_check · list_plugins · generate_input · run_simulation · run_sweep
get_run_status · get_results · list_runs · get_log_tail · stop_run
```

Falsification and recovery are not separate tools — they run inside the backend pipeline that `run_simulation` and `run_sweep` invoke. A sweep launches one independent pipeline run per parameter value, each with its own run record and fresh model context.

---

## Testing

The test suite runs fully offline — no MOOSE binary and no language-model API key — using deterministic inputs:

```bash
pip install pytest mcp httpx
pytest -q tests/
```

It covers plugin discovery and the `PLUGIN` schema, stub enforcement, recovery policy bounds, the Skeptic's invariant math on toy trajectories, the MCP tool contract, and run-record serialization. Continuous integration runs the same suite on Python 3.10–3.12 via [`.github/workflows/ci.yml`](.github/workflows/ci.yml).

---

## Documentation

Full documentation is available at **[automoose.readthedocs.io](https://automoose.readthedocs.io)**.

---

## Citation

If you use AutoMOOSE in your research, please cite:

```bibtex
@article{manna2026automoose,
  title   = {AutoMOOSE: an agentic AI for autonomous phase-field simulation},
  author  = {Manna, Sukriti and Chan, Henry and Sankaranarayanan, Subramanian},
  year    = {2026},
  eprint  = {2603.20986},
  note    = {Preprint: arXiv:2603.20986}
}
```

---

## License

MIT © 2026 AutoMOOSE Contributors

<p align="center">
  <sub>Built at the Center for Nanoscale Materials, Argonne National Laboratory, and the University of Illinois Chicago.</sub>
</p>
