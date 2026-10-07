#!/usr/bin/env python3
"""Identify each SurveyLens canonical human survey (DOI / arXiv id) by exact normalized title.

Semantic Scholar /paper/search/match first, CrossRef bibliographic query as fallback. Titles come from the
human .md's first heading when it has one, else from the file name (':' was saved as '-').
Usage: find_ref_ids.py <topics_map.json> <SurveyLens root> <out.json>
"""
from __future__ import annotations

import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(s or "").lower()).strip()


def get(url: str) -> dict:
    for attempt in range(6):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "das-eval/1.0 (mailto:support@atominfinite.ai)"})
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)
        except Exception:  # noqa: BLE001  rate limits / transient errors: back off
            time.sleep(4 * (attempt + 1))
    return {}


def main() -> int:
    rows = json.loads(Path(sys.argv[1]).read_text())
    root = Path(sys.argv[2])
    out = []
    for i, r in enumerate(rows, 1):
        md = (root / r["human_md"]).read_text(encoding="utf-8", errors="replace")
        first = next((l.lstrip("# ").strip() for l in md.splitlines() if l.startswith("# ")), "")
        cands = [t for t in (first, r["human_title"]) if t]
        hit = None
        for t in cands:
            j = get("https://api.semanticscholar.org/graph/v1/paper/search/match?"
                    + urllib.parse.urlencode({"query": t, "fields": "title,externalIds,year,venue"}))
            p = (j.get("data") or [{}])[0]
            if p and norm(p.get("title")) == norm(t):
                ext = p.get("externalIds") or {}
                hit = {"source": "s2", "title": p["title"], "doi": ext.get("DOI"), "arxiv_id": ext.get("ArXiv")}
                break
            time.sleep(1.2)
        if not hit:
            for t in cands:
                j = get("https://api.crossref.org/works?" + urllib.parse.urlencode({"query.bibliographic": t, "rows": 5}))
                for it in (j.get("message") or {}).get("items", []):
                    ct = (it.get("title") or [""])[0]
                    if norm(ct) == norm(t):
                        hit = {"source": "crossref", "title": ct, "doi": it.get("DOI"), "arxiv_id": None}
                        break
                if hit:
                    break
        dois = sorted({d.lower() for d in [hit and hit.get("doi"),
                                            hit and hit.get("arxiv_id") and f"10.48550/arxiv.{hit['arxiv_id']}"] if d})
        out.append({"sl_id": f"sl{i:03d}", "discipline": r["discipline"], "topic": r["topic"],
                    "title": (hit or {}).get("title") or cands[0], "alt_titles": cands,
                    "arxiv_id": (hit or {}).get("arxiv_id"), "dois": dois, "match": (hit or {}).get("source")})
        print(f"{out[-1]['sl_id']} {out[-1]['match'] or 'NONE':8s} doi={dois} | {cands[0][:70]}", file=sys.stderr)
        time.sleep(1.2)
    Path(sys.argv[3]).write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
