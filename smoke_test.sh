#!/usr/bin/env bash
# =============================================================================
# AutoMOOSE end-to-end smoke test  (reproducibility check)
# -----------------------------------------------------------------------------
# Run from the repository root, with your normal environment active
# (the one where `python -c "import automoose"` works):
#
#     bash smoke_test.sh
#
# What it does, in order:
#   Stage 0  Preflight   : config.env, MOOSE_EXEC, LLM config, package import
#   Stage A  Offline     : the 22-test suite (no MOOSE, no API key)
#   Stage B  Live MOOSE  : deterministic grain-growth run via the REST backend
#                          (proves MOOSE + plugin + backend, no LLM needed)
#   Stage C  Full agentic: headless orchestrator f1..f6 (adds the LLM agents +
#                          screen / falsify / interpret)
#
# Stages B and C are skipped (not failed) if MOOSE_EXEC / the LLM are not
# configured, so you always get a useful result. Nothing is written outside
# ./runs and a couple of temp files in ./ (cleaned up).
#
# At the end it prints a block between  >>>>> PASTE THIS BACK >>>>>  markers.
# Copy that whole block back. It contains no secrets (only booleans / names).
# =============================================================================
set -uo pipefail

# ---- config knobs (safe defaults; override via env if you like) -------------
PORT="${API_PORT:-8000}"
POLL_TIMEOUT="${SMOKE_TIMEOUT:-900}"     # max seconds to wait for a run
POLL_EVERY=3
# tiny, fast grain-growth job (correct key is num_grains, not n_grains):
SMOKE_PARAMS='{"dim":2,"nx":16,"ny":16,"uniform_refine":0,"num_grains":8,"op_num":8,"xmax":400,"ymax":400,"time_mode":"num_steps","num_steps":20,"rand_seed":42,"T":450}'

PY="$(command -v python3 || command -v python)"
CURL="$(command -v curl || true)"
TS="$(date +%Y%m%d_%H%M%S)"
OUT=".smoke_${TS}"; mkdir -p "$OUT"
BACKEND_PID=""; STARTED_BACKEND="no"

# result accumulators
R_OS="$(uname -srm 2>/dev/null)"
R_PYV="$($PY -V 2>&1)"
R_HEAD="$(git rev-parse --short HEAD 2>/dev/null || echo '?')"
R_DIRTY="$(test -n "$(git status --porcelain 2>/dev/null)" && echo yes || echo no)"
R_A="not-run"; R_B="not-run"; R_C="not-run"
R_MOOSE="unset"; R_MOOSEFOUND="no"; R_LLM="no"; R_MODEL=""
R_BMETRICS=""; R_BRUNID=""; R_CJSON=""; R_NOTES=""

say(){ printf '\n\033[1m== %s ==\033[0m\n' "$*"; }
note(){ R_NOTES="${R_NOTES}$1; "; printf '   %s\n' "$1"; }

cleanup(){
  if [ "$STARTED_BACKEND" = "yes" ] && [ -n "$BACKEND_PID" ]; then
    kill "$BACKEND_PID" >/dev/null 2>&1 || true
    wait "$BACKEND_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT

# =============================================================================
say "Stage 0  Preflight"

if [ ! -f pyproject.toml ] || [ ! -d automoose ]; then
  echo "ERROR: run this from the repository root (where ./automoose lives)."; exit 2
fi

# load config.env the same way start.sh does
if [ -f config.env ]; then
  set -a; . ./config.env; set +a
  echo "   loaded config.env"
else
  note "config.env not found (using current environment only)"
fi

# MOOSE executable
if [ -n "${MOOSE_EXEC:-}" ]; then
  R_MOOSE="$(basename "$MOOSE_EXEC")"
  if [ -x "${MOOSE_EXEC}" ]; then echo "   MOOSE_EXEC ok: $MOOSE_EXEC";
  else note "MOOSE_EXEC set but not executable/found: $MOOSE_EXEC"; fi
else
  note "MOOSE_EXEC not set -> live stages (B,C) will be skipped"
fi

# LLM configured?  (accept the common possibilities; only record booleans)
if [ -n "${ANTHROPIC_API_KEY:-}" ] || [ -n "${OPENAI_API_KEY:-}" ] \
   || [ -n "${LLM_ENDPOINT:-}" ] || [ -n "${LLM_BASE_URL:-}" ] \
   || [ -n "${OPENAI_BASE_URL:-}" ]; then R_LLM="yes"; fi
R_MODEL="${LLM_MODEL:-${MODEL:-model}}"
echo "   LLM configured: $R_LLM   model-name: $R_MODEL"

# package import (no key needed)
if $PY -c "import automoose" 2>/dev/null; then echo "   import automoose: ok";
else echo "ERROR: cannot import automoose in this environment."; exit 2; fi

# =============================================================================
say "Stage A  Offline test suite (pytest tests/)"
if $PY -m pytest tests/ > "$OUT/pytest.txt" 2>&1; then
  _np="$(grep -oE '[0-9]+ passed' "$OUT/pytest.txt" | tail -1)"
  R_A="pass (${_np:-all tests})"
  echo "   $R_A"
else
  R_A="FAIL"; echo "   FAIL — see $OUT/pytest.txt"; tail -15 "$OUT/pytest.txt"
fi

# ---- decide whether to attempt live stages ----------------------------------
if [ -z "${MOOSE_EXEC:-}" ] || [ ! -x "${MOOSE_EXEC:-/nonexistent}" ]; then
  R_B="skipped (no MOOSE_EXEC)"; R_C="skipped (no MOOSE_EXEC)"
elif [ -z "$CURL" ]; then
  R_B="skipped (no curl)"; R_C="skipped (no curl)"
else
  # ===========================================================================
  say "Stage B  Live MOOSE run via REST backend"

  # reuse an already-running backend if present, else start one
  if $CURL -sf "http://localhost:${PORT}/health" >/dev/null 2>&1; then
    echo "   backend already up on :${PORT}"
  else
    echo "   starting backend: uvicorn automoose.server:app --port ${PORT}"
    $PY -m uvicorn automoose.server:app --port "${PORT}" --log-level warning \
        > "$OUT/backend.log" 2>&1 &
    BACKEND_PID=$!; STARTED_BACKEND="yes"
    for _ in $(seq 1 30); do
      $CURL -sf "http://localhost:${PORT}/health" >/dev/null 2>&1 && break
      sleep 1
    done
  fi

  HEALTH="$($CURL -sf "http://localhost:${PORT}/health" 2>/dev/null || true)"
  if [ -z "$HEALTH" ]; then
    R_B="FAIL (backend did not come up)"; note "backend health never returned — see $OUT/backend.log"
  else
    R_MOOSEFOUND="$(printf '%s' "$HEALTH" | $PY -c 'import sys,json;d=json.load(sys.stdin);e=d.get("executables",{});print("yes" if any(v.get("found") for v in e.values()) else "no")' 2>/dev/null || echo '?')"
    echo "   /health ok — MOOSE executable found: $R_MOOSEFOUND"
    if [ "$R_MOOSEFOUND" != "yes" ]; then
      R_B="FAIL (MOOSE_EXEC not found by backend)"
      note "backend /health reports the MOOSE executable is not found"
    else
      RESP="$($CURL -sf -X POST "http://localhost:${PORT}/run" \
             -H 'Content-Type: application/json' \
             -d "{\"physics\":\"grain_growth\",\"params\":${SMOKE_PARAMS}}" 2>/dev/null || true)"
      R_BRUNID="$(printf '%s' "$RESP" | $PY -c 'import sys,json;print(json.load(sys.stdin).get("run_id",""))' 2>/dev/null || true)"
      if [ -z "$R_BRUNID" ]; then
        R_B="FAIL (/run did not return a run_id)"; note "/run response: $RESP"
      else
        echo "   run_id=$R_BRUNID  polling (timeout ${POLL_TIMEOUT}s)..."
        ST="pending"; T0=$(date +%s)
        while :; do
          REC="$($CURL -sf "http://localhost:${PORT}/runs/${R_BRUNID}" 2>/dev/null || true)"
          ST="$(printf '%s' "$REC" | $PY -c 'import sys,json;print(json.load(sys.stdin).get("status",""))' 2>/dev/null || echo '')"
          case "$ST" in done|failed|stopped) break;; esac
          [ $(( $(date +%s) - T0 )) -ge "$POLL_TIMEOUT" ] && { ST="timeout"; break; }
          sleep "$POLL_EVERY"
        done
        echo "   terminal status: $ST"
        if [ "$ST" = "done" ]; then
          R_BMETRICS="$(printf '%s' "$REC" | $PY -c 'import sys,json;m=json.load(sys.stdin).get("metrics",{});ks=[k for k in m if "series" not in k];print("keys="+",".join(sorted(ks)[:8]) if ks else "EMPTY")' 2>/dev/null || echo '?')"
          if printf '%s' "$REC" | $PY -c 'import sys,json;m=json.load(sys.stdin).get("metrics",{});sys.exit(0 if m else 1)' 2>/dev/null; then
            R_B="pass (status=done, metrics present)"
          else
            R_B="PARTIAL (status=done but metrics empty)"
          fi
          [ -f "runs/${R_BRUNID}/record.json" ] && echo "   record.json: runs/${R_BRUNID}/record.json (present)" || note "record.json missing for $R_BRUNID"
        else
          R_B="FAIL (status=$ST)"
          note "last 12 log lines follow"; tail -12 "runs/${R_BRUNID}/run.log" 2>/dev/null || true
        fi
      fi
    fi
  fi

  # ===========================================================================
  say "Stage C  Full agentic orchestrator (f1..f6)"
  if [ "$R_LLM" != "yes" ]; then
    R_C="skipped (LLM not configured)"; echo "   $R_C"
  elif printf '%s' "$R_B" | grep -q '^pass'; then
    export BACKEND_URL="http://localhost:${PORT}"
    if $PY -m automoose.agents.orchestrator \
          --physics grain_growth --params "$SMOKE_PARAMS" \
          --backend-name "$R_MODEL" > "$OUT/orch.txt" 2>&1; then
      # the orchestrator prints exactly one JSON object; parse the whole file,
      # or fall back to the last brace-balanced block if there is a preamble.
      R_CJSON="$($PY - "$OUT/orch.txt" <<'PYX'
import sys, json
t = open(sys.argv[1]).read().strip()
o = None
try:
    o = json.loads(t)                     # normal case: file IS one JSON object
except Exception:
    d = t.rfind("{")                      # fallback: last top-level object
    while d != -1:
        try: o = json.loads(t[d:]); break
        except Exception: d = t.rfind("{", 0, d)
if o is None:
    print("NO-JSON"); sys.exit()
if "error" in o:                          # orchestrator caught an exception
    print("ERROR:%s" % str(o["error"])[:200]); sys.exit()
comp = o.get("completed"); cred = o.get("credible")
mets = [k for k in (o.get("metrics") or {}) if "series" not in k]
fb   = ",".join(o.get("falsified_by") or []) or "none"
print("completed=%s credible=%s falsified_by=%s metrics=%s"
      % (comp, cred, fb, (",".join(sorted(mets)[:6]) or "none")))
PYX
)"
      echo "   orchestrator: $R_CJSON"
      case "$R_CJSON" in
        # a completed run is a PASS whether the Skeptic admits (credible=True)
        # or falsifies it (credible=False) — both mean f1..f6 executed.
        *completed=True*credible=True*)  R_C="pass ($R_CJSON)";;
        *completed=True*credible=False*) R_C="pass — run falsified by Skeptic, pipeline OK ($R_CJSON)";;
        *completed=True*)                R_C="pass ($R_CJSON)";;
        ERROR:*)                         R_C="FAIL (orchestrator caught: ${R_CJSON#ERROR:})";;
        NO-JSON)                         R_C="FAIL (no JSON emitted — see $OUT/orch.txt)";;
        *)                               R_C="PARTIAL ($R_CJSON)";;
      esac
    else
      R_C="FAIL (orchestrator errored)"; note "orchestrator error — see $OUT/orch.txt"; tail -15 "$OUT/orch.txt"
    fi
  else
    R_C="skipped (Stage B did not pass)"; echo "   $R_C"
  fi
fi

# =============================================================================
cat <<EOF

>>>>> PASTE THIS BACK >>>>>
AutoMOOSE smoke test  ${TS}
  OS            : ${R_OS}
  python        : ${R_PYV}
  git HEAD      : ${R_HEAD}   (uncommitted changes: ${R_DIRTY})
  MOOSE_EXEC    : ${R_MOOSE}   (found by backend: ${R_MOOSEFOUND})
  LLM config    : ${R_LLM}     (model-name: ${R_MODEL})
  ---
  Stage A  offline tests : ${R_A}
  Stage B  live MOOSE    : ${R_B}
           run_id        : ${R_BRUNID}
           metrics       : ${R_BMETRICS}
  Stage C  agentic f1-f6 : ${R_C}
  ---
  notes         : ${R_NOTES:-none}
  artifacts     : ${OUT}/  (pytest.txt, backend.log, orch.txt)
<<<<< END <<<<<
EOF

# overall exit code: non-zero only if a stage that RAN actually failed
echo "$R_A $R_B $R_C" | grep -q "FAIL" && exit 1 || exit 0
