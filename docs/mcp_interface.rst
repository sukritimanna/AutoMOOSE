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

The MCP server acts as a hub, routing tool calls from external clients
to the five-agent pipeline and plugin registry.

Available Tools
---------------

The server exposes ten tools:

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Tool Name
     - Description
   * - ``list_plugins``
     - List all registered physics plugins and their status
   * - ``create_run``
     - Initialize a new simulation run with given parameters
   * - ``generate_input``
     - Invoke f₂ Input Writer to produce a MOOSE ``.i`` file
   * - ``submit_run``
     - Execute the simulation via f₃ Runner
   * - ``get_run_status``
     - Poll run status from ``record.json``
   * - ``get_run_log``
     - Retrieve ``run.log`` content for a given run
   * - ``review_run``
     - Invoke f₄ Reviewer on completed run output
   * - ``get_results``
     - Return parsed postprocessor CSV data
   * - ``visualize_run``
     - Trigger f₅ Visualization for a completed run
   * - ``list_runs``
     - List all runs with status and metadata

Example: Creating a Run via MCP
--------------------------------

.. code-block:: python

   import httpx

   response = httpx.post("http://localhost:8001/mcp/tool", json={
       "tool": "create_run",
       "params": {
           "plugin": "GrainGrowth",
           "temperature": 600,
           "duration": 100,
           "mesh_size": [50, 50]
       }
   })
   print(response.json())

Future Directions
-----------------

RAG (Retrieval-Augmented Generation) integration is planned as a future
extension to augment the Architect agent with retrieval over MOOSE
documentation and prior simulation records.
