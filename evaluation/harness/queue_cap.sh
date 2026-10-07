#!/usr/bin/env bash
# Job scheduler with a global cap: launches gen.sh for jobs whose run dir does not exist yet, keeping at most
# CAP gen.sh sessions running in total (including sessions started by an earlier queue). Replaces queue.sh when
# the parallelism of a running xargs queue has to change.
# Usage: queue_cap.sh <jobfile> <cap>
H="$HOME/das_eval"; CAP="$2"
grep -vE '^\s*(#|$)' "$1" | while read -r M T MODE REP; do
  MODE="${MODE:-full}"; REP="${REP:-r1}"
  [ -d "$H/runs/${M##*/}_${MODE}_${REP}/$T" ] && continue
  while [ "$(pgrep -u "$(id -u)" -fc '/gen\.sh deepseek|das_eval/gen\.sh')" -ge "$CAP" ]; do sleep 20; done
  echo "$(date +%T) launch $T"
  setsid nohup bash "$H/gen.sh" "$M" "$T" "$MODE" "$REP" > /dev/null 2>&1 < /dev/null &
  sleep 10
done
wait
echo "$(date +%T) queue_cap done"
