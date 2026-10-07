#!/usr/bin/env python3
"""Analysis B of skillrefine/PAPER_ANALYSES.md: citation integrity of v3 vs v1 on the 26 held-out surveys."""
import glob
import hashlib
import json
import re
import sqlite3
import statistics as st
import sys
import urllib.parse

sys.path.insert(0, "tools")
from analyze_paper import bootstrap_ci  # noqa: E402

H = "citation_integrity"
db = sqlite3.connect(f"{H}/http_cache.sqlite")


def status(url):
    r = db.execute("select status from c where k=?", (hashlib.sha256(url.encode()).hexdigest(),)).fetchone()
    return r[0] if r else None


def rates(path):
    d = json.load(open(path))
    rows = [r for r in d["checked"] if r["class"] != "unparseable"]
    if not rows:
        return None
    bad_id = 0
    for r in rows:
        fl = r["fields"] or {}
        doi = (fl.get("doi") or "").strip().removeprefix("https://doi.org/").removeprefix("doi:") or None
        aid = re.sub(r"v\d+$", "", (fl.get("arxiv_id") or "").strip().removeprefix("arXiv:")) or None
        m = re.fullmatch(r"10\.48550/arxiv\.(.+)", doi or "", re.I)
        if m:
            doi, aid = None, aid or m.group(1)
        urls = ([f"https://api.crossref.org/works/{urllib.parse.quote(doi)}"] if doi else []) + \
               ([f"https://api.datacite.org/dois/10.48550/arXiv.{urllib.parse.quote(aid)}"] if aid else [])
        dead = any((s := status(u)) is not None and s != 200 for u in urls)
        bad_id += dead or bool(r.get("id_mismatch"))
    n = len(rows)
    return {"defective": sum(r["class"] in ("metadata_error", "not_found") for r in rows) / n,
            "metadata_error": sum(r["class"] == "metadata_error" for r in rows) / n,
            "not_found": sum(r["class"] == "not_found" for r in rows) / n, "bad_id": bad_id / n}


held = json.load(open("skillrefine/heldout.json"))
v3, v1 = {}, {}
for t in held["das"]:
    v3[t] = rates(f"{H}/results_paperB/v3_das/{t}.json")
    v1[t] = rates(f"{H}/results_v3/skill_full/{t}.json")
for t in held["sl"]:
    v3[t] = rates(f"{H}/results_paperB/v3_sl/{t}.json")
    v1[t] = rates(f"{H}/results_paperB/v1_sl/{t}.json")
common = [t for t in v3 if v3[t] and v1.get(t)]
out = {"n": len(common)}
for k in ("defective", "metadata_error", "not_found", "bad_id"):
    d = [v3[t][k] - v1[t][k] for t in common]
    out[k] = {"v3_mean": round(st.mean(v3[t][k] for t in common), 4), "v1_mean": round(st.mean(v1[t][k] for t in common), 4),
              "diff": round(st.mean(d), 4), "ci95": [round(x, 4) for x in bootstrap_ci(d)],
              "v3_lower": sum(x < 0 for x in d), "ties": sum(x == 0 for x in d), "v3_higher": sum(x > 0 for x in d)}
json.dump(out, open("skillrefine/paper_analysis_b.json", "w"), indent=1)
print(json.dumps(out, indent=1))
