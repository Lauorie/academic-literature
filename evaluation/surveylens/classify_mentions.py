#!/usr/bin/env python3
"""Classify where the withheld survey's title appears in non-blocked tool results.

head  = the title occurs in the first 1,500 characters of the result: the result may be the survey itself
        (or a search-result list that names it); listed for manual review.
later = the title occurs only further in: a citation in another paper's text or bibliography.
Usage: classify_mentions.py <runs dir> <exclude.json>
"""
import json
import re
import sys
from pathlib import Path


def norm(s):
    return re.sub(r"[^a-z0-9]+", " ", str(s or "").lower()).strip()


runs = Path(sys.argv[1])
heads, later = [], 0
for e in json.loads(Path(sys.argv[2]).read_text()):
    st = runs / e["sl_id"] / "stream.jsonl"
    if not st.exists():
        continue
    titles = [norm(t) for t in e.get("titles") or [e["title"]]]
    uses = {}
    for line in st.read_text(errors="replace").splitlines():
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        msg = d.get("message")
        content = msg.get("content") if isinstance(msg, dict) else None
        if not isinstance(content, list):
            continue
        for c in content:
            if c.get("type") == "tool_use":
                uses[c.get("id")] = (c.get("name"), json.dumps(c.get("input"))[:160])
            elif c.get("type") == "tool_result":
                t = c.get("content")
                t = t if isinstance(t, str) else json.dumps(t)
                if "withheld from this run" in t:
                    continue
                n = norm(t)
                pos = min((n.find(x) for x in titles if x in n), default=-1)
                if pos < 0:
                    continue
                if pos < 1500:
                    heads.append((e["sl_id"], uses.get(c.get("tool_use_id"), ("?", ""))[0],
                                  uses.get(c.get("tool_use_id"), ("?", ""))[1][:110], n[max(0, pos - 150):pos + 200]))
                else:
                    later += 1
print(f"later (citations inside other texts): {later}; head (manual review): {len(heads)}")
for h in heads:
    print("\n", h[0], h[1], h[2], "\n   ...", h[3])
