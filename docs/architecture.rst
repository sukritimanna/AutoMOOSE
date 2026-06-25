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
   f₄  Reviewer ◄──────────── (on failure: diagnose + retry → f₂)
       │
       ▼
   f₅  Visualization ◄─────── parse_results(csv_data)
       │
       ▼
   f₆  Skeptic ─────────────► physics-grounded falsification (verdict)

The pipeline is formally :math:`\mathcal{S} = f_6 \circ f_5 \circ f_4 \circ
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
On a non-zero exit, diagnoses the failure class and proposes corrected
parameters, returning them to f₂ via the retry arc. An *operational* check:
did the simulation run?

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
coarsening. Each invariant returns a verdict and, on failure, a diagnosis.

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
Each plugin exposes ``generate_input(**params) -> str`` and
``parse_results(csv_data) -> dict``. Currently registered plugins:

.. list-table::
   :header-rows: 1
   :widths: 40 20 40

   * - Plugin
     - Status
     - Notes
   * - Grain Growth (Allen–Cahn)
     - validated
     - Non-conserved; two formulations, 2D/3D, seven presets
   * - Spinodal (Cahn–Hilliard)
     - validated
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
