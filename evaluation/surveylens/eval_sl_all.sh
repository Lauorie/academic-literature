#!/usr/bin/env bash
# Judge systems under a processed root with the main judge (2 passes) and the cross judge (1 pass).
# Usage: eval_sl_all.sh <processed root> <system>...   Finished files are skipped.
set -uo pipefail
H=/home/juli/citation/DAS/das_eval; S=$H/surveylens; ROOT="$1"; shift
set -a; source "$H/.gateway.env"; set +a
for sys in "$@"; do
  for jp in "qwen/qwen3-30b-a3b-instruct-2507 p1" "qwen/qwen3-30b-a3b-instruct-2507 p2" "qwen/qwen3.5-397b-a17b p1"; do
    echo "$sys|$jp"
  done
done | xargs -P 6 -I{} bash -c '
  IFS="|" read -r sys jp <<< "{}"; read -r j p <<< "$jp"
  python3 '"$S"'/run_sl_eval.py --processed-root '"$ROOT"' --system "$sys" --model "$j" --pass-tag "$p" \
    --out '"$S"'/results --workers ${WORKERS:-6} > '"$S"'/logs/"${sys}_${j//\//_}_$p.log" 2>&1
  echo "$(date +%T) finished $sys $j $p exit=$? failed=$(grep -c "FAILED" '"$S"'/logs/"${sys}_${j//\//_}_$p.log")"'
