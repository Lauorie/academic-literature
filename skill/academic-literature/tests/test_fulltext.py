#!/usr/bin/env python3
"""Tests for fulltext.py: routes come from the ledger record or Europe PMC's answer, never guessed.

A local HTTP server stands in for Europe PMC (EUROPEPMC_API_BASE points at it), so the tests run offline.
"""
import json
import os
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
from citation_ledger import mint_key  # noqa: E402

PASS, FAIL = [], []
BODY = " ".join(["Body sentence about lice genomes and vectors."] * 80)
JATS = f"""<article><front><article-meta><title-group><article-title>Open Paper On Lice</article-title></title-group>
<abstract><p>An abstract.</p></abstract></article-meta></front>
<body><sec><title>Introduction</title><p>{BODY}</p><sec><title>Sub</title><p>More text.</p></sec>
<fig><label>Figure 1</label><caption><p>A louse.</p></caption></fig></sec></body>
<back><ref-list><ref><mixed-citation>Should not appear</mixed-citation></ref></ref-list></back></article>"""
HITS = {
    'DOI:"10.5/open"': [{"doi": "10.5/open", "title": "Open Paper On Lice", "isOpenAccess": "Y", "pmcid": "PMC111"}],
    'DOI:"10.5/closed"': [{"doi": "10.5/closed", "title": "Closed Paper", "isOpenAccess": "N", "pmcid": "PMC222"}],
    'TITLE:"Exact Title Only Paper Here"': [{"title": "Exact Title Only Paper Here", "isOpenAccess": "Y", "pmcid": "PMC333"}],
    'TITLE:"Near Title Paper About Things"': [{"title": "Near Title Paper About Other Things", "isOpenAccess": "Y", "pmcid": "PMC444"}],
}


class Fake(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        u = urlparse(self.path)
        if u.path.endswith("/search"):
            q = parse_qs(u.query)["query"][0]
            body, code, ctype = json.dumps({"resultList": {"result": HITS.get(q, [])}}), 200, "application/json"
        elif u.path.endswith("/PMC111/fullTextXML"):
            body, code, ctype = JATS, 200, "application/xml"
        elif u.path.endswith("/PMC999/fullTextXML"):
            body, code, ctype = "<article><body><p>too short</p></body></article>", 200, "application/xml"
        else:
            body, code, ctype = "", 404, "text/plain"
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.end_headers()
        self.wfile.write(body.encode())


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  {'✓' if cond else '✗'} {name}" + (f"\n      {detail}" if not cond and detail else ""))


def paper(**kw):
    base = dict(title="T", authors=["A B"], venue="V", year=2020, doi=None, arxiv_id=None, url=None, pdf_url=None,
                citations=1, abstract="x")
    base.update(kw)
    return base


srv = HTTPServer(("127.0.0.1", 0), Fake)
threading.Thread(target=srv.serve_forever, daemon=True).start()
env = {**os.environ, "EUROPEPMC_API_BASE": f"http://127.0.0.1:{srv.server_port}"}
P = {"arxiv": paper(title="An Arxiv Paper On Agents", arxiv_id="2401.00001"),
     "open": paper(title="Open Paper On Lice", doi="10.5/open", pdf_url="https://publisher.example/x.pdf"),
     "closed_pdf": paper(title="Closed Paper", doi="10.5/closed", pdf_url="https://publisher.example/closed.pdf"),
     "title": paper(title="Exact Title Only Paper Here"),
     "near": paper(title="Near Title Paper About Things"),
     "nothing": paper(title="Nothing Open About This One", url="https://publisher.example/landing")}
K = {n: mint_key(p) for n, p in P.items()}

with tempfile.TemporaryDirectory() as td:
    td = Path(td)
    (td / "f.json").write_text(json.dumps({"papers": list(P.values()), "stats": {}}))
    subprocess.run([sys.executable, str(SCRIPTS / "citation_ledger.py"), "add", "--from-search", "f.json", "--ledger", "l.jsonl"],
                   cwd=td, capture_output=True, env=env, check=True)
    (td / "m.tsv").write_text("key\ttier\n" + "".join(f"{k}\t{'core' if n != 'nothing' else 'supporting'}\n" for n, k in K.items()))
    r = subprocess.run([sys.executable, str(SCRIPTS / "fulltext.py"), "locate", "--ledger", "l.jsonl", "--keys", *K.values()],
                       cwd=td, capture_output=True, text=True, env=env)
    route = {line.split("\t")[0]: line.split("\t")[1:] for line in r.stdout.strip().splitlines()[1:]}
    check("arXiv id -> arxiv PDF", route[K["arxiv"]] == ["arxiv", "https://arxiv.org/pdf/2401.00001.pdf"], route[K["arxiv"]])
    check("open-access PMC copy preferred over a publisher pdf_url", route[K["open"]] == ["europepmc", "PMC111"], route[K["open"]])
    check("not open access -> falls back to the record's pdf_url", route[K["closed_pdf"]][0] == "pdf_url", route[K["closed_pdf"]])
    check("exact title match finds a PMC copy without a DOI", route[K["title"]] == ["europepmc", "PMC333"], route[K["title"]])
    check("a near title is not accepted", route[K["near"]][0] == "none", route[K["near"]])
    check("no route -> none", route[K["nothing"]][0] == "none", route[K["nothing"]])
    r = subprocess.run([sys.executable, str(SCRIPTS / "fulltext.py"), "locate", "--ledger", "l.jsonl", "--manifest", "m.tsv",
                        "--tier", "core"], cwd=td, capture_output=True, text=True, env=env)
    check("--manifest --tier core selects only core rows", len(r.stdout.strip().splitlines()) - 1 == 5, r.stdout)
    r = subprocess.run([sys.executable, str(SCRIPTS / "fulltext.py"), "epmc", "--pmcid", "PMC111", "--out", "ft/k.md"],
                       cwd=td, capture_output=True, text=True, env=env)
    md = (td / "ft/k.md").read_text() if (td / "ft/k.md").exists() else ""
    check("epmc writes Markdown and reports markdown_path", r.returncode == 0 and '"markdown_path"' in r.stdout, r.stderr)
    check("title, sections, subsections and captions kept",
          "# Open Paper On Lice" in md and "## Introduction" in md and "### Sub" in md and "A louse." in md, md[:300])
    check("reference list left out", "Should not appear" not in md)
    r = subprocess.run([sys.executable, str(SCRIPTS / "fulltext.py"), "epmc", "--pmcid", "PMC999", "--out", "ft/s.md"],
                       cwd=td, capture_output=True, text=True, env=env)
    check("too-short full text is refused (treat as abstract-only)", r.returncode == 1 and not (td / "ft/s.md").exists(), r.stderr)
    r = subprocess.run([sys.executable, str(SCRIPTS / "fulltext.py"), "epmc", "--pmcid", "PMC404", "--out", "ft/n.md"],
                       cwd=td, capture_output=True, text=True, env=env)
    check("no open full text -> exit 1, no file", r.returncode == 1 and not (td / "ft/n.md").exists(), r.stderr)

srv.shutdown()
print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
sys.exit(1 if FAIL else 0)
