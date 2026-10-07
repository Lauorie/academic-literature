#!/usr/bin/env python3
"""PreToolUse hook for SurveyBench runs: block WebFetch/Bash calls that reach the held-out reference survey.

Active only when SB_EXCLUDE_FILE is set (gen.sh sets it for sb* topics); otherwise it allows everything.
Exit code 2 blocks the call and returns the stderr message to the agent.
"""
import json
import os
import re
import sys
import urllib.parse


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(s or "").lower()).strip()


def main() -> int:
    path = os.environ.get("SB_EXCLUDE_FILE")
    if not path:
        return 0
    ex = json.load(open(path, encoding="utf-8"))
    call = json.load(sys.stdin)
    tool, inp = call.get("tool_name", ""), call.get("tool_input") or {}
    if tool == "WebFetch":
        text = urllib.parse.unquote(str(inp.get("url", "")))
    elif tool == "Bash":
        text = str(inp.get("command", ""))
    else:
        return 0
    low = text.lower()
    aid = ex.get("arxiv_id")
    hit = (aid and re.search(rf"(?<![\d.]){re.escape(aid)}(?!\d)", low)) or any(d in low for d in ex["dois"])
    if tool == "WebFetch" and not hit:
        hit = any(norm(t) in norm(text) for t in ex.get("titles") or [ex["title"]])
    if hit:
        sys.stderr.write("Blocked by the evaluation protocol: this source is withheld from this run. "
                         "Do not retry it; continue with other sources.\n")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
