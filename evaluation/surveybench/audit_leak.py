#!/usr/bin/env python3
"""Audit each SurveyBench run for contact with its held-out human reference survey.

Per run: presence in the citation ledger and the rendered reference list (must be zero), calls the
guard hook blocked, search results filtered, and non-blocked tool results whose text contains the
reference survey's full title (a WebSearch snippet counts; a fetched page or parsed PDF would be a leak).
Usage: audit_leak.py <runs dir> <exclude.json> <out.json>
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(s or "").lower()).strip()


def main() -> int:
    runs = Path(sys.argv[1])
    rows = []
    for e in json.loads(Path(sys.argv[2]).read_text()):
        e.setdefault("sb_id", e.get("sl_id"))
        run = runs / e["sb_id"]
        if not (run / "stream.jsonl").exists():
            continue
        titles = {norm(t) for t in (e.get("titles") or []) + [e["title"]] + (e.get("alt_titles") or [])} - {""}
        aid, dois = e.get("arxiv_id") or "\x00no-arxiv\x00", e["dois"]
        title = norm(e["title"])

        def hit(text: str) -> bool:
            low, nt = text.lower(), norm(text)
            return any(t in nt for t in titles) or aid in low or any(d in low for d in dois)

        def same_record(rec: dict) -> bool:
            ids = " ".join(str(rec.get(k) or "") for k in ("arxiv_id", "doi", "url", "pdf_url")).lower()
            return norm(rec.get("title")) in titles or aid in ids or any(d in ids for d in dois)

        def ref_line_hit(line: str) -> bool:
            segs = re.split(r'\.\s|"|\*', line)
            return any(norm(s) in titles for s in segs) or aid in line.lower() or any(d in line.lower() for d in dois)

        ledger = run / "review" / "citations.jsonl"
        lit = run / "review" / "literature.md"
        refs = lit.read_text(encoding="utf-8").split("\n## References", 1)[-1] if lit.exists() else ""
        body = lit.read_text(encoding="utf-8").split("\n## References", 1)[0] if lit.exists() else ""
        r = {"sb_id": e["sb_id"], "topic": e["topic"],
             "in_ledger": sum(same_record(json.loads(l).get("record") or {}) for l in ledger.read_text(encoding="utf-8").splitlines()
                              if l.strip()) if ledger.exists() else None,
             "in_reference_list": sum(ref_line_hit(l) for l in refs.splitlines()),
             "title_in_body": any(t in norm(body) for t in titles),
             "evidence_files_mentioning": sum(any(ref_line_hit(l) for l in p.read_text(errors="replace").splitlines())
                                              for p in (run / "review" / "evidence").glob("*") if p.is_file()),
             "blocked_calls": 0, "search_filtered": 0, "tool_results_with_title": []}
        uses = {}
        for line in (run / "stream.jsonl").read_text(errors="replace").splitlines():
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
                    uses[c.get("id")] = (c.get("name"), json.dumps(c.get("input"))[:200])
                elif c.get("type") == "tool_result":
                    t = c.get("content")
                    t = t if isinstance(t, str) else json.dumps(t)
                    if "withheld from this run" in t:
                        r["blocked_calls"] += 1
                        continue
                    r["search_filtered"] += sum(int(n) for n in re.findall(r'\\?"excluded_reference\\?":\s*(\d+)', t))
                    if any(x in norm(t) for x in titles):
                        name, inp = uses.get(c.get("tool_use_id"), ("?", ""))
                        r["tool_results_with_title"].append({"tool": name, "input": inp, "chars": len(t)})
        for f in (run / "review" / "search").glob("*.json"):
            r["search_filtered"] += sum(int(n) for n in re.findall(r'"excluded_reference":\s*(\d+)', f.read_text(errors="replace")))
        rows.append(r)
        print(f"{r['sb_id']} ledger={r['in_ledger']} reflist={r['in_reference_list']} body_title={r['title_in_body']} "
              f"evid={r['evidence_files_mentioning']} blocked={r['blocked_calls']} filtered={r['search_filtered']} "
              f"title_mentions_in_results={[(x['tool'], x['chars']) for x in r['tool_results_with_title']]}")
    Path(sys.argv[3]).write_text(json.dumps(rows, indent=1, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
