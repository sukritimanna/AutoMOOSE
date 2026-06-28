<p align="center">
  <img src="docs/_static/AutoMOOSE.png" alt="AutoMOOSE Logo" width="220"/>
</p>

<h1 align="center">AutoMOOSE</h1>

<p align="center">
  <b>An LLM-driven agentic framework for automated MOOSE phase-field simulations</b>
</p>

<p align="center">
  <a href="https://automoose.readthedocs.io/en/latest/?badge=latest">
    <img src="https://readthedocs.org/projects/automoose/badge/?version=latest" alt="Documentation Status"/>
  </a>
  <img src="https://img.shields.io/badge/python-3.10%2B-blue" alt="Python 3.10+"/>
  <img src="https://img.shields.io/badge/MOOSE-phase--field-orange" alt="MOOSE"/>
  <img src="https://img.shields.io/badge/license-MIT-green" alt="License MIT"/>
</p>

---

## Overview

**AutoMOOSE** is an agentic AI framework that automates the full lifecycle of [MOOSE](https://mooseframework.inl.gov/) phase-field simulations — from a natural-language problem specification through mesh and input-file construction, job execution, screening, **physics-grounded falsification**, closed-loop recovery, and visualization.

The framework is a **six-agent pipeline**, formally `S = f₆ ∘ f₅ ∘ f₄ ∘ f₃ ∘ f₂ ∘ f₁(U)`:

| Agent | Symbol | Role |
|-------|--------|------|
| Architect | f₁ | Decomposes user intent into a structured simulation plan |
| Input Writer | f₂ | Generates the MOOSE `.i` input file via six sub-agents |
| Runner | f₃ | Executes the simulation and monitors it to a terminal state |
| Reviewer | f₄ | **Screens** the run — *did it complete and look valid?* (does **not** repair) |
| Visualization | f₅ | Extracts observables and writes a natural-language interpretation |
| Skeptic | f₆ | **Adversarially falsifies** the result against physics invariants (does **not** repair) |

Detection is deliberately separated from correction: the Skeptic falsifies but never repairs, and a distinct closed-loop module (`recovery.py`) acts on its verdict — classifying the failure and applying a bounded correction (e.g. a time-step cutback `Δt ← α·Δt`) before re-running. A corrected run is accepted only if it re-completes **and** the Skeptic re-admits it.

A **plugin registry** decouples physics from the agents via a small `PLUGIN` dict + `generate_input(**params) -> str` contract (see below). The backend exposes a **Model Context Protocol (MCP)** server (Starlette/uvicorn, port 8001, stdio + SSE) with ten tools, backed by a FastAPI REST API (port 8000) and a Vite/React frontend.

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
f₅ Visualization ──► parse_results(csv_data)
    │
    ▼
f₆ Skeptic ──► physics-grounded falsification (verdict)
    │
    ▼  (on a falsified, recoverable failure)
recovery.py ──► classify failure → bounded correction → re-run pipeline
```

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
python automoose/mcp_server.py                       # stdio
python automoose/mcp_server.py --transport sse --port 8001   # SSE
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
|--------|----------------|--------|----------------|
| `grain_growth` | Allen–Cahn grain growth | **ready** | `num_grains`, `T`, `GBenergy`, `GBmob0`, `op_num` |
| `spinodal` | Cahn–Hilliard phase separation | **ready** | `c0`, `kappa`, `M`, `W`, `noise`, `end_time` |
| `solidification` | dendritic solidification | stub | — |
| `ferro` | ferroelectric (Landau–Devonshire) | stub | — |

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
