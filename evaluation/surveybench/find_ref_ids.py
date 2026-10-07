#!/usr/bin/env python3
"""Look up the arXiv id of each SurveyBench human reference survey by exact (normalized) title."""
from __future__ import annotations

import json
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ATOM = "{http://www.w3.org/2005/Atom}"


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def lookup(title: str) -> list[dict]:
    words = re.sub(r"[^A-Za-z0-9 ]+", " ", title).split()
    q = " AND ".join(f"ti:{w}" for w in words if len(w) > 2)
    url = "http://export.arxiv.org/api/query?" + urllib.parse.urlencode({"search_query": q, "max_results": 20})
    with urllib.request.urlopen(url, timeout=60) as r:
        root = ET.fromstring(r.read())
    out = []
    for e in root.iter(ATOM + "entry"):
        t = " ".join(e.find(ATOM + "title").text.split())
        aid = e.find(ATOM + "id").text.rsplit("/abs/", 1)[1]
        out.append({"arxiv_id": re.sub(r"v\d+$", "", aid), "title": t, "published": e.find(ATOM + "published").text[:10]})
    return out


def main() -> int:
    human = Path(sys.argv[1])
    res = []
    for f in sorted(human.glob("*.md")):
        title = f.read_text(encoding="utf-8").splitlines()[0].lstrip("# ").strip()
        hits = lookup(title)
        exact = [h for h in hits if norm(h["title"]) == norm(title)]
        res.append({"topic": f.stem, "title": title, "matches": exact or hits[:3], "exact": bool(exact)})
        print(f"{'OK ' if exact else '?? '}{f.stem} -> {[h['arxiv_id'] for h in (exact or hits[:3])]}", file=sys.stderr)
        time.sleep(3.5)
    Path(sys.argv[2]).write_text(json.dumps(res, indent=1, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
