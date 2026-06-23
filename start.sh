#!/usr/bin/env bash
# AutoMOOSE — Start
# Usage: bash start.sh

if [ -f "config.env" ]; then
    export $(grep -v '^#' config.env | xargs)
    echo "✓ Loaded config.env"
else
    echo "✗ config.env not found"; exit 1
fi

MOOSE_OK=false
[ -f "$MOOSE_EXEC" ] && MOOSE_OK=true
$MOOSE_OK && echo "✓ MOOSE found: $MOOSE_EXEC" || echo "⚠  MOOSE not found — input-only mode"
[ -z "$ANTHROPIC_API_KEY" ] || [ "$ANTHROPIC_API_KEY" = "sk-ant-..." ] \
    && echo "⚠  ANTHROPIC_API_KEY not set" || echo "✓ ANTHROPIC_API_KEY set"

echo ""
echo "Backend  → http://localhost:8000"
echo "Frontend → http://localhost:5173"
echo "Ctrl+C to stop both."
echo ""

conda activate moose 2>/dev/null || true
uvicorn automoose.server:app --port 8000 &
BACKEND_PID=$!
cd ..
sleep 2
cd frontend && npm run dev &
FRONTEND_PID=$!
cd ..

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; echo 'Stopped.'" INT
wait
