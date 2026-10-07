#!/usr/bin/env python3
"""Tests for `citation_ledger.py fill`: missing venues come from CrossRef or not at all.

A local HTTP server stands in for CrossRef (CROSSREF_API_BASE points at it), so the tests run offline.
"""
import json
import os
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

SCRIPT = Path(os.environ.get("LEDGER_SCRIPT", Path(__file__).resolve().parent.parent / "scripts/citation_ledger.py"))
sys.path.insert(0, str(SCRIPT.parent))
from citation_ledger import Ledger, mint_key  # noqa: E402

PASS, FAIL = [], []

DOI_RECORDS = {"10.1/withdoi": {"title": ["Paper With Doi"], "container-title": ["Journal of Tests"],
                                "author": [{"family": "Smith"}], "issued": {"date-parts": [[2023]]}}}
SEARCH = {
    "exact title paper about acoustics": [{"title": ["Exact Title Paper About Acoustics"], "DOI": "10.2/exact",
                                           "container-title": ["Lab on a Chip"], "author": [{"family": "Lee"}],
                                           "issued": {"date-parts": [[2021]]}}],
    "similar title paper about lice": [{"title": ["A Different Paper About Lice Genomes"], "DOI": "10.2/other",
                                        "container-title": ["Wrong Journal"], "author": [{"family": "Kim"}],
                                        "issued": {"date-parts": [[2020]]}}],
    "same title different author": [{"title": ["Same Title Different Author"], "DOI": "10.2/sameauthor",
                                     "container-title": ["Some Journal"], "author": [{"family": "Zhou"}],
                                     "issued": {"date-parts": [[2022]]}}],
}


class Fake(BaseHTTPRequestHandler):
    def log_message(self, *a):  # quiet
        pass

    def do_GET(self):
        u = urlparse(self.path)
        if u.path.startswith("/works/"):
            msg = DOI_RECORDS.get(unquote(u.path[len("/works/"):]).lower())
            body = {"message": msg} if msg else None
        else:
            q = parse_qs(u.query).get("query.bibliographic", [""])[0].lower()
            body = {"message": {"items": SEARCH.get(q, [])}}
        self.send_response(200 if body else 404)
        self.end_headers()
        self.wfile.write(json.dumps(body or {}).encode())


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  {'✓' if cond else '✗'} {name}" + (f"\n      {detail}" if not cond and detail else ""))


def paper(**kw):
    base = dict(title="T", authors=["A B"], venue="", year=2024, doi=None, arxiv_id=None, url=None,
                pdf_url=None, citations=1, abstract="x")
    base.update(kw)
    return base


srv = HTTPServer(("127.0.0.1", 0), Fake)
threading.Thread(target=srv.serve_forever, daemon=True).start()
env = {**os.environ, "CROSSREF_API_BASE": f"http://127.0.0.1:{srv.server_port}/works/"}

papers = {
    "doi": paper(title="Paper With Doi", authors=["J Smith"], doi="10.1/withdoi", year=2023),
    "title": paper(title="Exact Title Paper About Acoustics", authors=["K Lee"], year=2021),
    "near": paper(title="Similar Title Paper About Lice", authors=["M Kim"], year=2020),
    "author": paper(title="Same Title Different Author", authors=["P Wang"], year=2022),
    "hasvenue": paper(title="Already Has Venue Here", venue="Nature", year=2020),
    "arxiv": paper(title="An Arxiv Preprint Paper", arxiv_id="2401.00001", year=2024),
    "uncited": paper(title="Exact Title Paper About Acoustics Uncited Copy", authors=["K Lee"], year=2021),
}
keys = {k: mint_key(p) for k, p in papers.items()}

with tempfile.TemporaryDirectory() as td:
    td = Path(td)
    (td / "f.json").write_text(json.dumps({"papers": list(papers.values()), "stats": {}}))
    subprocess.run([sys.executable, str(SCRIPT), "add", "--from-search", "f.json", "--ledger", "l.jsonl"],
                   cwd=td, capture_output=True, text=True, env=env, check=True)
    cited = [k for n, k in keys.items() if n != "uncited"]
    (td / "d.md").write_text("# T\n\n## S\n" + " ".join(f"Claim [{k}]." for k in cited) + "\n")
    r = subprocess.run([sys.executable, str(SCRIPT), "fill", "--draft", "d.md", "--ledger", "l.jsonl"],
                       cwd=td, capture_output=True, text=True, env=env)
    print("[fill]", r.stderr.strip().splitlines()[-1] if r.stderr.strip() else "")
    led = Ledger.load(td / "l.jsonl").active()
    rec = {n: led[k].record for n, k in keys.items()}

    check("DOI record gets its CrossRef venue", rec["doi"].get("venue") == "Journal of Tests", rec["doi"])
    check("title search fills venue on title+author+year match", rec["title"].get("venue") == "Lab on a Chip", rec["title"])
    check("title search adds the matched DOI", rec["title"].get("doi") == "10.2/exact", rec["title"])
    check("a merely similar title is rejected", not rec["near"].get("venue"), rec["near"])
    check("same title, different first author is rejected", not rec["author"].get("venue"), rec["author"])
    check("an existing venue is left alone", rec["hasvenue"].get("venue") == "Nature")
    check("arXiv records are skipped", not rec["arxiv"].get("venue"))
    check("uncited entries are not touched", not rec["uncited"].get("venue"))
    log = [json.loads(x) for x in (td / "l.jsonl").read_text().splitlines()]
    revs = [e for e in log if e.get("event") == "revise"]
    check("exactly two revise events", len(revs) == 2, [e["key"] for e in revs])
    check("each revise keeps the old value and names CrossRef",
          all("superseded" in e and e["provenance"]["source"].startswith("crossref") for e in revs))
    r = subprocess.run([sys.executable, str(SCRIPT), "render", "--draft", "d.md", "--ledger", "l.jsonl", "--out", "o.md"],
                       cwd=td, capture_output=True, text=True, env=env)
    out = (td / "o.md").read_text()
    check("render shows the filled venues", "Journal of Tests" in out and "Lab on a Chip" in out)
    check("unfilled entries still say [venue unavailable]", out.count("[venue unavailable]") == 2, out)

srv.shutdown()
print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
sys.exit(1 if FAIL else 0)
