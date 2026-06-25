Installation
============

Prerequisites
-------------

- Python 3.11
- A compiled MOOSE framework installation (``phase_field-opt`` binary)
- Node.js 18+ (for the frontend)
- Git
- (Optional, for HPC execution) a NERSC account with ``sshproxy`` configured —
  see :doc:`execution`

Clone the Repository
--------------------

.. code-block:: bash

   git clone https://github.com/sukritimanna/AutoMOOSE.git
   cd AutoMOOSE

Python Dependencies
-------------------

.. code-block:: bash

   conda create -n automoose python=3.11
   conda activate automoose
   pip install -r requirements.txt

Environment Configuration
-------------------------

Copy the example config and edit it:

.. code-block:: bash

   cp config.env.example config.env

Set the core values in ``config.env``:

.. code-block:: bash

   # execution backend
   EXECUTION_BACKEND=local
   MOOSE_EXEC=/path/to/your/moose/phase_field-opt
   RUNS_DIR=./runs

   # model backend (model-agnostic)
   LLM_PROVIDER=anthropic
   LLM_MODEL=claude-sonnet-4-6
   # provider credentials as required, e.g. ANTHROPIC_API_KEY=...

For HPC execution, additionally set the ``HPC_*`` values described in
:doc:`execution`.

Frontend Dependencies
---------------------

.. code-block:: bash

   cd frontend
   npm install
   cd ..

Verify Installation
-------------------

.. code-block:: bash

   export $(grep -v '^#' config.env | xargs)
   python -c "from automoose.server import app; print('Backend OK')"
