# Execution Backends

AutoMOOSE runs simulations on one of two **execution backends**, selected by a
single configuration value. The agent pipeline (`f1`–`f6`) is identical either
way; only *where* MOOSE executes changes.

```{list-table}
:header-rows: 1
:widths: 30 70

* - Setting
  - Behavior
* - `EXECUTION_BACKEND=local`
  - Run MOOSE on this machine (laptop / workstation) via a subprocess.
* - `EXECUTION_BACKEND=hpc`
  - Stage files to NERSC Perlmutter and run via SLURM, then fetch results back.
```

```{note}
The HPC backend requires the one-time setup in
[HPC execution](hpc-execution) below — in particular a working
`sshproxy` certificate. Verify the connection before launching production jobs.
```

---

(local-execution)=
## 1. Local execution

Use this for development, small 2D cases, and validation runs.

### Prerequisites

- A working MOOSE build (the `phase_field-opt` executable).
- The `automoose` conda environment (Python 3.11).
- MPI available locally (`mpiexec` on `PATH`) — optional; single-rank works too.

### Configure `config.env`

```bash
EXECUTION_BACKEND=local
MOOSE_EXEC=/path/to/phase_field-opt
RUNS_DIR=./runs
LLM_PROVIDER=anthropic
LLM_MODEL=claude-sonnet-4-6      # or any configured backend
```

### Run

```bash
conda deactivate; conda deactivate; conda activate automoose
uvicorn automoose.server:app --host 127.0.0.1 --port 8000

# in another terminal, drive the pipeline:
python -m automoose.agents.orchestrator --physics grain_growth \
    --params '{"T":800,"num_grains":50}'
```

Results land in `./runs/<run_dir>/` with the CSV, log, and provenance JSON.
The Skeptic agent (`f6`) falsifies each completed run automatically.

### What "local" does internally

`LocalBackend` writes the `.i` file into a timestamped run directory and
launches `mpiexec -n N phase_field-opt -i sim.i` as a subprocess, polling the
process to completion. No SSH, no scheduler.

---

(hpc-execution)=
## 2. HPC execution (NERSC Perlmutter)

Use this for 3D cases, large meshes, parameter sweeps, and production runs.
`HPCBackend` stages files to Perlmutter scratch, submits a SLURM job, polls it,
and copies results back.

### 2.1 NERSC prerequisites

1. An active NERSC account with the relevant allocation (e.g. `m3794`).
2. The MOOSE app built on Perlmutter, e.g.
   `/global/homes/s/<user>/projects/phase_field_app/phase_field_app-opt`.
3. A scratch working area, e.g. `/pscratch/sd/s/<user>/autoMOOSE`.
4. Python available on the compute side (`module load python` or a conda env)
   for the in-job analysis step.

### 2.2 Authentication (`sshproxy`)

Perlmutter requires multi-factor authentication for SSH, which a headless
service cannot perform interactively. NERSC's supported solution is
**`sshproxy`**: you authenticate once per day and receive a short-lived
(24-hour) SSH certificate; all subsequent SSH/SCP within that window are
non-interactive.

```{warning}
HPC runs only work while the `sshproxy` certificate is valid (24 h). For
multi-day campaigns, re-authenticate each morning. AutoMOOSE surfaces a clear
error ("SSH auth failed — run sshproxy.sh") rather than hanging if the
certificate has lapsed.
```

Set up `sshproxy` once:

```bash
curl -O https://raw.githubusercontent.com/NERSC/sshproxy/master/sshproxy.sh
chmod +x sshproxy.sh

# each day (or when the cert expires):
./sshproxy.sh -u <nersc_user>
# enter NERSC password + OTP when prompted
# -> writes a 24 h cert to ~/.ssh/nersc and ~/.ssh/nersc-cert.pub
```

Configure `~/.ssh/config`:

```text
Host perlmutter perlmutter.nersc.gov
    HostName perlmutter.nersc.gov
    User <nersc_user>
    IdentityFile ~/.ssh/nersc
    IdentitiesOnly yes
```

Verify it works non-interactively:

```bash
ssh perlmutter 'echo OK; squeue --me | head'
```

If that runs without prompting for a password, `HPCBackend` will work. If it
prompts, re-run `sshproxy.sh`.

### 2.3 Configure `config.env` for HPC

```bash
EXECUTION_BACKEND=hpc

# SSH / transfer
HPC_HOST=perlmutter.nersc.gov
HPC_USER=<nersc_user>
HPC_SSH_ALIAS=perlmutter          # the Host alias from ~/.ssh/config
HPC_SCRATCH=/pscratch/sd/s/<user>/autoMOOSE

# MOOSE on the HPC side
HPC_MOOSE_APP=/global/homes/s/<user>/projects/phase_field_app/phase_field_app-opt

# SLURM directives
HPC_ACCOUNT=m3794
HPC_CONSTRAINT=cpu
HPC_QOS=premium
HPC_NODES=1
HPC_NTASKS=32
HPC_WALLTIME=12:00:00

# how to obtain python on the compute node for in-job analysis
HPC_PYTHON_SETUP="module load python"   # or "conda activate automoose"
```

### 2.4 First-time directory check

```bash
ssh perlmutter '
  mkdir -p /pscratch/sd/s/<user>/autoMOOSE
  ls -d /global/homes/s/<user>/projects/phase_field_app/phase_field_app-opt \
    && echo "MOOSE app OK" || echo "MOOSE app MISSING"
'
```

---

## 3. Running an HPC job

Once the setup above is complete, running on HPC is the **same command** as
local; only the config differs:

```bash
# config.env has EXECUTION_BACKEND=hpc
python -m automoose.agents.orchestrator --physics spinodal \
    --params '{"fe_mode":"FeCr","c0":0.4677,"num_steps":50000}' \
    --backend-name "Claude"
```

### The HPC lifecycle

1. **Generate** — `f2` renders the `.i` file locally (no HPC needed).
2. **Stage** — `HPCBackend` copies the run directory to
   `$HPC_SCRATCH/<run_id>/` and writes a generated `submit.sh` from the SLURM
   template, filled with the configured directives.
3. **Submit** — `ssh perlmutter 'cd <dir> && sbatch submit.sh'`; captures the
   SLURM job ID.
4. **Poll** — `ssh perlmutter 'sacct -j <jobid> ...'` every *N* seconds until
   the state is `COMPLETED` / `FAILED` / `TIMEOUT` / `CANCELLED`.
5. **Fetch** — on completion, copy the results (CSV, `.e`, log, `results/`)
   back into the local run directory.
6. **Falsify** — the `f6` Skeptic runs locally on the fetched results, exactly
   as for local runs.

### Monitoring

```bash
ssh perlmutter 'squeue --me'
ssh perlmutter 'tail -f /pscratch/sd/s/<user>/autoMOOSE/<run_id>/slurm-*.out'
```

---

## 4. Switching between local and HPC

The switch is one line in `config.env`:

```bash
EXECUTION_BACKEND=local   # development, small cases
EXECUTION_BACKEND=hpc     # production, large/3D/sweeps
```

Nothing else changes — same prompts, same pipeline, same Skeptic. Keep two
config files and select per session:

```bash
cp config.local.env config.env    # local
cp config.hpc.env   config.env    # HPC
```

### Decision guide

```{list-table}
:header-rows: 1
:widths: 50 50

* - Use **local** when…
  - Use **HPC** when…
* - 2D, small meshes (≤ 100²)
  - 3D, large meshes
* - Developing / debugging a plugin
  - Production parameter sweeps
* - Quick validation (invariants hold at any size)
  - Long `num_steps` / `end_time` runs
* - No NERSC certificate handy
  - Many concurrent tasks (benchmark)
```

---

## 5. Troubleshooting

```{list-table}
:header-rows: 1
:widths: 30 35 35

* - Symptom
  - Cause
  - Fix
* - `SSH auth failed` / hangs on connect
  - sshproxy cert expired
  - re-run `./sshproxy.sh -u <user>`
* - `sbatch: command not found`
  - wrong host / not on Perlmutter
  - check `HPC_SSH_ALIAS` resolves to a login node
* - Job submits but no results fetched
  - output names differ
  - generated `submit.sh` auto-detects `*_out.csv`; check `results/` populated
* - `MOOSE app MISSING`
  - wrong `HPC_MOOSE_APP` path
  - verify via `ssh perlmutter 'ls <path>'`
* - Local run: `mpiexec not found`
  - no MPI locally
  - single-rank still works; or install MPI
* - Job stuck `PENDING`
  - queue wait
  - normal; `premium` QOS speeds it; check `squeue --me`
```
