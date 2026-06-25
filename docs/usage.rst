Usage
=====

See :doc:`quickstart` to get up and running, and :doc:`execution` for running
locally versus on HPC.

Selecting an execution backend
------------------------------

AutoMOOSE runs simulations either locally or on NERSC Perlmutter, selected by a
single value in ``config.env``:

.. code-block:: bash

   EXECUTION_BACKEND=local   # development, small 2D cases
   EXECUTION_BACKEND=hpc     # production, 3D, large meshes, sweeps

The agent pipeline is identical for both; only where MOOSE executes changes.
See :doc:`execution` for full setup (including NERSC ``sshproxy``
authentication).

Selecting a model backend
-------------------------

The pipeline is model-agnostic. Set the backend in ``config.env``:

.. code-block:: bash

   LLM_PROVIDER=anthropic            # or an OpenAI-compatible endpoint
   LLM_MODEL=claude-sonnet-4-6       # or a self-hosted open-weights model

Switching backends is a configuration change; no code changes are required.

Driving the pipeline headlessly
-------------------------------

Beyond the web UI, the full pipeline can be run from the command line:

.. code-block:: bash

   python -m automoose.agents.orchestrator --physics grain_growth \
       --params '{"T":800,"n_grains":50}'

Each completed run is automatically verified by the Skeptic agent (f₆), which
reports a credibility verdict alongside the extracted metrics.
