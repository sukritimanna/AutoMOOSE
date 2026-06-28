Architecture
============

AutoMOOSE implements a **six-agent pipeline** with a plugin registry, a
model-agnostic LLM backend, a pluggable execution backend (local or HPC), and
an MCP interface layer.

Agent Pipeline
--------------

.. code-block:: text

   User Query
       │
       ▼
   f₁  Architect ──────────► Plugin Registry
       │                           │
       ▼                           ▼
   f₂  Input Writer  ◄────── generate_input(**params)
     ├── Meshing sub-agent
     ├── Variables sub-agent
     ├── Kernels sub-agent
     ├── Materials sub-agent
     ├── Postprocessors sub-agent
     └── Executioner sub-agent
       │
       ▼
   f₃  Runner ──────────────► Execution Backend (local | HPC)
       │                           │
       │                           ▼
       │                       MOOSE Executable
       ▼
   f₄  Reviewer ────────────► screen: did the run complete and look valid?
       │
       ▼
   f₅  Visualization ◄─────── parse_results(csv_data)
       │
       ▼
   f₆  Skeptic ─────────────► physics-grounded falsification (verdict)
       │
       ▼   (falsified + recoverable)
   recovery.py ─────────────► classify failure → bounded correction → re-run

The pipeline is formally :math:`\mathcal{S} = f_5 \circ f_6 \circ f_4 \circ
f_3 \circ f_2 \circ f_1(\mathcal{U})` and partitions into three layers:
**cognitive** (f₁, f₂), **execution** (f₃, f₄), and **epistemic** (f₅, f₆) —
reframing the workflow from software stages into the epistemic roles
*generate*, *execute*, and *verify*.

Agents
------

f₁ Architect
~~~~~~~~~~~~
Decomposes the user's natural-language problem description into structured
simulation parameters, selecting physics, boundary conditions, and solver
settings, and routes the specification to the plugin registry.

f₂ Input Writer
~~~~~~~~~~~~~~~
Generates a valid MOOSE ``.i`` input file via six coordinated sub-agents, each
responsible for one MOOSE input block:

- **Meshing** — mesh type, element size, dimensions
- **Variables** — field variable declarations
- **Kernels** — PDE kernel specifications
- **Materials** — material property definitions
- **Postprocessors** — output quantity definitions
- **Executioner** — solver type, time-stepping, convergence criteria

f₃ Runner
~~~~~~~~~
Executes the simulation on the configured **execution backend** — a local
subprocess or a remote HPC/SLURM job (see :doc:`execution`) — streams the
solver log, and writes a self-contained, timestamped run directory under
``runs/`` with a full provenance manifest.

f₄ Reviewer
~~~~~~~~~~~
Screens the completed run — an *operational* check: did the simulation reach a
terminal state and do the metrics look physically valid? Correction is handled downstream by the closed-loop recovery
module acting on the Skeptic's verdict.

f₅ Visualization
~~~~~~~~~~~~~~~~
Reads postprocessor CSV via ``parse_results()``, extracts quantitative
observables (kinetics, Arrhenius fits), and generates figures and a
natural-language interpretation.

f₆ Skeptic
~~~~~~~~~~
Adversarially tests each completed, successful run against physics-grounded
falsification invariants — a *physical* check, distinct from the Reviewer:
should we believe the result? For grain growth it tests monotonicity,
asymptotic behavior, parabolic Burke–Turnbull scaling, numerical integrity,
and cross-run Arrhenius consistency; for conserved Cahn–Hilliard dynamics it
tests the exact laws of mass conservation and free-energy dissipation, plus
coarsening. Each invariant returns a verdict and, on failure, a diagnosis. The
Skeptic falsifies.

Closed-loop recovery
~~~~~~~~~~~~~~~~~~~~~~
When the Skeptic falsifies a run for a recoverable reason (for example a
time-step divergence), a separate module, ``recovery.py``, classifies the
failure and applies a bounded correction — such as a time-step cutback
:math:`\Delta t \leftarrow \alpha\,\Delta t` — and re-runs the pipeline.
Detection (Skeptic) is deliberately kept distinct from correction (recovery):
a corrected run is accepted only if it re-completes **and** the Skeptic
re-admits it. All recovery actions are logged for auditability.

Model-Agnostic Backend
----------------------

Every agent is driven by a configurable language-model backend. A
provider-agnostic client reads the provider, model, and endpoint from
configuration and dispatches to either a hosted API or a self-hosted
open-weights model behind an OpenAI-compatible endpoint. Switching backends is
a configuration change, not a code change, so the framework does not depend on
any single model or provider remaining available.

Execution Backend
-----------------

The Runner targets a pluggable execution backend selected by configuration:

- **local** — runs MOOSE as a subprocess on the current machine.
- **hpc** — stages files to NERSC Perlmutter, submits a SLURM job, polls it,
  and fetches results back.

See :doc:`execution` for setup and usage of both backends.

Plugin Registry
---------------

The plugin registry decouples physics implementations from the agent pipeline.
Each plugin is a directory under ``automoose/plugins/`` whose ``plugin.py``
exposes a ``PLUGIN`` metadata dict and a module-level
``generate_input(**params) -> str`` (with an optional
``parse_results(csv_data) -> dict``); the registry auto-discovers it at
start-up. Currently registered plugins:

.. list-table::
   :header-rows: 1
   :widths: 40 20 40

   * - Plugin
     - Status
     - Notes
   * - Grain Growth (Allen–Cahn)
     - ready
     - Non-conserved; two formulations, 2D/3D, seven presets
   * - Spinodal (Cahn–Hilliard)
     - ready
     - Conserved; CALPHAD Fe–Cr free-energy mode
   * - Ferroelectric (LGD)
     - stub
     - Future implementation
   * - Solidification (dendritic)
     - stub
     - Future implementation

MCP Interface
-------------

AutoMOOSE exposes its capabilities via a **Model Context Protocol (MCP)**
server (Starlette/uvicorn, port 8001) over stdio and SSE transports.
See :doc:`mcp_interface` for full tool documentation.
