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

**AutoMOOSE** is an agentic AI framework that automates the full lifecycle of [MOOSE](https://mooseframework.inl.gov/) phase-field simulations — from natural-language problem specification through mesh generation, input file construction, job execution, result review, and visualization.

The framework is composed of five specialized agents:

| Agent | Symbol | Role |
|-------|--------|------|
| Architect | f₁ | Decomposes user intent into simulation parameters |
| Input Writer | f₂ | Generates MOOSE `.i` input files via six sub-agents |
| Runner | f₃ | Executes simulations and monitors convergence |
| Reviewer | f₄ | Validates output and detects errors |
| Visualization | f₅ | Renders phase-field evolution figures |

A **plugin registry** enables extensible physics support via a standardized `generate_input(**params) → str` / `parse_results(csv_data) → dict` interface. Currently registered plugins: **GrainGrowth**, with Solidification, Spinodal, and Precipitate stubs in development.

The backend exposes a **MCP server** (Starlette/uvicorn, port 8001) with ten tools over stdio and SSE transports, backed by a FastAPI REST API (port 8000) and a Vite/React frontend (port 5174).

---

## Architecture

```
User Query
    │
    ▼
f₁ Architect ──► Plugin Registry
    │                   │
    ▼                   ▼
f₂ Input Writer  ◄── generate_input()
  ├── Meshing
  ├── Variables
  ├── Kernels
  ├── Materials
  ├── Postprocessors
  └── Executioner
    │
    ▼
f₃ Runner ──► MOOSE Executable
    │
    ▼
f₄ Reviewer ──► parse_results()
    │
    ▼
f₅ Visualization
```

---

## Quick Start

### Prerequisites

- Python 3.10+
- MOOSE framework compiled (set `MOOSE_EXEC` in `config.env`)
- Node.js 18+ (for frontend)

### Installation

```bash
git clone https://github.com/<your-org>/AutoMOOSE.git
cd AutoMOOSE

# Backend
pip install -r requirements.txt
cp config.env.example config.env  # set MOOSE_EXEC path

# Frontend
cd frontend && npm install && cd ..
```

### Running

```bash
# Start backend (MCP + FastAPI)
cd backend
export $(grep -v '^#' ../config.env | xargs)
uvicorn server:app --port 8000

# Start MCP server
uvicorn mcp_server:app --port 8001

# Start frontend
cd frontend && npm run dev
```

Open [http://localhost:5174](http://localhost:5174) in your browser.

---

## Plugin Development

Implement the plugin interface to add new physics:

```python
from automoose.plugins import PhysicsPlugin, register_plugin

class MyPlugin(PhysicsPlugin):
    name = "MyPhysics"

    def generate_input(self, **params) -> str:
        # Return a valid MOOSE .i input file as a string
        ...

    def parse_results(self, csv_data: str) -> dict:
        # Parse MOOSE CSV output, return structured dict
        ...

register_plugin(MyPlugin)
```

---

## Documentation

Full documentation is available at **[automoose.readthedocs.io](https://automoose.readthedocs.io)**.

---

## Citation

If you use AutoMOOSE in your research, please cite:

```bibtex
@article{automoose2026,
  title   = {AutoMOOSE: An LLM-Driven Agentic Framework for Automated Phase-Field Simulations},
  author  = {[Authors]},
  journal = {NA},
  year    = {2026}
}
```

---

## License

MIT © 2026 AutoMOOSE Contributors
