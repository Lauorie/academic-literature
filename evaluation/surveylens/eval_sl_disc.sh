#!/usr/bin/env bash
# Discipline-rubric judging (secondary metric): primary judge, 1 pass. Usage: eval_sl_disc.sh <processed root> <system>...
set -uo pipefail
H=/home/juli/citation/DAS/das_eval; S=$H/surveylens; ROOT="$1"; shift
set -a; source "$H/.gateway.env"; set +a
printf '%s\n' "$@" | xargs -P 4 -I{} bash -c '
  python3 '"$S"'/run_sl_eval.py --rubric discipline --processed-root '"$ROOT"' --system "{}" \
    --model qwen/qwen3-30b-a3b-instruct-2507 --pass-tag p1 --out '"$S"'/results --workers 6 > '"$S"'/logs/disc_{}.log 2>&1
  echo "$(date +%T) finished disc {} exit=$? failed=$(grep -c FAILED '"$S"'/logs/disc_{}.log)"'
