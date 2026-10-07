#!/usr/bin/env bash
# Generate one DAS-Bench survey with the academic-literature skill (runs as evalbot).
# Usage: gen.sh <model> <topic_id> [mode] [rep]
#   mode: full (full text when available, else abstract; default) | abs (abstracts only)
#         | sub (submission-grade mode of the skill, full text when available; 5 h limit)
#   rep:  repetition tag, e.g. r2 (default r1)
# Output: runs/<model-short>_<mode>_<rep>/<topic_id>/
set -uo pipefail
H="$HOME/das_eval"; MODEL="$1"; TID="$2"; MODE="${3:-full}"; REP="${4:-r1}"
export PATH=/opt/gen/bin:/usr/local/bin:/usr/bin:/bin
source "$H/.gateway.env"
case "$MODE" in
  full) READING="有全文读全文，没有读摘要 (read the full text when it can be obtained, otherwise the abstract)." ;;
  abs)  READING="仅阅读摘要 (abstracts only: build the review from the search-result abstracts; do not fetch or parse full texts)." ;;
  sub)  READING="有全文读全文，没有读摘要 (read the full text when it can be obtained, otherwise the abstract)."
        SCOPE="a submission-grade survey (投稿级综述): use the skill's submission-grade mode."; GEN_TIMEOUT="${GEN_TIMEOUT:-18000}" ;;
  *) echo "unknown mode $MODE" >&2; exit 2 ;;
esac
# SurveyBench (sb01-sb20) and SurveyLens (sl001-sl100) topics: own topic list, and the held-out human reference survey is withheld
# from search results (wis_mcp_search.py filter) and from WebFetch/Bash (PreToolUse hook /opt/gen/sb_guard.py).
TOPICS="$H/topics.json"; SB_EX=""
case "$TID" in
  sb*) TOPICS="$H/topics_sb.json"; SB_EX="/opt/gen/sb_exclude/$TID.json" ;;
  sl*) TOPICS="$H/topics_sl.json"; SB_EX="/opt/gen/sl_exclude/$TID.json" ;;   # SurveyLens, same guard
esac
[ -z "$SB_EX" ] || [ -r "$SB_EX" ] || { echo "missing $SB_EX" >&2; exit 2; }
TOPIC="$(python3 -c "import json,sys;print(next(t['topic'] for t in json.load(open(sys.argv[2])) if t['topic_id']==sys.argv[1]))" "$TID" "$TOPICS")"
OUT="$H/runs/${MODEL##*/}_${MODE}_${REP}/$TID"; mkdir -p "$OUT/work"
cat > "$OUT/prompt.txt" <<EOF
Use the academic-literature skill to write a comprehensive academic survey of the field on the topic:

"$TOPIC"

Run settings (this is a non-interactive batch run; nobody can answer questions, so never call AskUserQuestion):
- Reading mode: $READING
- Scope: ${SCOPE:-a comprehensive survey of the field, not a quick scan.}
- Language: English.
- Output directory: $OUT/review
Finish only when the rendered review is at $OUT/review/literature.md.
EOF
date -Is > "$OUT/started_at"
# Per-session temp dir: concurrent sessions share one uid, and Claude Code keeps background-task
# outputs under $TMPDIR/claude-<uid>/; a shared /tmp let one agent's wildcard cleanup delete
# another session's files (2026-09-30, full_r3/019).
mkdir -p "$OUT/tmp"; export TMPDIR="$OUT/tmp" TMP="$OUT/tmp" TEMP="$OUT/tmp"
cd "$OUT/work"
timeout "${GEN_TIMEOUT:-10800}" env -u CLAUDECODE TMPDIR="$TMPDIR" TMP="$TMP" TEMP="$TEMP" \
  WISDOCRS_BASE_URL="$WISDOCRS_BASE_URL" ${SB_EX:+SB_EXCLUDE_FILE="$SB_EX"} \
  ANTHROPIC_BASE_URL="https://aigateway.paperbypass.com/api" \
  ANTHROPIC_AUTH_TOKEN="$PAPERBYPASS_AUTH_TOKEN" ANTHROPIC_API_KEY="" \
  ANTHROPIC_MODEL="$MODEL" ANTHROPIC_SMALL_FAST_MODEL="$MODEL" \
  ANTHROPIC_DEFAULT_HAIKU_MODEL="$MODEL" ANTHROPIC_DEFAULT_SONNET_MODEL="$MODEL" \
  ANTHROPIC_DEFAULT_OPUS_MODEL="$MODEL" CLAUDE_CODE_SUBAGENT_MODEL="$MODEL" \
  DISABLE_TELEMETRY=1 CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1 \
  claude -p "$(cat "$OUT/prompt.txt")" --model "$MODEL" \
    --dangerously-skip-permissions --output-format stream-json --verbose \
  > "$OUT/stream.jsonl" 2> "$OUT/stderr.log" < /dev/null
echo "$?" > "$OUT/exit_code"; date -Is > "$OUT/finished_at"
# Disk: images extracted from parsed full texts are ~200 MB per run and unused after the session; the
# parsed text, evidence, ledger and stream are kept.
# review/figures/ holds the skill's own figures (submission-grade mode) and is kept.
find "$OUT/review" "$OUT/work" -type f \( -name '*.png' -o -name '*.jpg' -o -name '*.jpeg' \) -not -path "$OUT/review/figures/*" -delete 2>/dev/null
rm -rf "$OUT/tmp"
