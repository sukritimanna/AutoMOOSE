Quick Start
===========

Start All Services
------------------

Open three terminal tabs from the ``AutoMOOSE/`` root:

**Terminal 1 — FastAPI backend (port 8000):**

.. code-block:: bash

   cd backend
   export $(grep -v '^#' ../config.env | xargs)
   uvicorn server:app --host 0.0.0.0 --port 8000

**Terminal 2 — MCP server (port 8001):**

.. code-block:: bash

   cd backend
   export $(grep -v '^#' ../config.env | xargs)
   uvicorn mcp_server:app --host 0.0.0.0 --port 8001

**Terminal 3 — Frontend (port 5174):**

.. code-block:: bash

   cd frontend
   npm run dev

Then open ``http://localhost:5174`` in your browser.

Run Your First Simulation
--------------------------

In the AutoMOOSE UI, type a natural-language prompt such as:

   *"Run a grain growth simulation at 600 K for 100 seconds with a 50×50 mesh."*

AutoMOOSE will:

1. Parse your intent (f₁ Architect)
2. Generate the MOOSE input file (f₂ Input Writer)
3. Execute the simulation (f₃ Runner)
4. Validate results (f₄ Reviewer)
5. Produce plots (f₅ Visualization)

Results are saved under ``runs/<timestamp>_<physics>/``.

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
