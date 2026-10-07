#!/usr/bin/env bash
# Evaluate every submitted topic of one method with DAS-Eval (runs on the GPU host as root).
# Usage: run_eval.sh <method> [parallel_topics] [bench_dir_name]
#   bench_dir_name defaults to DAS-Bench (main judge). Any other name (e.g. DAS-Bench-xjudge)
#   is a cross-judge bench: it reuses the main bench's MinerU cache and DAS-2M metadata,
#   skips preprocessing, and only scores topics the main bench has already prepared.
# Every evaluator gets explicit paths: the scripts resolve PROJECT_ROOT through symlinks,
# so relying on defaults would write cross-judge results into the main bench.
set -uo pipefail
M="$1"; PAR="${2:-4}"; BENCH="${3:-DAS-Bench}"
D=/root/autodl-tmp/dasbench
P=/root/autodl-tmp/envs/eval/bin/python
MAIN="$D/DAS-Bench"; ROOT="$D/$BENCH"
cd "$ROOT"
source "$D/judge.env"

MDC="$MAIN/eval_cache"
if [ "$BENCH" != "DAS-Bench" ]; then
  # BSC writes its evidence JSONL under <md-cache-root>/<method>/ref and refuses to overwrite,
  # so a cross-judge bench keeps its own cache and only borrows the MinerU markdown.
  MDC="$ROOT/bsc_cache"; mkdir -p "$MDC/$M"; ln -sfn "$MAIN/eval_cache/$M/md" "$MDC/$M/md"
fi

if [ "$BENCH" = "DAS-Bench" ]; then
  "$P" "$MAIN/evaluation/eval_prepare.py" --method "$M" --gpus "${EVAL_GPUS:-0}" --timeout-seconds 600
  "$P" "$D/tools/das2m_index.py" export --db "$D/das2m.sqlite" --eval-inputs "$MAIN/eval_inputs" --out "$MAIN/data/metadata"
fi

for pdf in "$MAIN/eval_inputs/$M"/*.pdf; do
  T=$(basename "$pdf" .pdf)
  [ -s "$MAIN/eval_cache/$M/md/$T.md" ] && echo "$T"
done | xargs -P "$PAR" -I{} bash -c '
    M="$0"; T="$1"; P="$2"; ROOT="$3"; MAIN="$4"; MDC="$5"
    mkdir -p "$ROOT/logs/$M"
    ok() { grep -q "\"status\": \"success\"" "$1" 2>/dev/null; }  # whitelist: anything else re-runs
    R="$ROOT/results/$M"
    # Each family runs only if its own result is missing or failed, so a retry never
    # re-judges (and can never overwrite) a family that already succeeded.
    if ! ok "$R/bsc/api_off/$T.json"; then
      # --overwrite rebuilds the evidence JSONL; the build is deterministic from ref+md.
      "$P" "$MAIN/evaluation/eval_bsc.py" --method "$M" --topic-id "$T" --api-mode off --overwrite \
        --ref-input-root "$MAIN/eval_inputs" --md-cache-root "$MDC" --metadata-root "$MAIN/data/metadata" \
        --mineru-root "$MAIN/data/mineru" --results-root "$ROOT/results" --config "$ROOT/config.json" \
        >> "$ROOT/logs/$M/bsc_$T.log" 2>&1
    fi
    if ! ok "$R/mar/api_off/$T.json"; then
      "$P" "$MAIN/evaluation/eval_mar.py" --method "$M" --topic-id "$T" --api-mode off --overwrite \
        --cache-root "$MAIN/eval_cache" --results-root "$ROOT/results" --config "$ROOT/config.json" \
        >> "$ROOT/logs/$M/mar_$T.log" 2>&1
    fi
    if ! grep -q "\"status\": \"done\"" "$R/tsq_hdq/api_off/$T.json" 2>/dev/null; then
      "$P" "$MAIN/evaluation/eval_tsq_hdq.py" --method "$M" --topic-id "$T" --api-mode off \
        --root "$ROOT" --config "$ROOT/config.json" \
        >> "$ROOT/logs/$M/tsq_hdq_$T.log" 2>&1
    fi
    echo "done $M $T"
  ' "$M" {} "$P" "$ROOT" "$MAIN" "$MDC"
echo "EVAL_DONE $M $BENCH"
