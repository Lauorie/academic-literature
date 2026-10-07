#!/usr/bin/env bash
# C8: pull the NoSkill-Agent runs, convert them for DAS-Eval, push the inputs and start both judges on the GPU host.
# Same conversion (tools/make_submission.py, reference-section path) and evaluator (tools/run_eval.sh) as every
# other condition. Method name: noskill_deepseek-v4.1-flash_r1.
set -uo pipefail
H=/home/juli/citation/DAS/das_eval; cd "$H"
source .remote.env
SSH="ssh -o StrictHostKeyChecking=no -p $REMOTE_PORT"
RUN=deepseek-v4.1-flash_noskill_r1; M=noskill_deepseek-v4.1-flash_r1; EI=$H/eval_inputs
sshpass -e rsync -a -e "$SSH" --include '*/' --include 'review/literature.md' --include '*.txt' --include 'stream.jsonl' \
  --include 'exit_code' --include '*_at' --exclude '*' "$REMOTE_HOST:/home/evalbot/das_eval/runs/$RUN/" "$H/pulled/$RUN/"
for d in "$H/pulled/$RUN"/*; do
  t=$(basename "$d"); [ -f "$EI/$M/$t.pdf" ] && continue
  if [ -f "$d/review/literature.md" ]; then
    python3 tools/make_submission.py --review "$d/review" --eval-inputs "$EI" --method "$M" --topic-id "$t" \
      --das2m-db data/titles.sqlite 2>&1 | tail -1
  else
    echo "NO_OUTPUT $t exit=$(cat "$d/exit_code" 2>/dev/null)"
  fi
done
sshpass -e rsync -a -e "$SSH" "$EI/$M" "$REMOTE_HOST:/root/autodl-tmp/dasbench/DAS-Bench/eval_inputs/"
sshpass -e rsync -a -e "$SSH" "$H/tools/" "$REMOTE_HOST:/root/autodl-tmp/dasbench/tools/"
echo "inputs: $(ls "$EI/$M"/*.pdf 2>/dev/null | wc -l)"
