Plugin Development
==================

AutoMOOSE's plugin registry allows you to add new physics modules
without modifying the core agent pipeline.

Plugin Interface
----------------

.. code-block:: python

   from automoose.plugins import PhysicsPlugin, register_plugin

   class MyPlugin(PhysicsPlugin):
       name = "MyPhysics"

       def generate_input(self, **params) -> str:
           """
           Generate a complete MOOSE .i input file string.

           Parameters
           ----------
           **params : dict
               Simulation parameters from the Architect agent.

           Returns
           -------
           str
               Valid MOOSE input file content.
           """
           ...

       def parse_results(self, csv_data: str) -> dict:
           """
           Parse MOOSE postprocessor CSV output.

           Parameters
           ----------
           csv_data : str
               Raw CSV string from MOOSE postprocessor output.

           Returns
           -------
           dict
               Structured results dictionary.
           """
           ...

   register_plugin(MyPlugin)

Common Pitfalls
---------------

Based on lessons from the GrainGrowth plugin development:

- **Duplicate block declarations** — each MOOSE block (e.g. ``[Kernels]``) must appear exactly once.
- **Duplicate solver parameters** — parameters like ``nl_abs_tol`` cannot appear in both ``[Executioner]`` and ``[Preconditioning]``.
- **Unused parameters** — MOOSE aborts on unrecognized parameters; check ``run.log`` with ``grep "ERROR\\|unused"``.
