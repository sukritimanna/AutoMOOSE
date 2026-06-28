Agents
======

AutoMOOSE orchestrates the MOOSE simulation lifecycle through a sequential
multi-agent pipeline,

.. math::

   \mathcal{S} = f_5 \circ f_6 \circ f_4 \circ f_3 \circ f_2 \circ f_1(\mathcal{U}),

where :math:`\mathcal{U}` is the natural-language user intent and each agent
:math:`f_i` enriches a shared simulation plan. The pipeline partitions into
three functional layers — **cognitive**, **execution**, and **epistemic** —
reframing the workflow from software stages into epistemic roles: *generate*,
*execute*, and *verify*.

Cognitive layer
---------------

**Architect** (:math:`f_1`)
   Parses the natural-language prompt into a fully resolved, structured
   simulation plan (physics formulation, dimensionality, boundary conditions,
   sweep intent, solver strategy). Emits strict JSON for the Input Writer.

**Input Writer** (:math:`f_2`)
   Renders a complete, syntax-validated MOOSE ``.i`` input file from the plan
   via the plugin registry, coordinating block generation in dependency order
   and enforcing constraints such as interface resolution.

Execution layer
---------------

**Runner** (:math:`f_3`)
   Executes the simulation on the configured execution backend (local
   subprocess or HPC/SLURM; see :doc:`execution`), creates a timestamped,
   self-contained run directory, and records a full provenance manifest.

**Reviewer** (:math:`f_4`)
   Screens the completed run — an *operational* check: did it reach a terminal
   state and do the metrics look physically valid? Correction is handled by the closed-loop recovery module acting
   on the Skeptic's verdict.

Epistemic layer
---------------

**Visualization** (:math:`f_5`)
   Extracts quantitative observables (e.g. coarsening kinetics, Arrhenius fits)
   from the completed run and produces a natural-language interpretation.

**Skeptic** (:math:`f_6`)
   Adversarially tests each completed, successful run against physics-grounded
   falsification invariants — distinct from the Reviewer, this is a *physical*
   check: should we believe the result? For grain growth it tests grain-count
   monotonicity, asymptotic behavior, parabolic Burke–Turnbull scaling,
   numerical integrity, and cross-run Arrhenius consistency. For conserved
   Cahn–Hilliard dynamics it tests the exact laws of mass conservation and
   free-energy dissipation, plus coarsening. Each invariant returns a verdict
   and, on failure, a diagnosis that localizes the likely cause. The Skeptic
   falsifies.

Closed-loop recovery
--------------------

When the Skeptic falsifies a run for a recoverable reason (for example a
time-step divergence), ``recovery.py`` classifies the failure and applies a
bounded correction — such as a time-step cutback
:math:`\Delta t \leftarrow \alpha\,\Delta t` — before re-running the pipeline.
Detection is kept separate from correction, and a corrected run is accepted
only if it re-completes **and** the Skeptic re-admits it. Recovery actions are
logged, so an automatically corrected run carries an audit trail from prompt
to accepted result.

Model-agnostic backend
----------------------

Every agent is driven by a configurable language-model backend rather than any
hard-coded model. A provider-agnostic client reads the provider, model, and
endpoint from configuration and dispatches to either a hosted API or a
self-hosted open-weights model behind an OpenAI-compatible endpoint; switching
backends is a configuration change, not a code change.

.. note::
   Per-agent API documentation is generated from docstrings; see :doc:`api`.
