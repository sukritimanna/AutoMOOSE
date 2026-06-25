Quick Start
===========

Start All Services
------------------

Open three terminal tabs from the ``AutoMOOSE/`` root:

**Terminal 1 — FastAPI backend (port 8000):**

.. code-block:: bash

   export $(grep -v '^#' config.env | xargs)
   uvicorn automoose.server:app --host 127.0.0.1 --port 8000

**Terminal 2 — MCP server (port 8001):**

.. code-block:: bash

   export $(grep -v '^#' config.env | xargs)
   uvicorn automoose.mcp_server:app --host 127.0.0.1 --port 8001

**Terminal 3 — Frontend (port 5174):**

.. code-block:: bash

   cd frontend
   npm run dev

Then open ``http://localhost:5174`` in your browser.

.. tip::
   Use ``127.0.0.1`` rather than ``localhost`` to avoid IPv4/IPv6 ambiguity in
   local API calls. Stop the backend with ``Ctrl+C`` (never ``Ctrl+Z``); if a
   port is stuck, free it with ``lsof -ti:8000 | xargs kill -9``.

Run Your First Simulation
--------------------------

In the AutoMOOSE UI, type a natural-language prompt such as:

   *"Run a grain growth simulation at 600 K for 100 seconds with a 50×50 mesh."*

AutoMOOSE will:

1. Parse your intent (f₁ Architect)
2. Generate the MOOSE input file (f₂ Input Writer)
3. Execute the simulation on the configured backend (f₃ Runner)
4. Recover from any convergence failures (f₄ Reviewer)
5. Extract kinetics and produce plots (f₅ Visualization)
6. Verify the result against physics invariants (f₆ Skeptic)

Results are saved under ``runs/<timestamp>_<physics>/``, and the Skeptic
reports a credibility verdict for the run.

Headless / scripted runs
------------------------

You can also drive the full pipeline from the command line, which is the basis
for batch benchmarks and HPC sweeps:

.. code-block:: bash

   python -m automoose.agents.orchestrator --physics grain_growth \
       --params '{"T":800,"n_grains":50}'

Choosing where it runs
----------------------

Set the execution backend in ``config.env`` (see :doc:`execution`):

.. code-block:: bash

   EXECUTION_BACKEND=local   # run on this machine
   EXECUTION_BACKEND=hpc     # run on NERSC Perlmutter via SLURM

Monitor Runs
------------

Check run status directly from JSON records:

.. code-block:: bash

   python3 -c "
   import json, glob
   for p in sorted(glob.glob('runs/2026*/record.json')):
       r = json.load(open(p))
       print(r.get('status'), p)
   "
