#!/usr/bin/env python3
"""C6 (PLAN_C6_C8.md): mechanical heading edits of the held-out SurveyLens surveys, body text unchanged.

v1-split: in each top-level section (## ...) of a v1 survey, except References, that has no ### heading and at least
two paragraphs, every paragraph gets a ### heading made of its first sentence, citation markers and markdown removed,
cut to its first ten words.
v3-flat: every ### heading of a v3 survey becomes a bold lead-in ("**Heading.** ") at the start of the paragraph it
opened (a standalone bold line when the next block is not a paragraph).
Writes c6/runs_v1split/<sl>/review/literature.md and c6/runs_v3flat/<sl>/review/literature.md, and c6/counts.json.
Usage: c6_prepare.py <das_eval dir>
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Dict, List

HERE = Path(__file__).parent
REFS = re.compile(r"^##+\s*(References|Bibliography)\s*$", re.I)
CITE = re.compile(r"\[\d+(?:\s*[,–-]\s*\d+)*\]")


def is_prose(block: List[str]) -> bool:
    first = block[0].lstrip()
    return not (first.startswith(("#", "|", "- ", "* ", "> ", "```", "<!--", "!["))
                or re.match(r"^\d+\.\s", first) or re.match(r"^-{3,}$", first))


def blocks(lines: List[str]) -> List[List[str]]:
    out, cur = [], []
    for ln in lines:
        if ln.strip():
            cur.append(ln)
        elif cur:
            out.append(cur)
            cur = []
    if cur:
        out.append(cur)
    return out


def heading_from(par: List[str]) -> str:
    text = re.sub(r"[*_`]", "", CITE.sub("", " ".join(par)))
    first = re.split(r"(?<=[.!?])\s+(?=[A-Z])", re.sub(r"\s+", " ", text).strip())[0]
    return " ".join(first.split()[:10]).rstrip(" .,;:")


def split_body(md: str) -> tuple:
    lines = md.split("\n")
    cut = next((i for i, ln in enumerate(lines) if REFS.match(ln.strip())), len(lines))
    return lines[:cut], lines[cut:]


def v1_split(md: str) -> tuple:
    body, tail = split_body(md)
    sections, cur = [], []
    for ln in body:  # a section starts at a level-2 heading; the preamble (title, front text) is its own chunk
        if re.match(r"^##\s", ln) and cur:
            sections.append(cur)
            cur = []
        cur.append(ln)
    sections.append(cur)
    out, added = [], 0
    for sec in sections:
        has_h2 = bool(re.match(r"^##\s", sec[0]))
        bl = blocks(sec[1:] if has_h2 else sec)
        prose = [b for b in bl if is_prose(b)]
        if has_h2 and not any(ln.startswith("### ") for ln in sec) and len(prose) >= 2:
            out.append(sec[0])
            out.append("")
            for b in bl:
                if is_prose(b):
                    out.extend([f"### {heading_from(b)}", ""])
                    added += 1
                out.extend(b + [""])
        else:
            out.extend(sec)
    return "\n".join(out + tail), added


def v3_flat(md: str) -> tuple:
    body, tail = split_body(md)
    spaced: List[str] = []
    for ln in body:  # give every heading line its own block; blank lines change no text
        spaced.extend(["", ln, ""] if re.match(r"^#{1,6}\s", ln) else [ln])
    body = spaced
    out, pending, removed = [], None, 0
    for bl in blocks(body):
        if bl[0].startswith("### "):  # a heading, possibly with its paragraph on the next lines
            if pending:
                out.extend([f"**{pending}.**", ""])
            pending = bl[0][4:].strip().rstrip(".")
            removed += 1
            bl = bl[1:]
            if not bl:
                continue
        if pending:
            if is_prose(bl):
                bl = [f"**{pending}.** " + bl[0]] + bl[1:]
            else:
                out.extend([f"**{pending}.**", ""])
            pending = None
        out.extend(bl + [""])
    if pending:
        out.extend([f"**{pending}.**", ""])
    return "\n".join(out + tail), removed


def main() -> int:
    root = Path(sys.argv[1])
    held = json.loads((root / "skillrefine/heldout.json").read_text())["sl"]
    counts: Dict[str, Dict[str, int]] = {}
    for sl in held:
        v1 = (root / "pulled/deepseek-v4.1-flash_full_sl" / sl / "review/literature.md").read_text(encoding="utf-8")
        v3 = (root / "pulled/deepseek-v4.1-flash_full_v3_sl" / sl / "review/literature.md").read_text(encoding="utf-8")
        s1, added = v1_split(v1)
        f3, removed = v3_flat(v3)
        for name, text in (("runs_v1split", s1), ("runs_v3flat", f3)):
            d = HERE / "c6" / name / sl / "review"
            d.mkdir(parents=True, exist_ok=True)
            (d / "literature.md").write_text(text, encoding="utf-8")
        h3 = lambda t: sum(ln.startswith("### ") for ln in split_body(t)[0])  # noqa: E731
        counts[sl] = {"v1_h3": h3(v1), "v1split_h3": h3(s1), "added": added, "v3_h3": h3(v3), "v3flat_h3": h3(f3),
                      "removed": removed,
                      "v1_words_equal": re.sub(r"\W+", "", "".join(ln for ln in split_body(s1)[0] if not ln.startswith("### "))) ==
                                        re.sub(r"\W+", "", "".join(ln for ln in split_body(v1)[0] if not ln.startswith("### "))),
                      "v3_text_equal": re.sub(r"\W+", "", f3) == re.sub(r"\W+", "", re.sub(r"(?m)^### ", "", v3))}
    (HERE / "c6" / "counts.json").write_text(json.dumps(counts, indent=1) + "\n")
    tot = {k: sum(v[k] for v in counts.values()) for k in ("v1_h3", "v1split_h3", "v3_h3", "v3flat_h3")}
    print(json.dumps({"per_survey_mean": {k: round(v / len(counts), 1) for k, v in tot.items()},
                      "text_checks_failed": [s for s, v in counts.items() if not (v["v1_words_equal"] and v["v3_text_equal"])]}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
