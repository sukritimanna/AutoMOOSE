Plugin Development
==================

AutoMOOSE's plugin registry allows you to add new physics modules
without modifying the core agent pipeline. Each plugin implements a minimal
two-function contract, and the orchestration layer, MCP server, and UI require
no changes when a new plugin is added.

Available plugins
-----------------

.. list-table::
   :header-rows: 1
   :widths: 30 25 45

   * - Plugin
     - Status
     - Notes
   * - Grain Growth (Allen–Cahn)
     - validated
     - Non-conserved order parameters; two formulations (``GBEvolution``,
       ``LinearizedInterface``), 2D/3D, seven presets.
   * - Spinodal Decomposition (Cahn–Hilliard)
     - validated
     - Conserved order parameter; includes a CALPHAD-based Fe–Cr free-energy
       mode validated against exact mass conservation and free-energy
       dissipation.
   * - Ferroelectric Switching (Landau–Ginzburg–Devonshire)
     - stub
     - Registered for future implementation.
   * - Solidification (Allen–Cahn dendritic)
     - stub
     - Registered for future implementation.

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

Verification invariants
-----------------------

When you add a plugin, you can register physics-grounded falsification
invariants for the Skeptic agent (:math:`f_6`). These are exact or
quantitative laws the result must obey — for example, mass conservation and
free-energy dissipation for conserved (Cahn–Hilliard) dynamics, or monotonic
coarsening and parabolic scaling for grain growth. The Skeptic uses them to
issue a credibility verdict on each completed run.

Common Pitfalls
---------------

Based on lessons from the GrainGrowth plugin development:

- **Duplicate block declarations** — each MOOSE block (e.g. ``[Kernels]``) must appear exactly once.
- **Duplicate solver parameters** — parameters like ``nl_abs_tol`` cannot appear in both ``[Executioner]`` and ``[Preconditioning]``.
- **Unused parameters** — MOOSE aborts on unrecognized parameters; check ``run.log`` with ``grep "ERROR\\|unused"``.
