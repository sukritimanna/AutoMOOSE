# AutoMOOSE — Grain Growth (2D)
# Generated  : 2026-06-23 22:20:30
# Run        : grain_growth
# Formulation: GBEvolution
# IC Type    : Voronoi
# Mesh       : 24×24  uniform_refine=1
# Grains     : 30  op_num=8
[Mesh]
  type           = GeneratedMesh
  dim            = 2
  nx             = 24
  ny             = 24
  xmin           = 0
  xmax           = 1000.0
  ymin           = 0
  ymax           = 1000.0
  elem_type      = QUAD4
  uniform_refine = 1
  parallel_type  = replicated
[]
[GlobalParams]
  op_num        = 8
  var_name_base = gr
[]
[UserObjects]
  [voronoi]
    type      = PolycrystalVoronoi
    grain_num = 30
    rand_seed = 7
    int_width = 7
  []
  [grain_tracker]
    type              = GrainTracker
    threshold         = 0.1
    compute_halo_maps = true
    polycrystal_ic_uo = voronoi
  []
[]
[ICs]
  [PolycrystalICs]
    [PolycrystalColoringIC]
      polycrystal_ic_uo = voronoi
      
    []
  []
[]
[Modules]
  [PhaseField]
    [GrainGrowth]
    []
  []
[]
[AuxVariables]
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
  []
[]
[AuxKernels]
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
  []
[]

[BCs]
  [Periodic]
    [All]
      auto_direction = 'x y'
    []
  []
[]

[Materials]
  [CuGrGr]
    type     = GBEvolution
    T        = 500
    wGB      = 14.0
    GBmob0   = 2.5e-06
    Q        = 0.23
    GBenergy = 0.708
  []
[]
[Postprocessors]
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
[]
[Executioner]
  type       = Transient
  scheme     = bdf2
  solve_type = PJFNK
  petsc_options_iname = '-pc_type'
  petsc_options_value = 'asm'
  l_tol      = 0.0001
  l_max_its  = 30
  nl_max_its = 20
  nl_rel_tol = 1e-08
  start_time = 0.0
  end_time  = 500.0
  [TimeStepper]
    type               = IterationAdaptiveDT
    cutback_factor     = 0.5
    dt                 = 25.0
    growth_factor      = 1.1
    optimal_iterations = 8
  []
  [Adaptivity]
    initial_adaptivity = 2
    refine_fraction    = 0.7
    coarsen_fraction   = 0.1
    max_h_level        = 4
  []
[]
[Outputs]
  file_base = grain_growth
  csv       = true
  [console]
    type = Console
  []
[]
