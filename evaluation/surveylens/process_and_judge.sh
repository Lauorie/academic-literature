#!/usr/bin/env bash
# Process one condition's runs with the released pipeline, then judge it (generic: primary x2 + cross x1;
# discipline: primary x1). Finished files are skipped on re-runs.
# Usage: process_and_judge.sh <runs dir> <method>
set -uo pipefail
H=/home/juli/citation/DAS/das_eval; S=$H/surveylens
RUNS="$(realpath "$1")"   # resolve before cd: callers pass paths relative to their own cwd
set -a; source "$H/.gateway.env"; set +a
export API_KEY="$PAPERBYPASS_AUTH_TOKEN" BASE_URL="https://aigateway.paperbypass.com/api/v1" PYTHONUNBUFFERED=1
cd "$S"
python3 process_sl.py "$RUNS" exclude.json "$2" staging > "logs/process_$2.log" 2>&1 || { echo "$(date +%T) PROCESS_FAILED $2"; exit 1; }
grep -E "^$2: staged" "logs/process_$2.log"
./eval_sl_all.sh "$S/staging/processed" "$2" >> logs/eval_ours.log 2>&1
./eval_sl_disc.sh "$S/staging/processed" "$2" >> logs/eval_ours.log 2>&1
echo "$(date +%T) judged $2"
