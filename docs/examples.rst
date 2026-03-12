Examples
========

Grain Growth Temperature Sweep
-------------------------------

Run a four-temperature sweep (300, 450, 600, 750 K) to characterize
grain boundary mobility as a function of temperature:

.. code-block:: bash

   for T in 300 450 600 750; do
     curl -X POST http://localhost:8000/api/runs \
       -H "Content-Type: application/json" \
       -d "{\"plugin\": \"GrainGrowth\", \"temperature\": $T, \"duration\": 200}"
   done

Results are written to ``runs/<timestamp>_GrainGrowth_<T>K/``.
