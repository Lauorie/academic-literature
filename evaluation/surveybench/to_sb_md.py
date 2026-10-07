#!/usr/bin/env python3
"""Convert skill reviews to SurveyBench's input format.

SurveyBench's outline and chapter parsers only see numbered headings ("## 2 Title", "### 2.1 Title"),
so headings are numbered hierarchically. Nothing else changes; "## References" keeps its exact
spelling because the evaluator cuts the text at that marker.
Usage: to_sb_md.py <runs dir (…/<condition>_sb)> <exclude.json> <out dir>
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HEAD = re.compile(r"^(#{2,4})\s+(.*)$")


def number_headings(md: str) -> str:
    counters = [0, 0, 0]
    out, in_code = [], False
    for line in md.splitlines():
        if line.lstrip().startswith("```"):
            in_code = not in_code
        m = None if in_code else HEAD.match(line)
        if not m or m.group(2).strip().lower() == "references":
            out.append(line)
            continue
        level = len(m.group(1)) - 2
        counters[level] += 1
        counters[level + 1:] = [0] * (2 - level)
        num = ".".join(str(c) for c in counters[: level + 1])
        title = re.sub(r"^(?:\d+(?:\.\d+)*\.?|[IVX]+\.)\s+", "", m.group(2).strip())  # drop the model's own numbering
        out.append(f"{m.group(1)} {num} {title}")
    return "\n".join(out) + "\n"


def main() -> int:
    runs, out = Path(sys.argv[1]), Path(sys.argv[3])
    out.mkdir(parents=True, exist_ok=True)
    for e in json.loads(Path(sys.argv[2]).read_text()):
        src = runs / e["sb_id"] / "review" / "literature.md"
        if not src.exists():
            print(f"MISSING {e['sb_id']} {e['topic']}", file=sys.stderr)
            continue
        text = number_headings(src.read_text(encoding="utf-8"))
        assert "\n## References" in text, e["sb_id"]
        (out / f"{e['topic']}.md").write_text(text, encoding="utf-8")
        print(f"OK {e['sb_id']} {e['topic']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
