Plugin Development
==================

AutoMOOSE's plugin registry lets you add new physics modules without modifying
the core agent pipeline. Each plugin is a self-contained directory, and the
orchestration layer, MCP server, and UI require no changes when a new plugin is
added — the registry auto-discovers it at start-up.

Available plugins
-----------------

.. list-table::
   :header-rows: 1
   :widths: 30 25 45

   * - Plugin
     - Status
     - Notes
   * - Grain Growth (Allen–Cahn)
     - ready
     - Non-conserved order parameters; two formulations (``GBEvolution``,
       ``LinearizedInterface``), 2D/3D, seven presets.
   * - Spinodal Decomposition (Cahn–Hilliard)
     - ready
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

A plugin lives in ``automoose/plugins/<name>/plugin.py`` and exposes a
``PLUGIN`` metadata dictionary together with a module-level
``generate_input(**params)``. An optional ``parse_results(csv_data)`` maps the
MOOSE postprocessor CSV to a metrics dict. No registration call is required —
``plugin_registry.py`` discovers every directory whose ``plugin.py`` defines a
``PLUGIN`` dict:

.. code-block:: python

   # automoose/plugins/myphysics/plugin.py

   PLUGIN = {
       "label":          "My Physics",
       "status":         "ready",          # "ready" | "stub"
       "params":         {                 # name -> metadata
           "T":  {"default": 800, "range": [300, 1200]},
           # ...
       },
       "sweepable":      ["T"],            # parameters a sweep may vary
       "executable_key": "MOOSE_EXEC",     # env var holding the solver path
       "system_prompt":  "You are a MOOSE expert for <physics>.",
   }


   def generate_input(**params) -> str:
       """Return a complete MOOSE .i input file as a string."""
       ...


   def parse_results(csv_data) -> dict:    # optional
       """Map MOOSE postprocessor CSV output to a structured metrics dict."""
       ...

Verification invariants
-----------------------

Physics-grounded falsification invariants are defined in the Skeptic agent
(:math:`f_6`), currently for the grain-growth and spinodal domains. These are
exact or quantitative laws the result must obey — for example mass conservation
and free-energy dissipation for conserved (Cahn–Hilliard) dynamics, or monotonic
coarsening and parabolic Burke–Turnbull scaling for grain growth. The Skeptic
uses them to issue a credibility verdict on each completed run. Extending the
Skeptic to a new plugin means adding an invariant battery for that physics.

Common Pitfalls
---------------

Based on lessons from the GrainGrowth plugin development:

- **Duplicate block declarations** — each MOOSE block (e.g. ``[Kernels]``) must appear exactly once.
- **Duplicate solver parameters** — parameters like ``nl_abs_tol`` cannot appear in both ``[Executioner]`` and ``[Preconditioning]``.
- **Unused parameters** — MOOSE aborts on unrecognized parameters; check ``run.log`` with ``grep "ERROR\\|unused"``.
