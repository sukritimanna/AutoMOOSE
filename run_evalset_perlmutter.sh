#!/bin/bash -l
# =============================================================================
# AutoMOOSE eval-set batch run on Perlmutter (semi-automated W6)
# Loops over all staged task dirs, runs each MOOSE input, writes status to
# metadata.json. Adapted from the user's GrainGrowthDB-v2 debug script.
# =============================================================================
#SBATCH -A m5152
#SBATCH -C cpu
#SBATCH -q regular
#SBATCH -N 2
#SBATCH -t 02:00:00
#SBATCH -J automoose_evalset
#SBATCH -o /pscratch/sd/s/smanna/automoose_evalset/logs/eval_%j.out
#SBATCH -e /pscratch/sd/s/smanna/automoose_evalset/logs/eval_%j.err
#SBATCH --mail-type=END,FAIL
#SBATCH --mail-user=sukriti.manna@gmail.com

module load python
export OMP_NUM_THREADS=1
export OMP_PLACES=cores
export OMP_PROC_BIND=spread

MOOSE_APP="/global/homes/s/smanna/projects/phase_field_app/phase_field_app-opt"
STAGE="/pscratch/sd/s/smanna/automoose_evalset/staging"
mkdir -p /pscratch/sd/s/smanna/automoose_evalset/logs

echo "=== AutoMOOSE eval-set batch | Job $SLURM_JOB_ID | $(date -u) ==="

launch_one () {
  local d="$1"
  (
    cd "$d" || exit 2
    SIM_ID=$(basename "$d")
    INPUT="${SIM_ID}.i"
    META="metadata.json"
    [ -f "$INPUT" ] || { echo "SKIP (no .i): $SIM_ID" >&2; exit 0; }

    python3 -c "
import json,pathlib,os
p=pathlib.Path('$META')
m=json.loads(p.read_text()) if p.exists() else {}
m['status']='running'; m['slurm_job_id']=os.environ.get('SLURM_JOB_ID','')
p.write_text(json.dumps(m,indent=2))"

    START=$(date +%s)
    echo "START $(date -u +%H:%M:%S) $SIM_ID"
    srun --exclusive -N 1 --ntasks=16 --ntasks-per-node=16 --cpus-per-task=1 \
         --cpu-bind=cores "$MOOSE_APP" -i "$INPUT" > "${SIM_ID}.log" 2>&1
    rc=$?
    WALL=$(( $(date +%s) - START ))
    echo "END   $(date -u +%H:%M:%S) $SIM_ID rc=$rc wall=${WALL}s"

    python3 -c "
import json,pathlib
from datetime import datetime,timezone
p=pathlib.Path('$META'); m=json.loads(p.read_text())
m['completed_at']=datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
m['wall_time_s']=$WALL
cp=pathlib.Path('${SIM_ID}.csv')
if cp.exists(): m['csv_size_kb']=round(cp.stat().st_size/1e3,2)
m['status']='completed' if $rc==0 else 'failed'
m['error_msg']=None if $rc==0 else 'exit code $rc'
p.write_text(json.dumps(m,indent=2))"
    exit $rc
  ) &
}

# ── launch all staged tasks, throttled to N concurrent ──────────────────────
MAXJOBS=8     # concurrent sims (2 nodes x ~4 each; tune to taste)
count=0
for d in "$STAGE"/GG*/ ; do
  launch_one "$d"
  count=$((count+1))
  if (( count % MAXJOBS == 0 )); then wait; fi   # drain a batch before next
done
wait
echo "=== All tasks done | $(date -u) ==="

# ── summary ─────────────────────────────────────────────────────────────────
python3 -c "
import json,pathlib,glob
rows=[json.loads(pathlib.Path(f).read_text()) for f in glob.glob('$STAGE/GG*/metadata.json')]
ok=sum(r.get('status')=='completed' for r in rows)
print(f'COMPLETED {ok}/{len(rows)}')
for r in sorted(rows,key=lambda x:x['sim_id']):
    print(f\"  {r['sim_id']:<6} {r.get('status'):<10} wall={r.get('wall_time_s','?')}s\")"
exit 0
