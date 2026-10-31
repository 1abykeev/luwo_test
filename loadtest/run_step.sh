#!/usr/bin/env bash
# One measured load-test step against a fresh server on port 8001 and the load-test database.
# The model is the fake one unless you run it with LLM_PROVIDER=claude (then it uses the key from .env and costs money).
#
#   loadtest/run_step.sh <name> <users> <spawn_rate> <seconds> <fake_delay> <think_min> <think_max> [pool_size] [overflow]
#
# Example (100 users, 1 s per model call, 1-3 s think time, 90 s):
#   loadtest/run_step.sh u100 100 20 90 1.0 1 3
#
# Results go to loadtest/results/<name>/ : locust csv, server log, process.csv, before/after metrics, report.txt
set -euo pipefail
cd "$(dirname "$0")/.."
source .venv/bin/activate

NAME=$1 USERS=$2 RATE=$3 SECONDS_RUN=$4 DELAY=$5 THINK_MIN=$6 THINK_MAX=$7 POOL=${8:-10} OVERFLOW=${9:-10}
OUT=loadtest/results/$NAME
mkdir -p "$OUT"
PORT=8001

# The previous step's server may still be shutting down: wait until the port is really free
for _ in $(seq 1 60); do lsof -ti :$PORT -sTCP:LISTEN > /dev/null 2>&1 || break; sleep 0.5; done
if lsof -ti :$PORT -sTCP:LISTEN > /dev/null 2>&1; then echo "port $PORT is still busy" >&2; exit 1; fi

export DATABASE_URL=postgresql+asyncpg://luwo:luwo@localhost:5433/luwo_loadtest
LLM_PROVIDER=${LLM_PROVIDER:-fake} FAKE_LLM_DELAY=$DELAY DB_POOL_SIZE=$POOL DB_MAX_OVERFLOW=$OVERFLOW \
  uvicorn app.main:app --host 127.0.0.1 --port $PORT --log-level warning > "$OUT/server.log" 2>&1 &
SERVER=$!
trap 'kill $SERVER 2>/dev/null || true; wait $SERVER 2>/dev/null || true' EXIT

for _ in $(seq 1 40); do curl -sf -o /dev/null http://127.0.0.1:$PORT/metrics && break; sleep 0.5; done

# Warm-up: a few requests so imports, connections and caches are not counted
TOKEN=$(curl -s -X POST http://127.0.0.1:$PORT/auth/login -H 'content-type: application/json' \
  -d '{"email":"aigul@luwo.test","password":"demo1234"}' | python3 -c "import sys,json;print(json.load(sys.stdin)['access_token'])")
for _ in 1 2 3; do
  curl -s -o /dev/null -X POST http://127.0.0.1:$PORT/chat -H "authorization: Bearer $TOKEN" \
    -H 'content-type: application/json' -d '{"message":"Покажи список учеников 4А"}'
done

curl -s http://127.0.0.1:$PORT/metrics > "$OUT/before.txt"
python loadtest/sample_process.py $SERVER $((SECONDS_RUN + 5)) "$OUT/process.csv" > "$OUT/process.txt" &
SAMPLER=$!

TOKENS_CSV="$OUT/tokens.csv" THINK_MIN=$THINK_MIN THINK_MAX=$THINK_MAX locust -f loadtest/locustfile.py --headless \
  -u "$USERS" -r "$RATE" -t "${SECONDS_RUN}s" --host http://127.0.0.1:$PORT \
  --csv "$OUT/locust" --only-summary > "$OUT/locust.txt" 2>&1 || true

wait $SAMPLER || true
curl -s http://127.0.0.1:$PORT/metrics > "$OUT/after.txt"

{
  echo "step: $NAME  users=$USERS spawn=$RATE/s duration=${SECONDS_RUN}s fake_delay=${DELAY}s think=${THINK_MIN}-${THINK_MAX}s pool=$POOL+$OVERFLOW"
  echo "--- process"; cat "$OUT/process.txt"
  echo "--- backend metrics (whole test, ramp-up included)"
  python loadtest/metrics_report.py "$OUT/before.txt" "$OUT/after.txt" "$SECONDS_RUN"
} | tee "$OUT/report.txt"
echo "--- locust aggregated (exact percentiles)"
python3 - "$OUT/locust_stats.csv" <<'PY' | tee -a "$OUT/report.txt"
import csv, sys
rows = list(csv.DictReader(open(sys.argv[1])))
agg = next(r for r in rows if r["Name"] == "Aggregated")
chat = [r for r in rows if r["Name"].startswith("/chat")]
n = sum(int(r["Request Count"]) for r in chat)
fails = sum(int(r["Failure Count"]) for r in chat)
print(f"requests {agg['Request Count']}, failures {agg['Failure Count']}, req/s {float(agg['Requests/s']):.1f}")
print(f"aggregated: median {agg['50%']} ms, p95 {agg['95%']} ms, p99 {agg['99%']} ms, max {agg['Max Response Time']} ms")
print(f"/chat only: {n} requests, {fails} failed")
PY
