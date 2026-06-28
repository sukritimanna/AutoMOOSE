MCP Interface
=============

AutoMOOSE exposes a **Model Context Protocol (MCP)** server that allows
external LLM agents and tools to interact with the simulation pipeline
programmatically.

Server Details
--------------

- **Transport**: stdio and SSE
- **Host**: ``0.0.0.0``
- **Port**: ``8001``
- **Framework**: Starlette / uvicorn

The MCP server acts as a hub, routing tool calls from external clients to the
six-agent pipeline and plugin registry. Validation, falsification, and recovery
run **inside** the backend pipeline that ``run_simulation`` and ``run_sweep``
invoke, rather than as separately callable tools.

Available Tools
---------------

The server exposes ten tools:

.. list-table::
   :header-rows: 1
   :widths: 28 72

   * - Tool Name
     - Description
   * - ``health_check``
     - Verify the backend is up and the MOOSE executables are found
   * - ``list_plugins``
     - List physics plugins with their parameters and sweep fields
   * - ``generate_input``
     - Preview a MOOSE ``.i`` file without running it
   * - ``run_simulation``
     - Launch a single simulation; returns a ``run_id``
   * - ``run_sweep``
     - Launch a parallel sweep over a parameter list
   * - ``get_run_status``
     - Poll status: pending / running / done / failed
   * - ``get_results``
     - Retrieve metrics (``N(t)``, ``R²``, ``dN/dt``, …)
   * - ``list_runs``
     - Browse run history with optional filters
   * - ``get_log_tail``
     - Read the last *N* lines of the MOOSE solver log
   * - ``stop_run``
     - Terminate an active simulation

Example: running a simulation
-----------------------------

From an MCP client (Claude Desktop, Claude Code, or any MCP-compatible tool),
the tools are called directly:

.. code-block:: text

   run_simulation(physics="grain_growth",
                  params={"T": 450, "num_grains": 15, "dim": 2})   ->  run_id
   get_run_status(run_id)                                          ->  "done"
   get_results(run_id)                                            ->  metrics

The same pipeline is reachable over the FastAPI REST backend (port 8000), which
is convenient for scripted use:

.. code-block:: python

   import httpx

   started = httpx.post("http://localhost:8000/run", json={
       "physics": "grain_growth",
       "params":  {"T": 450, "num_grains": 15},
   }).json()
   run_id = started["run_id"]

   status = httpx.get(f"http://localhost:8000/runs/{run_id}").json()["status"]
   csv    = httpx.get(f"http://localhost:8000/runs/{run_id}/csv").text

Future Directions
-----------------

RAG (Retrieval-Augmented Generation) integration is planned as a future
extension to augment the Architect agent with retrieval over MOOSE
documentation and prior simulation records.
