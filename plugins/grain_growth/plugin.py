"""
AutoMOOSE Plugin — Grain Growth
================================
Supports:
  - 2D and 3D meshes
  - Formulation: GBEvolution | LinearizedInterface
  - IC: Voronoi | Random
  - Mesh adaptivity, periodic BCs, Terminator, checkpoints
Executable: phase_field-opt
"""
import os, socket
from datetime import datetime

# ── Plugin metadata ───────────────────────────────────────────────────────
PLUGIN = {
    "label":          "Grain Growth",
    "icon":           "🌾",
    "description":    "Polycrystal grain growth — GBEvolution & LinearizedInterface, 2D/3D",
    "executable_key": "MOOSE_EXEC",
    "status":         "ready",
    "params": {
        # Simulation identity
        "run_name":         "grain_growth",
        "dim":              2,
        "formulation":      "GBEvolution",   # GBEvolution | LinearizedInterface
        "ic_type":          "Voronoi",        # Voronoi | Random
        # Mesh
        "nx": 40, "ny": 40, "nz": 20,
        "xmax": 1000.0, "ymax": 1000.0, "zmax": 1000.0,
        "uniform_refine": 2,
        "periodic_x": True, "periodic_y": True, "periodic_z": False,
        # Grains / order parameters
        "num_grains": 20,
        "op_num":     8,
        "rand_seed":  42,
        "coloring_algorithm": "jp",   # jp | bt
        # GBEvolution material
        "T":        450.0,
        "wGB":      14.0,
        "GBmob0":   2.5e-6,
        "Q":        0.23,
        "GBenergy": 0.708,
        # LinearizedInterface material
        "gbmob":       100.0,
        "gbenergy_li": 6.0,
        "gbwidth_li":  10.0,
        "gamma_asymm": 1.5,
        "bound_value": 5.0,
        # Solver
        "preconditioner":     "asm",    # asm | hypre_boomeramg
        "nl_max_its":         20,
        "nl_rel_tol":         1e-8,
        "nl_abs_tol":         1e-8,
        "l_max_its":          30,
        "l_tol":              1e-4,
        "optimal_iterations": 8,
        # Time
        "time_mode":  "end_time",   # end_time | num_steps
        "end_time":   4000.0,
        "num_steps":  500,
        "dt_start":   25.0,
        "dt_cutback": 0.5,
        "dt_growth":  1.1,
        # Mesh adaptivity
        "use_adaptivity":     True,
        "initial_adaptivity": 2,
        "refine_fraction":    0.7,
        "coarsen_fraction":   0.1,
        "max_h_level":        4,
        # GrainTracker
        "gt_threshold":    0.1,
        "gt_tracking_step": 0,        # 0 = immediate
        # Advanced outputs
        "exodus_interval":   5,
        "use_checkpoint":    False,
        "use_nemesis":       False,
        "output_halos":      False,
        "output_ghosts":     False,
        # Terminator
        "use_terminator":       False,
        "terminator_threshold": 5,
        # MPI
        "mpi": 1,
    },
    "presets": {
        # 2D
        "2D · quick":    {"dim":2,"formulation":"GBEvolution","ic_type":"Voronoi",
            "num_grains":10,"op_num":10,"nx":12,"ny":12,"uniform_refine":2,
            "end_time":4000,"dt_start":25,"use_adaptivity":True,"time_mode":"end_time",
            "periodic_x":True,"periodic_y":True},
        "2D · standard": {"dim":2,"formulation":"GBEvolution","ic_type":"Voronoi",
            "num_grains":15,"op_num":15,"nx":12,"ny":12,"uniform_refine":3,
            "end_time":4000,"dt_start":25,"use_adaptivity":True,"time_mode":"end_time",
            "periodic_x":True,"periodic_y":True},
        "2D · 100 grains":{"dim":2,"formulation":"GBEvolution","ic_type":"Voronoi",
            "num_grains":100,"op_num":8,"nx":44,"ny":44,"uniform_refine":2,
            "end_time":4000,"dt_start":20,"use_adaptivity":True,
            "preconditioner":"hypre_boomeramg","time_mode":"end_time",
            "periodic_x":True,"periodic_y":True},
        "2D · random IC": {"dim":2,"formulation":"GBEvolution","ic_type":"Random",
            "op_num":10,"nx":40,"ny":40,"uniform_refine":2,
            "end_time":4000,"dt_start":1,"use_adaptivity":True,"time_mode":"end_time",
            "periodic_x":True,"periodic_y":True},
        "2D · linearized":{"dim":2,"formulation":"LinearizedInterface","ic_type":"Voronoi",
            "num_grains":60,"op_num":8,"nx":100,"ny":100,"uniform_refine":1,
            "end_time":30,"dt_start":0.02,"use_adaptivity":False,"time_mode":"end_time",
            "periodic_x":True,"periodic_y":True,
            "preconditioner":"hypre_boomeramg"},
        # 3D
        "3D · quick":    {"dim":3,"formulation":"GBEvolution","ic_type":"Voronoi",
            "num_grains":25,"op_num":15,"nx":10,"ny":10,"nz":10,
            "xmax":1000,"ymax":1000,"zmax":1000,"uniform_refine":1,
            "end_time":4000,"dt_start":25,"use_adaptivity":False,
            "time_mode":"end_time","exodus_interval":10},
        "3D · HPC":      {"dim":3,"formulation":"GBEvolution","ic_type":"Voronoi",
            "num_grains":6000,"op_num":28,"nx":180,"ny":180,"nz":180,
            "xmax":180,"ymax":180,"zmax":180,"uniform_refine":0,
            "end_time":999999,"num_steps":500,"time_mode":"num_steps",
            "dt_start":0.0002,"use_adaptivity":False,"use_checkpoint":True,
            "use_nemesis":True,"output_halos":True,"output_ghosts":True,
            "use_terminator":True,"terminator_threshold":218,
            "exodus_interval":20,"mpi":32},
    },
    "sweepable":   ["num_grains", "T", "GBenergy", "GBmob0", "op_num"],
    "result_keys": ["grain_tracker", "dt", "DOFs"],
    "system_prompt": """You are an expert in MOOSE phase-field grain growth simulations.
Formulations:
- GBEvolution: quantitative Cu parameters (GBmob0, Q, T, wGB, GBenergy). Units: nm, ns.
- LinearizedInterface: kappa/L parsed from gbmob, gbenergy, gbwidth. Adds bound_value constraint.
IC types:
- Voronoi: PolycrystalVoronoi seeds. coloring_algorithm jp (large) or bt (num_grains=op_num).
- Random: PolycrystalRandomIC discrete — no grain_num needed, more natural initial structure.
Mesh adaptivity: uniform_refine sets initial mesh, Adaptivity block refines at GBs.
- refine_fraction 0.7-0.8, coarsen_fraction 0.05-0.1, max_h_level 2-4.
- For 3D: disable adaptivity (too expensive), use distributed parallel_type.
Preconditioners:
- asm: good for 3D, simple problems.
- hypre boomeramg: better for large 2D with adaptivity.
GrainTracker tracking_step: delay tracking until grains are established (e.g. step 20 for Random IC).
Terminator: stops run when grain_tracker < threshold. Useful for HPC to avoid wasted time.
Growth laws: d²-d₀²=kt (2D), d³-d₀³=kt (3D). Parabolic fit R² should be > 0.99 for good data.
Be concise and specific.""",
}


def make_run_dir_name(params: dict, run_id: str) -> str:
    """Human-readable run directory name with metadata."""
    ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
    dim  = f"{params.get('dim',2)}D"
    ic   = params.get("ic_type","Voronoi")
    form = "GBEvo" if params.get("formulation","GBEvolution")=="GBEvolution" else "LinIF"
    nm   = params.get("run_name","grain_growth").replace(" ","_")
    nx, ny = params.get("nx",40), params.get("ny",40)
    mesh = f"{nx}x{ny}x{params.get('nz',1)}" if int(params.get("dim",2))==3 else f"{nx}x{ny}"
    ng   = params.get("num_grains","?")
    T    = params.get("T","?")
    return f"{ts}__{nm}__{dim}_{ic}_{form}__T{T}_n{ng}_{mesh}"


def make_metadata(params: dict, run_id: str, moose_exec: str) -> dict:
    return {
        "run_id":      run_id,
        "created":     datetime.now().isoformat(),
        "hostname":    socket.gethostname(),
        "plugin":      "grain_growth",
        "formulation": params.get("formulation", "GBEvolution"),
        "ic_type":     params.get("ic_type", "Voronoi"),
        "dim":         params.get("dim", 2),
        "moose_exec":  moose_exec,
        "params":      params,
        "status":      "pending",
        "duration_s":  None,
    }


def _periodic_block(px, py, pz, dim):
    dirs = []
    if px: dirs.append("x")
    if py: dirs.append("y")
    if dim==3 and pz: dirs.append("z")
    if not dirs: return ""
    return f"""
[BCs]
  [Periodic]
    [All]
      auto_direction = '{" ".join(dirs)}'
    []
  []
[]
"""


def _precond(prec):
    if prec == "hypre_boomeramg":
        return ("petsc_options_iname = '-pc_type -pc_hypre_type -ksp_gmres_restart -mat_mffd_type'\n"
                "  petsc_options_value = 'hypre    boomeramg      101                ds'")
    return ("petsc_options_iname = '-pc_type'\n"
            "  petsc_options_value = 'asm'")


def _adaptivity_block(p):
    if not p.get("use_adaptivity", True): return ""
    ia = p.get("initial_adaptivity", 2)
    rf = p.get("refine_fraction", 0.7)
    cf = p.get("coarsen_fraction", 0.1)
    mh = p.get("max_h_level", 4)
    return f"""
  [Adaptivity]
    initial_adaptivity = {ia}
    refine_fraction    = {rf}
    coarsen_fraction   = {cf}
    max_h_level        = {mh}
  []"""


def _terminator_block(p):
    if not p.get("use_terminator", False): return ""
    thr = p.get("terminator_threshold", 5)
    return f"""
  [term]
    type       = Terminator
    expression = 'grain_tracker < {thr}'
  []"""


def _outputs_block(p, run_name):
    parts = [f"  file_base = {run_name}", "  csv       = true"]
    if p.get("use_nemesis", False):
        parts.append("  nemesis = true")
    if p.get("use_checkpoint", False):
        parts.append("  checkpoint = true")
    parts.append("  [console]\n    type = Console\n  []")
    if p.get("use_nemesis", False):
        parts.append("  [pg]\n    type       = PerfGraphOutput\n    execute_on = 'initial final'\n    level      = 2\n  []")
    return "[Outputs]\n" + "\n".join(parts) + "\n[]"


def _halo_aux_vars(p):
    if not p.get("output_halos", False): return ""
    return """
  [halos]
    order  = CONSTANT
    family = MONOMIAL
  []
  [ghost_elements]
    order  = CONSTANT
    family = MONOMIAL
  []"""


def _halo_aux_kernels(p):
    if not p.get("output_halos", False): return ""
    return """
  [halos]
    type          = FeatureFloodCountAux
    variable      = halos
    field_display = HALOS
    execute_on    = 'initial timestep_end'
    flood_counter = grain_tracker
  []
  [ghost_elements]
    type          = FeatureFloodCountAux
    variable      = ghost_elements
    field_display = GHOSTED_ENTITIES
    execute_on    = 'initial timestep_end'
    flood_counter = grain_tracker
  []"""


def generate_input(
    run_name="grain_growth", dim=2,
    formulation="GBEvolution", ic_type="Voronoi",
    nx=40, ny=40, nz=20,
    xmax=1000.0, ymax=1000.0, zmax=1000.0,
    uniform_refine=2,
    periodic_x=True, periodic_y=True, periodic_z=False,
    num_grains=20, op_num=8, rand_seed=42, coloring_algorithm="jp",
    # GBEvolution
    T=450.0, wGB=14.0, GBmob0=2.5e-6, Q=0.23, GBenergy=0.708,
    # LinearizedInterface
    gbmob=100.0, gbenergy_li=6.0, gbwidth_li=10.0, gamma_asymm=1.5, bound_value=5.0,
    # Solver
    preconditioner="asm", nl_max_its=20, nl_rel_tol=1e-8, nl_abs_tol=1e-8,
    l_max_its=30, l_tol=1e-4, optimal_iterations=8,
    # Time
    time_mode="end_time", end_time=4000.0, num_steps=500, dt_start=25.0,
    dt_cutback=0.5, dt_growth=1.1,
    # Adaptivity
    use_adaptivity=True, initial_adaptivity=2,
    refine_fraction=0.7, coarsen_fraction=0.1, max_h_level=4,
    # GrainTracker
    gt_threshold=0.1, gt_tracking_step=0,
    # Outputs
    exodus_interval=5, use_checkpoint=False, use_nemesis=False,
    output_halos=False, output_ghosts=False,
    # Terminator
    use_terminator=False, terminator_threshold=5,
    **kwargs,
) -> str:
    dim  = int(dim)
    is3d = dim == 3
    p    = locals()   # pass to helper functions

    dim_label  = "3D" if is3d else "2D"
    mesh_label = f"{nx}×{ny}×{nz}" if is3d else f"{nx}×{ny}"
    ts         = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # ── Mesh ──────────────────────────────────────────────────────────────
    par_type = "distributed" if is3d else "replicated"
    if is3d:
        mesh = f"""[Mesh]
  type           = GeneratedMesh
  dim            = 3
  nx             = {nx}
  ny             = {ny}
  nz             = {nz}
  xmax           = {xmax}
  ymax           = {ymax}
  zmax           = {zmax}
  elem_type      = HEX8
  uniform_refine = {uniform_refine}
  parallel_type  = {par_type}
[]"""
    else:
        mesh = f"""[Mesh]
  type           = GeneratedMesh
  dim            = 2
  nx             = {nx}
  ny             = {ny}
  xmin           = 0
  xmax           = {xmax}
  ymin           = 0
  ymax           = {ymax}
  elem_type      = QUAD4
  uniform_refine = {uniform_refine}
  parallel_type  = {par_type}
[]"""

    # ── GlobalParams ──────────────────────────────────────────────────────
    if formulation == "LinearizedInterface":
        global_params = f"""[GlobalParams]
  bound_value   = {bound_value}
  op_num        = {op_num}
  var_name_base = phi
[]"""
    else:
        global_params = f"""[GlobalParams]
  op_num        = {op_num}
  var_name_base = gr
[]"""

    # ── IC ────────────────────────────────────────────────────────────────
    if ic_type == "Random":
        ic_block = """[ICs]
  [PolycrystalICs]
    [PolycrystalRandomIC]
      random_type = discrete
    []
  []
[]"""
        ic_uo_ref = ""
    else:
        ic_uo_ref = "voronoi"
        ic_block = f"""[ICs]
  [PolycrystalICs]
    [PolycrystalColoringIC]
      polycrystal_ic_uo = voronoi
      {"nonlinear_preconditioning = true" if formulation=="LinearizedInterface" else ""}
    []
  []
[]"""

    # ── UserObjects ───────────────────────────────────────────────────────
    voronoi_block = "" if ic_type=="Random" else f"""  [voronoi]
    type      = PolycrystalVoronoi
    grain_num = {num_grains}
    rand_seed = {rand_seed}
    {"int_width = 10" if formulation=="LinearizedInterface" else f"int_width = 7"}
  []"""
    gt_delay = f"\n    tracking_step = {gt_tracking_step}" if gt_tracking_step > 0 else ""
    gt_uo = f"""  [grain_tracker]
    type              = GrainTracker
    threshold         = {gt_threshold}
    compute_halo_maps = true{gt_delay}
    {"polycrystal_ic_uo = voronoi" if ic_type!="Random" else ""}
  []"""
    term_uo = _terminator_block(p)
    user_objects = f"""[UserObjects]
{voronoi_block}
{gt_uo}{term_uo}
[]"""

    # ── Variables / Kernels ───────────────────────────────────────────────
    if formulation == "LinearizedInterface":
        variables_kernels = """[Modules]
  [PhaseField]
    [GrainGrowthLinearizedInterface]
      op_name_base = gr
      mobility     = L
      kappa        = kappa_op
    []
  []
[]"""
    else:
        variables_kernels = """[Modules]
  [PhaseField]
    [GrainGrowth]
    []
  []
[]"""

    # ── AuxVariables ──────────────────────────────────────────────────────
    aux_vars = f"""[AuxVariables]
  [bnds]
    order  = FIRST
    family = LAGRANGE
  []
  [unique_grains]
    order  = CONSTANT
    family = MONOMIAL
  []
  [var_indices]
    order  = CONSTANT
    family = MONOMIAL
  []{_halo_aux_vars(p)}
[]"""

    aux_kernels = f"""[AuxKernels]
  [bnds_aux]
    type       = BndsCalcAux
    variable   = bnds
    execute_on = 'initial timestep_end'
  []
  [unique_grains]
    type          = FeatureFloodCountAux
    variable      = unique_grains
    field_display = UNIQUE_REGION
    execute_on    = 'initial timestep_end'
    flood_counter = grain_tracker
  []
  [var_indices]
    type          = FeatureFloodCountAux
    variable      = var_indices
    field_display = VARIABLE_COLORING
    execute_on    = 'initial timestep_end'
    flood_counter = grain_tracker
  []{_halo_aux_kernels(p)}
[]"""

    # ── Materials ─────────────────────────────────────────────────────────
    if formulation == "LinearizedInterface":
        materials = f"""[Materials]
  [properties]
    type        = GenericConstantMaterial
    prop_names  = 'gbmob gbenergy gbwidth gamma_asymm'
    prop_values = '{gbmob} {gbenergy_li} {gbwidth_li} {gamma_asymm}'
  []
  [kappa_op]
    type                     = ParsedMaterial
    material_property_names  = 'gbenergy gbwidth'
    property_name            = kappa_op
    expression               = '3/4*gbenergy*gbwidth'
  []
  [L]
    type                     = ParsedMaterial
    material_property_names  = 'gbmob gbwidth'
    property_name            = L
    expression               = '4/3*gbmob/gbwidth'
  []
  [mu]
    type                     = ParsedMaterial
    material_property_names  = 'gbenergy gbwidth'
    property_name            = mu
    expression               = '6*gbenergy/gbwidth'
  []
[]"""
    else:
        materials = f"""[Materials]
  [CuGrGr]
    type     = GBEvolution
    T        = {T}
    wGB      = {wGB}
    GBmob0   = {GBmob0}
    Q        = {Q}
    GBenergy = {GBenergy}
  []
[]"""

    # ── Postprocessors ────────────────────────────────────────────────────
    postprocessors = """[Postprocessors]
  [dt]
    type = TimestepSize
  []
  [n_elements]
    type       = NumElements
    execute_on = timestep_end
  []
  [DOFs]
    type = NumDOFs
  []
[]"""

    # ── Executioner ───────────────────────────────────────────────────────
    time_ctrl = (f"  end_time  = {end_time}" if time_mode=="end_time"
                 else f"  num_steps = {num_steps}")
    prec_str  = _precond(preconditioner)
    adapt_str = _adaptivity_block(p)
    if formulation == "LinearizedInterface":
        solver_opts = ("  petsc_options_iname = '-pc_type -pc_hypre_type -snes_type'\n"
                       "  petsc_options_value = 'hypre    boomeramg      vinewtonrsls'")
    else:
        solver_opts = f"  {prec_str}"

    executioner = f"""[Executioner]
  type       = Transient
  scheme     = bdf2
  solve_type = PJFNK
{solver_opts}
  l_tol      = {l_tol}
  l_max_its  = {l_max_its}
  nl_max_its = {nl_max_its}
  nl_rel_tol = {nl_rel_tol}
  start_time = 0.0
{time_ctrl}
  [TimeStepper]
    type               = IterationAdaptiveDT
    cutback_factor     = {dt_cutback}
    dt                 = {dt_start}
    growth_factor      = {dt_growth}
    optimal_iterations = {optimal_iterations}
  []{adapt_str}
[]"""

    periodic = _periodic_block(periodic_x, periodic_y, periodic_z, dim)
    outputs  = _outputs_block(p, run_name)

    return f"""# AutoMOOSE — Grain Growth ({dim_label})
# Generated  : {ts}
# Run        : {run_name}
# Formulation: {formulation}
# IC Type    : {ic_type}
# Mesh       : {mesh_label}  uniform_refine={uniform_refine}
# Grains     : {num_grains if ic_type!="Random" else "random"}  op_num={op_num}
{mesh}
{global_params}
{user_objects}
{ic_block}
{variables_kernels}
{aux_vars}
{aux_kernels}
{periodic}
{materials}
{postprocessors}
{executioner}
{outputs}
"""


def parse_results(csv_data: dict) -> dict:
    import math
    m = {}
    if "grain_tracker" in csv_data and csv_data["grain_tracker"]:
        g0 = csv_data["grain_tracker"][0]
        gf = csv_data["grain_tracker"][-1]
        m["grains_initial"]       = g0
        m["grains_final"]         = gf
        m["grain_reduction_pct"]  = round(100*(1 - gf/max(g0,1)), 1)
        m["grain_tracker_series"] = csv_data["grain_tracker"]
    if "dt" in csv_data and csv_data["dt"]:
        m["dt_final"]  = csv_data["dt"][-1]
        m["dt_series"] = csv_data["dt"]
    if "time" in csv_data and csv_data["time"]:
        t = csv_data["time"]
        m["total_timesteps"] = len(t)
        m["final_time"]      = t[-1]
        m["time_series"]     = t
        # parabolic fit d²~t (2D) using grain_tracker as proxy for 1/d²
        if "grain_tracker" in csv_data and len(t) > 4:
            try:
                g = csv_data["grain_tracker"]
                d2 = [1.0/max(gi,1)**2 for gi in g]
                n  = len(t)
                sx  = sum(t); sy  = sum(d2)
                sxy = sum(t[i]*d2[i] for i in range(n))
                sx2 = sum(ti**2 for ti in t)
                slope = (n*sxy - sx*sy)/(n*sx2 - sx**2 + 1e-30)
                intercept = (sy - slope*sx)/n
                ss_res = sum((d2[i]-slope*t[i]-intercept)**2 for i in range(n))
                ss_tot = sum((d2[i]-sy/n)**2 for i in range(n))
                m["parabolic_R2"]    = round(1 - ss_res/max(ss_tot,1e-30), 4)
                m["parabolic_k"]     = slope
                m["d2_series"]       = d2
            except: pass
    if "DOFs" in csv_data and csv_data["DOFs"]:
        m["dofs_final"]  = csv_data["DOFs"][-1]
        m["dofs_series"] = csv_data["DOFs"]
    return m
