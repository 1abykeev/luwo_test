#!/usr/bin/env bash
# The full fake-model campaign (about 15 minutes). Results in loadtest/results/.
# A: realistic pace (1 s per model call, 1-3 s think time) at growing numbers of users.
# B: ceiling of the backend itself (no model delay, no think time).
# Steps that already have a report.txt are skipped, so a stopped campaign can be started again.
set -euo pipefail
cd "$(dirname "$0")/.."

step() {
  local name=$1
  if [ -f "loadtest/results/$name/report.txt" ]; then echo "skip $name (already done)"; return; fi
  echo "start $name"
  rm -rf "loadtest/results/$name"
  loadtest/run_step.sh "$@" > /dev/null
  echo "end $name"
}

for users in 50 100 200 400; do
  step "A-u$users" "$users" $((users / 10)) 90 1.0 1 3
done
for users in 10 30 100; do
  step "B-u$users" "$users" 10 60 0 0 0
done
echo finished
