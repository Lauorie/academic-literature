#!/usr/bin/env bash
# C8 (review_followup/PLAN_C6_C8.md): the Skill-Full harness without the skill (runs as evalbot).
# Same generator, gateway, limit, reading-mode sentence and per-session TMPDIR as gen.sh; differences:
# a config dir with no skill and with WisPaper registered as an MCP server, and a prompt that states the
# output contract instead of naming the skill.
# Usage: gen_noskill.sh <model> <topic_id> [rep]
# Output: runs/<model-short>_noskill_<rep>/<topic_id>/
set -uo pipefail
H="$HOME/das_eval"; MODEL="$1"; TID="$2"; REP="${3:-r1}"
export PATH=/opt/gen/bin:/usr/local/bin:/usr/bin:/bin
source "$H/.gateway.env"
READING="有全文读全文，没有读摘要 (read the full text when it can be obtained, otherwise the abstract)."
TOPIC="$(python3 -c "import json,sys;print(next(t['topic'] for t in json.load(open(sys.argv[2])) if t['topic_id']==sys.argv[1]))" "$TID" "$H/topics.json")"
OUT="$H/runs/${MODEL##*/}_noskill_${REP}/$TID"; mkdir -p "$OUT/work" "$OUT/review"
cat > "$OUT/prompt.txt" <<EOF
Write a comprehensive academic survey of the field on the topic:

"$TOPIC"

You can search the scholarly literature with the WisPaper tools (quick_search and deep_search), which are available to you through MCP.

Run settings (this is a non-interactive batch run; nobody can answer questions, so never call AskUserQuestion):
- Reading mode: $READING
- Scope: a comprehensive survey of the field, not a quick scan.
- Language: English.
- Output: write the survey as Markdown to $OUT/review/literature.md. Cite works in the text with numbers in square brackets, e.g. [3] or [2, 7]. End with a section "## References" that lists every cited work as one numbered entry in the form: [n] Authors. *Title.* Venue, Year. DOI or arXiv URL.
Finish only when the survey is at $OUT/review/literature.md.
EOF
date -Is > "$OUT/started_at"
mkdir -p "$OUT/tmp"; export TMPDIR="$OUT/tmp" TMP="$OUT/tmp" TEMP="$OUT/tmp"
cd "$OUT/work"
timeout "${GEN_TIMEOUT:-10800}" env -u CLAUDECODE TMPDIR="$TMPDIR" TMP="$TMP" TEMP="$TEMP" \
  CLAUDE_CONFIG_DIR="$HOME/.claude_noskill" \
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
find "$OUT/review" "$OUT/work" -type f \( -name '*.png' -o -name '*.jpg' -o -name '*.jpeg' -o -name '*.pdf' \) -delete 2>/dev/null
rm -rf "$OUT/tmp"
