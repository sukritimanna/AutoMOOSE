"""
AutoMOOSE Plugin — Spinodal Decomposition (Cahn-Hilliard)
=========================================================
Conserved-order-parameter phase separation via the split Cahn-Hilliard equation.
A second, physically distinct domain from grain growth (conserved vs. non-conserved
dynamics), with rigorous validation invariants:

  - Mass conservation        : integral of c is exactly constant (CH conserves c)
  - Free-energy dissipation  : total free energy decreases monotonically (gradient flow)
  - Coarsening scaling       : characteristic domain size L(t) ~ t^(1/3) (Lifshitz-Slyozov)

Free-energy modes:
  - double_well : f = W c^2 (1-c)^2     (clean, controllable; default for validation)
  - FeCr        : CALPHAD-style Fe-Cr local free energy (realistic alloy)

Executable: phase_field-opt (MOOSE phase_field module, split CH kernels)
"""
import os, socket
from datetime import datetime

PLUGIN = {
    "label":          "Spinodal",
    "icon":           "🌊",
    "description":    "Cahn-Hilliard spinodal decomposition — conserved order parameter, 2D/3D",
    "executable_key": "MOOSE_EXEC",
    "status":         "ready",
    "params": {
        "run_name":   "spinodal",
        "dim":        2,
        # Mesh
        "nx": 100, "ny": 100, "nz": 20,
        "xmax": 25.0, "ymax": 25.0, "zmax": 25.0,
        "uniform_refine": 0,
        "periodic_x": True, "periodic_y": True, "periodic_z": True,
        # Composition initial condition (spinodal: near-uniform + small noise)
        "c0":         0.4677,     # mean mole fraction
        "noise":      0.02,       # +/- spread of RandomIC
        "rand_seed":  210,
        # Free energy
        "fe_mode":    "double_well",   # double_well | FeCr
        "W":          1.0,             # double-well barrier height (eV/mol scale)
        "kappa":      0.5,             # gradient energy coefficient
        "M":          1.0,             # mobility (double_well mode)
        # Solver
        "preconditioner": "asm",
        "nl_max_its": 50, "nl_abs_tol": 1e-9,
        "l_max_its":  30, "l_tol": 1e-6,
        "optimal_iterations": 7,
        # Time
        "time_mode":  "end_time",
        "end_time":   100.0, "num_steps": 500,
        "dt_start":   0.1, "dt_cutback": 0.8, "dt_growth": 1.5,
        # Adaptivity / outputs
        "use_adaptivity": True, "refine_fraction": 0.7, "coarsen_fraction": 0.1,
        "max_h_level": 2,
        "feature_threshold": 0.5,   # threshold for FeatureFloodCount domain counting
    },
    "presets": {
        "validation_doublewell": {
            "fe_mode": "double_well", "c0": 0.5, "noise": 0.02,
            "nx": 100, "ny": 100, "end_time": 100.0,
        },
        "FeCr_alloy": {
            "fe_mode": "FeCr", "c0": 0.4677, "noise": 0.02,
            "nx": 100, "ny": 100, "end_time": 100.0,
        },
    },
    "sweepable":   ["c0", "kappa", "M", "W", "noise", "end_time"],
    "result_keys": ["domains_initial", "domains_final", "coarsening_exponent",
                    "coarsening_R2", "c_conservation_drift", "energy_monotone"],
    "system_prompt": ("You are a MOOSE Cahn-Hilliard spinodal decomposition expert. "
                      "You set up split-form CH simulations of conserved-composition "
                      "phase separation, validate mass conservation and free-energy "
                      "dissipation, and quantify domain coarsening against the t^(1/3) law."),
}


# ── helpers ────────────────────────────────────────────────────────────────
def _periodic(px, py, pz, dim):
    dirs = []
    if px: dirs.append("x")
    if py: dirs.append("y")
    if pz and dim == 3: dirs.append("z")
    return " ".join(dirs) if dirs else "x y"


def _free_energy_block(fe_mode, W):
    if fe_mode == "FeCr":
        # CALPHAD-style Fe-Cr local free energy (eV/mol, with unit scaling d)
        return """  [local_energy]
    type = DerivativeParsedMaterial
    property_name = f_loc
    coupled_variables = c
    constant_names = 'A B C D E F G eV_J d'
    constant_expressions = '-2.446831e+04 -2.827533e+04 4.167994e+03 7.052907e+03
                            1.208993e+04 2.568625e+03 -2.354293e+03
                            6.24150934e+18 1e-27'
    expression = 'eV_J*d*(A*c+B*(1-c)+C*c*log(c)+D*(1-c)*log(1-c)+
                E*c*(1-c)+F*c*(1-c)*(2*c-1)+G*c*(1-c)*(2*c-1)^2)'
    derivative_order = 2
  []"""
    # default: symmetric double well  f = W c^2 (1-c)^2
    return f"""  [local_energy]
    type = DerivativeParsedMaterial
    property_name = f_loc
    coupled_variables = c
    constant_names = 'W'
    constant_expressions = '{W}'
    expression = 'W*c^2*(1-c)^2'
    derivative_order = 2
  []"""


def _constants_block(fe_mode, kappa, M):
    if fe_mode == "FeCr":
        # canonical Fe-Cr kappa and constant mobility (unit-scaled)
        return """  [constants]
    type = GenericFunctionMaterial
    prop_names  = 'kappa_c M'
    prop_values = '8.125e-16*6.24150934e+18*1e+09^2*1e-27
                   2.2841e-26*1e+09^2/6.24150934e+18/1e-27'
  []"""
    return f"""  [constants]
    type = GenericConstantMaterial
    prop_names  = 'kappa_c M'
    prop_values = '{kappa} {M}'
  []"""


# ── main generator ──────────────────────────────────────────────────────────
def generate_input(
    run_name="spinodal", dim=2,
    nx=100, ny=100, nz=20,
    xmax=25.0, ymax=25.0, zmax=25.0,
    uniform_refine=0,
    periodic_x=True, periodic_y=True, periodic_z=True,
    c0=0.4677, noise=0.02, rand_seed=210,
    fe_mode="double_well", W=1.0, kappa=0.5, M=1.0,
    preconditioner="asm", nl_max_its=50, nl_abs_tol=1e-9,
    l_max_its=30, l_tol=1e-6, optimal_iterations=7,
    time_mode="end_time", end_time=100.0, num_steps=500,
    dt_start=0.1, dt_cutback=0.8, dt_growth=1.5,
    use_adaptivity=True, refine_fraction=0.7, coarsen_fraction=0.1, max_h_level=2,
    feature_threshold=0.5,
    **kwargs,
) -> str:
    dim = int(dim)
    is3d = dim == 3
    cmin = max(0.0, c0 - noise)
    cmax = min(1.0, c0 + noise)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    mesh_label = f"{nx}×{ny}×{nz}" if is3d else f"{nx}×{ny}"
    periodic_dirs = _periodic(periodic_x, periodic_y, periodic_z, dim)

    # mesh block
    if is3d:
        mesh = f"""[Mesh]
  type = GeneratedMesh
  dim = 3
  elem_type = HEX8
  nx = {nx}
  ny = {ny}
  nz = {nz}
  xmin = 0  xmax = {xmax}
  ymin = 0  ymax = {ymax}
  zmin = 0  zmax = {zmax}
  uniform_refine = {uniform_refine}
[]"""
    else:
        mesh = f"""[Mesh]
  type = GeneratedMesh
  dim = 2
  elem_type = QUAD4
  nx = {nx}
  ny = {ny}
  nz = 0
  xmin = 0  xmax = {xmax}
  ymin = 0  ymax = {ymax}
  zmin = 0  zmax = 0
  uniform_refine = {uniform_refine}
[]"""

    adaptivity = ""
    if use_adaptivity:
        adaptivity = f"""  [Adaptivity]
    coarsen_fraction = {coarsen_fraction}
    refine_fraction = {refine_fraction}
    max_h_level = {max_h_level}
  []"""

    time_block = (f"end_time = {end_time}" if time_mode == "end_time"
                  else f"num_steps = {num_steps}")

    text = f"""# AutoMOOSE — Spinodal Decomposition (Cahn-Hilliard, {('3D' if is3d else '2D')})
# Generated   : {ts}
# Run         : {run_name}
# Free energy : {fe_mode}
# Mesh        : {mesh_label}  uniform_refine={uniform_refine}
# Composition : c0={c0} +/- {noise}  (RandomIC seed {rand_seed})
# Validation  : mass conservation (total_c), free-energy dissipation (total_energy),
#               domain coarsening L(t)~t^(1/3) (num_features)

{mesh}

[Variables]
  [c]
    order = FIRST
    family = LAGRANGE
  []
  [w]
    order = FIRST
    family = LAGRANGE
  []
[]

[AuxVariables]
  [f_density]
    order = CONSTANT
    family = MONOMIAL
  []
[]

[ICs]
  [concentrationIC]
    type = RandomIC
    variable = c
    min = {cmin}
    max = {cmax}
    seed = {rand_seed}
  []
[]

[BCs]
  [Periodic]
    [all]
      auto_direction = '{periodic_dirs}'
    []
  []
[]

[Kernels]
  [w_dot]
    type = CoupledTimeDerivative
    variable = w
    v = c
  []
  [coupled_res]
    type = SplitCHWRes
    variable = w
    mob_name = M
  []
  [coupled_parsed]
    type = SplitCHParsed
    variable = c
    f_name = f_loc
    kappa_name = kappa_c
    w = w
  []
[]

[AuxKernels]
  [f_density]
    type = TotalFreeEnergy
    variable = f_density
    f_name = 'f_loc'
    kappa_names = 'kappa_c'
    interfacial_vars = c
    execute_on = 'INITIAL TIMESTEP_END'
  []
[]

[Materials]
{_constants_block(fe_mode, kappa, M)}
{_free_energy_block(fe_mode, W)}
[]

[Postprocessors]
  [total_c]                 # MASS CONSERVATION: integral of c must stay constant
    type = ElementIntegralVariablePostprocessor
    variable = c
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [total_energy]            # FREE-ENERGY DISSIPATION: must decrease monotonically
    type = ElementIntegralVariablePostprocessor
    variable = f_density
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [num_features]            # DOMAIN COUNT: drives L(t)~t^(1/3) coarsening
    type = FeatureFloodCount
    variable = c
    threshold = {feature_threshold}
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [dt]
    type = TimestepSize
  []
[]

[Preconditioning]
  [coupled]
    type = SMP
    full = true
  []
[]

[Executioner]
  type = Transient
  solve_type = NEWTON
  l_max_its = {l_max_its}
  l_tol = {l_tol}
  nl_max_its = {nl_max_its}
  nl_abs_tol = {nl_abs_tol}
  {time_block}
  petsc_options_iname = '-pc_type -ksp_gmres_restart -sub_ksp_type -sub_pc_type -pc_asm_overlap'
  petsc_options_value = '{preconditioner} 31 preonly ilu 1'
  [TimeStepper]
    type = IterationAdaptiveDT
    dt = {dt_start}
    cutback_factor = {dt_cutback}
    growth_factor = {dt_growth}
    optimal_iterations = {optimal_iterations}
  []
{adaptivity}
[]

[Outputs]
  exodus = true
  csv = true
  [console]
    type = Console
    max_rows = 10
  []
[]
"""
    return text


# ── results parsing + validation metrics ────────────────────────────────────
def parse_results(csv_data: dict) -> dict:
    """Extract spinodal validation metrics from the CSV postprocessor columns.
    Columns: time, total_c, total_energy, num_features, dt (+ MOOSE extras)."""
    import math
    m = {}
    t = csv_data.get("time") or []
    if not t:
        return m
    m["total_timesteps"] = len(t)
    m["final_time"] = t[-1]
    m["time_series"] = t

    # MASS CONSERVATION: drift of integral(c) from its initial value
    tc = csv_data.get("total_c")
    if tc:
        c0_int = tc[0]
        drift = max(abs(v - c0_int) for v in tc)
        m["c_integral_initial"]   = c0_int
        m["c_integral_final"]     = tc[-1]
        m["c_conservation_drift"] = drift
        m["c_conservation_rel"]   = drift / abs(c0_int) if c0_int else None
        m["total_c_series"]       = tc

    # FREE-ENERGY DISSIPATION: must be (near-)monotone decreasing
    en = csv_data.get("total_energy")
    if en:
        rises = sum(1 for a, b in zip(en, en[1:]) if b > a + 1e-9 * max(1.0, abs(a)))
        m["energy_initial"]  = en[0]
        m["energy_final"]    = en[-1]
        m["energy_monotone"] = (rises == 0)
        m["energy_rises"]    = rises
        m["total_energy_series"] = en

    # COARSENING: domain count N(t) decreases; characteristic size L ~ N^(-1/dim).
    # In 2D, area/domain ~ 1/N, so L ~ N^(-1/2). Lifshitz-Slyozov: L^3 ~ t  =>
    # fit log L vs log t, slope ~ 1/3.  L proxy = N^(-1/2).
    nf = csv_data.get("num_features")
    if nf and len(t) > 4:
        m["domains_initial"] = nf[0]
        m["domains_final"]   = nf[-1]
        m["num_features_series"] = nf
        pts = [(ti, ni) for ti, ni in zip(t, nf) if ti > 0 and ni and ni > 0]
        if len(pts) >= 4:
            xs = [math.log(p[0]) for p in pts]
            ys = [math.log(p[1] ** (-0.5)) for p in pts]   # log L,  L = N^(-1/2)
            n = len(xs); sx = sum(xs); sy = sum(ys)
            sxx = sum(x*x for x in xs); sxy = sum(x*y for x, y in zip(xs, ys))
            den = n*sxx - sx*sx
            if den:
                slope = (n*sxy - sx*sy)/den
                intercept = (sy - slope*sx)/n
                ybar = sy/n
                ss_tot = sum((y-ybar)**2 for y in ys)
                ss_res = sum((y-(slope*x+intercept))**2 for x, y in zip(xs, ys))
                r2 = 1 - ss_res/ss_tot if ss_tot > 0 else 0.0
                m["coarsening_exponent"] = round(slope, 4)   # target ~0.333
                m["coarsening_R2"]       = round(r2, 4)
    if "dt" in csv_data and csv_data["dt"]:
        m["dt_final"] = csv_data["dt"][-1]
    return m
