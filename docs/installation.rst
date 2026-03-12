Installation
============

Prerequisites
-------------

- Python 3.10 or higher
- A compiled MOOSE framework installation (``phase_field-opt`` binary)
- Node.js 18+ (for the frontend)
- Git

Clone the Repository
--------------------

.. code-block:: bash

   git clone https://github.com/<your-org>/AutoMOOSE.git
   cd AutoMOOSE

Python Dependencies
-------------------

.. code-block:: bash

   pip install -r requirements.txt

Environment Configuration
-------------------------

Copy the example config and set your MOOSE executable path:

.. code-block:: bash

   cp config.env.example config.env

Edit ``config.env``:

.. code-block:: bash

   MOOSE_EXEC=/path/to/your/moose/phase_field-opt
   RUNS_DIR=../runs

Frontend Dependencies
---------------------

.. code-block:: bash

   cd frontend
   npm install
   cd ..

Verify Installation
-------------------

.. code-block:: bash

   cd backend
   export $(grep -v '^#' ../config.env | xargs)
   python -c "from server import app; print('Backend OK')"
