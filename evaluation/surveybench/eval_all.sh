#!/usr/bin/env bash
# Judge every method dir under the given roots with both judges and all passes; finished topics are skipped.
# Usage: eval_all.sh <method>...   (methods resolved in SurveyBench/data or surveybench/data)
set -uo pipefail
H=/home/juli/citation/DAS/das_eval/surveybench; SB=/home/juli/citation/SurveyBench/data
set -a; source "$H/../.gateway.env"; set +a
JOBS=()
for m in "$@"; do
  d="$SB/$m"; [ -d "$d" ] || d="$H/data/$m"
  for jp in "openai/gpt-4o-mini p1" "openai/gpt-4o-mini p2" "openai/gpt-4o-mini p3" \
            "qwen/qwen3.5-397b-a17b p1" "qwen/qwen3.5-397b-a17b p2"; do
    set -- $jp
    JOBS+=("$m|$d|$1|$2")
  done
done
printf '%s\n' "${JOBS[@]}" | xargs -P 4 -I{} bash -c '
  IFS="|" read -r m d j p <<< "{}"
  python3 '"$H"'/run_sb_eval.py --method "$m" --survey-dir "$d" --human-dir '"$SB"'/HumanSurvey \
    --model "$j" --pass-tag "$p" --out '"$H"'/results --workers 5 \
    > '"$H"'/logs/"${m}_${j//\//_}_$p.log" 2>&1
  echo "$(date +%T) finished $m $j $p exit=$?"'
