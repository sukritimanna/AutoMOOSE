Architecture
============

AutoMOOSE v2 implements a five-agent pipeline with a plugin registry
and an MCP interface layer.

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
   f₃  Runner ──────────────► MOOSE Executable
       │
       ▼
   f₄  Reviewer ◄──────────── parse_results(csv_data)
       │
       ▼
   f₅  Visualization

Agents
------

f₁ Architect
~~~~~~~~~~~~
Decomposes the user's natural-language problem description into structured
simulation parameters. Relies on pre-trained MOOSE domain knowledge to
select appropriate physics, boundary conditions, and solver settings.
Routes the parameterized specification to the plugin registry.

f₂ Input Writer
~~~~~~~~~~~~~~~
Generates a valid MOOSE ``.i`` input file. Implemented as six coordinated
sub-agents, each responsible for one MOOSE input block:

- **Meshing** — mesh type, element size, dimensions
- **Variables** — field variable declarations
- **Kernels** — PDE kernel specifications
- **Materials** — material property definitions
- **Postprocessors** — output quantity definitions
- **Executioner** — solver type, time-stepping, convergence criteria

f₃ Runner
~~~~~~~~~
Launches the MOOSE executable, streams ``run.log`` output, monitors
convergence, and writes results to the run directory under ``runs/``.

f₄ Reviewer
~~~~~~~~~~~
Parses ``run.log`` for ``ERROR`` and ``unused`` parameter warnings,
validates CSV output against expected postprocessors, and flags
issues back to f₂ for correction if needed.

f₅ Visualization
~~~~~~~~~~~~~~~~
Reads postprocessor CSV data via ``parse_results()`` and generates
publication-quality phase-field evolution figures.

Plugin Registry
---------------

The plugin registry decouples physics implementations from the agent
pipeline. Each plugin exposes:

.. code-block:: python

   def generate_input(self, **params) -> str:
       """Return a complete MOOSE .i input file."""

   def parse_results(self, csv_data: str) -> dict:
       """Parse postprocessor CSV and return structured results."""

Currently registered plugins:

+-------------------+---------+
| Plugin            | Status  |
+===================+=========+
| GrainGrowth       | Active  |
+-------------------+---------+
| Solidification    | Stub    |
+-------------------+---------+
| Spinodal          | Stub    |
+-------------------+---------+
| Precipitate       | Stub    |
+-------------------+---------+

MCP Interface
-------------

AutoMOOSE exposes its capabilities via a **Model Context Protocol (MCP)**
server (Starlette/uvicorn, port 8001) with ten tools over stdio and SSE
transports. See :doc:`mcp_interface` for full tool documentation.
