#!/usr/bin/env bash
# C8 queue: gen_noskill.sh for the 30 DAS-Bench topics whose run dir does not exist yet, at most CAP at a time.
# Usage: queue_noskill.sh <cap> [rep]
H="$HOME/das_eval"; CAP="$1"; REP="${2:-r1}"; M=deepseek/deepseek-v4.1-flash
for i in $(seq -w 1 30); do
  T="0$i"; T="${T: -3}"
  [ -d "$H/runs/${M##*/}_noskill_${REP}/$T" ] && continue
  while [ "$(pgrep -u "$(id -u)" -fc '[g]en_noskill\.sh deepseek')" -ge "$CAP" ]; do sleep 20; done
  echo "$(date +%T) launch $T"
  setsid nohup bash "$H/gen_noskill.sh" "$M" "$T" "$REP" > /dev/null 2>&1 < /dev/null &
  sleep 10
done
wait
echo "$(date +%T) queue_noskill done"
