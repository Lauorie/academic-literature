#!/usr/bin/env python3
"""Verify survey reference lists against CrossRef, OpenAlex, DBLP and arXiv (citation_integrity/PROTOCOL.md).

Steps per survey: split the reference list into entries, sample at most 40 (seed = int(topic id)), extract fields
with an LLM (copy only), look each entry up deterministically, and classify it as verified / metadata_error /
not_found / unparseable. Writes one JSON per survey: <out>/<cond>/<tid>.json.
Usage: verify_refs.py --cond NAME --runs DIR [--only 001,002] --out DIR
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import logging
import os
import random
import re
import sqlite3
import threading
import time
import unicodedata
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)

GATEWAY = "https://aigateway.paperbypass.com/api/v1/chat/completions"
EXTRACT_MODEL = "qwen/qwen3-30b-a3b-instruct-2507"
MAX_ENTRIES = 40
TITLE_RATIO = 0.90
CACHE = Path(__file__).resolve().parent / "http_cache.sqlite"
MIN_INTERVAL = {"crossref": 0.2, "openalex": 0.12, "dblp": 1.0, "arxiv": 0.2}  # seconds between requests per source
EXTRACT_PROMPT = """Extract bibliographic fields from this reference-list entry. Copy them exactly as written; do not correct, complete or guess anything. Use null for a field that is absent.
Return only JSON: {{"title": str|null, "authors": [each author's full name exactly as written, one string per person, in order], "year": int|null, "doi": str|null, "arxiv_id": str|null}}
Do not include "et al." as an author.
A DOI or arXiv identifier that appears inside a URL counts as present.

Entry:
{entry}"""


class Http:
    """Cached, per-source rate-limited GET."""

    def __init__(self) -> None:
        self.db = sqlite3.connect(CACHE, check_same_thread=False)
        self.db.execute("CREATE TABLE IF NOT EXISTS c (k TEXT PRIMARY KEY, status INT, body TEXT)")
        self.lock = threading.Lock()
        self.src_locks = {s: threading.Lock() for s in MIN_INTERVAL}
        self.last = {s: 0.0 for s in MIN_INTERVAL}

    def get(self, src: str, url: str) -> Optional[str]:
        k = hashlib.sha256(url.encode()).hexdigest()
        with self.lock:
            row = self.db.execute("SELECT status, body FROM c WHERE k=?", (k,)).fetchone()
        if row:
            return row[1] if row[0] == 200 else None
        for attempt in range(8):
            with self.src_locks[src]:
                wait = self.last[src] + MIN_INTERVAL[src] - time.time()
                if wait > 0:
                    time.sleep(wait)
                self.last[src] = time.time()
            try:
                r = requests.get(url, timeout=60, headers={"User-Agent": "citation-integrity-check/1.0"})
            except requests.RequestException as exc:
                logger.warning("%s %s: %s", src, url[:80], exc)
                time.sleep(5 * (attempt + 1))
                continue
            if r.status_code in (429, 500, 502, 503, 504) or r.text.lstrip()[:15].lower() == "<!doctype html>":
                # Rate limit, server error, or a bot-challenge page served with status 200: never cache it.
                time.sleep(min(60 * (attempt + 1), 300) if r.status_code == 429 else 10 * (attempt + 1))
                continue
            with self.lock:
                self.db.execute("INSERT OR REPLACE INTO c VALUES (?,?,?)", (k, r.status_code, r.text))
                self.db.commit()
            return r.text if r.status_code == 200 else None
        raise RuntimeError(f"{src} unavailable after retries: {url[:100]}")


def norm(s: Any) -> str:
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def surname(name: str) -> str:
    """Family name: the part before a comma ('Lin, Q.'), else the last token ('Q Lin', 'Shahul Es'),
    unless the last token is an initial ('Lin Q', 'Lin QY'), then the first token."""
    if "," in name:
        toks = norm(name.split(",")[0]).split()
        return toks[-1] if toks else ""
    toks = norm(name).split()
    if not toks:
        return ""
    if len(toks) > 1 and len(toks[-1]) <= 2 and name.strip().split()[-1].replace(".", "").isupper():
        return toks[0]
    return toks[-1]


def split_entries(md: str) -> List[str]:
    parts = re.split(r"^#{1,6}\s*References\s*$", md, maxsplit=1, flags=re.M | re.I)
    if len(parts) < 2:
        return []
    entries: List[str] = []
    for line in parts[1].splitlines():
        if re.match(r"^\s*(\[\d+\]|\d+[.)]|[-*])\s+", line):
            entries.append(line.strip())
        elif line.strip() and entries and not line.startswith("#"):
            entries[-1] += " " + line.strip()
        elif line.startswith("#"):
            break
    return entries


def extract(entry: str, token: str) -> Dict[str, Any]:
    for _ in range(3):
        r = requests.post(GATEWAY, headers={"Authorization": f"Bearer {token}"}, timeout=300,
                          json={"model": EXTRACT_MODEL, "temperature": 0, "max_tokens": 600,
                                "messages": [{"role": "user", "content": EXTRACT_PROMPT.format(entry=entry)}]})
        if r.status_code != 200:
            time.sleep(5)
            continue
        text = r.json()["choices"][0]["message"].get("content") or ""
        m = re.search(r"\{.*\}", text, re.S)
        try:
            return json.loads(m.group(0)) if m else {}
        except json.JSONDecodeError:
            continue
    return {}


def cands_crossref(http: Http, title: str = "", doi: str = "") -> List[Dict[str, Any]]:
    url = (f"https://api.crossref.org/works/{urllib.parse.quote(doi)}" if doi else
           "https://api.crossref.org/works?rows=5&query.bibliographic=" + urllib.parse.quote(title))
    body = http.get("crossref", url)
    if not body:
        return []
    msg = json.loads(body)["message"]
    items = [msg] if doi else msg.get("items", [])
    out = []
    for it in items:
        dp = (it.get("issued") or {}).get("date-parts") or [[None]]
        out.append({"src": "crossref", "title": " ".join(it.get("title") or []),
                    "authors": [a.get("family") or a.get("name") or "" for a in it.get("author") or []],
                    "year": dp[0][0] if dp and dp[0] else None})
    return out


def cands_openalex(http: Http, title: str) -> List[Dict[str, Any]]:
    body = http.get("openalex", "https://api.openalex.org/works?per-page=5&search=" + urllib.parse.quote(title))
    if not body:
        return []
    return [{"src": "openalex", "title": w.get("title") or "", "year": w.get("publication_year"),
             "authors": [((a.get("author") or {}).get("display_name") or "") for a in w.get("authorships") or []]}
            for w in json.loads(body).get("results", [])]


def cands_dblp(http: Http, title: str) -> List[Dict[str, Any]]:
    body = http.get("dblp", "https://dblp.org/search/publ/api?format=json&h=5&q=" + urllib.parse.quote(title))
    if not body:
        return []
    hits = (((json.loads(body).get("result") or {}).get("hits") or {}).get("hit")) or []
    out = []
    for h in hits:
        info = h.get("info", {})
        au = (info.get("authors") or {}).get("author") or []
        au = au if isinstance(au, list) else [au]
        out.append({"src": "dblp", "title": info.get("title", ""), "year": int(info["year"]) if info.get("year") else None,
                    "authors": [re.sub(r"\s\d{4}$", "", a.get("text", "")) for a in au]})
    return out


def cands_arxiv(http: Http, title: str = "", aid: str = "") -> List[Dict[str, Any]]:
    """arXiv records through DataCite, the registry of arXiv DOIs (10.48550/arXiv.<id>); the arXiv API itself
    answered HTTP 429 to every request on 2026-10-02 (PROTOCOL Deviations)."""
    if aid:
        url = "https://api.datacite.org/dois/10.48550/arXiv." + urllib.parse.quote(aid)
    else:
        url = ("https://api.datacite.org/dois?client-id=arxiv.content&page%5Bsize%5D=5&query="
               + urllib.parse.quote("titles.title:(" + norm(title) + ")"))
    body = http.get("arxiv", url)
    if not body:
        return []
    data = json.loads(body)["data"]
    out = []
    for d in [data] if aid else data:
        a = d.get("attributes", {})
        out.append({"src": "arxiv", "title": ((a.get("titles") or [{}])[0]).get("title", ""),
                    "year": a.get("publicationYear"),
                    "authors": [c.get("familyName") or c.get("name") or "" for c in a.get("creators") or []]})
    return out


def title_ok(a: str, b: str) -> bool:
    return difflib.SequenceMatcher(None, norm(a), norm(b)).ratio() >= TITLE_RATIO


def full_ok(f: Dict[str, Any], c: Dict[str, Any]) -> bool:
    first = surname(f["authors"][0]) if f.get("authors") else ""
    a_ok = not first or first in {surname(x) for x in c["authors"][:3]}
    y_ok = not f.get("year") or not c.get("year") or abs(int(f["year"]) - int(c["year"])) <= 1
    return a_ok and y_ok


def keep_written_ids(f: Dict[str, Any], entry: str) -> Dict[str, Any]:
    """Drop an extracted DOI or arXiv id that does not appear verbatim in the entry: the extractor
    sometimes builds a DOI from a publisher URL (PROTOCOL Deviations, v3)."""
    out = dict(f or {})
    low = entry.lower()
    for key, pre in (("doi", r"^(https?://doi\.org/|doi:)"), ("arxiv_id", r"^arxiv:")):
        val = re.sub(pre, "", str(out.get(key) or "").strip(), flags=re.I)
        core = re.sub(r"v\d+$", "", val) if key == "arxiv_id" else val
        if core and core.lower() not in low:
            out[key] = None
    return out


def classify(f: Dict[str, Any], http: Http) -> Dict[str, Any]:
    title = (f.get("title") or "").strip()
    if len(title.split()) < 3:
        return {"class": "unparseable"}
    doi = (f.get("doi") or "").strip().removeprefix("https://doi.org/").removeprefix("doi:") or None
    aid = re.sub(r"v\d+$", "", (f.get("arxiv_id") or "").strip().removeprefix("arXiv:")) or None
    m = re.fullmatch(r"10\.48550/arxiv\.(.+)", doi or "", re.I)
    if m:  # arXiv DOIs are DataCite DOIs, absent from CrossRef: resolve them as arXiv ids
        doi, aid = None, aid or m.group(1)
    id_cands = (cands_crossref(http, doi=doi) if doi else []) + (cands_arxiv(http, aid=aid) if aid else [])
    id_mismatch = bool(id_cands) and not any(title_ok(title, c["title"]) for c in id_cands)
    seen = [c for c in id_cands if title_ok(title, c["title"])]
    for src in ("crossref", "arxiv"):  # DBLP and OpenAlex dropped: bot challenge / exhausted quota (PROTOCOL Deviations)
        if any(full_ok(f, c) for c in seen):
            break  # verified already; the identifier check has run, so later sources cannot change the class
        found = {"crossref": cands_crossref, "openalex": cands_openalex,
                 "dblp": cands_dblp, "arxiv": cands_arxiv}[src](http, title)
        seen += [c for c in found if title_ok(title, c["title"])]
    if not seen:
        return {"class": "not_found", "id_mismatch": id_mismatch}
    full = [c for c in seen if full_ok(f, c)]
    cls = "verified" if full and not id_mismatch else "metadata_error"
    best = (full or seen)[0]
    return {"class": cls, "id_mismatch": id_mismatch, "match": {k: best[k] for k in ("src", "title", "year")},
            "match_authors": best["authors"][:3]}


def verify_survey(cond: str, tid: str, md_path: Path, out: Path, http: Http, token: str) -> None:
    dest = out / cond / f"{tid}.json"
    if dest.exists():
        return
    entries = split_entries(md_path.read_text())
    idx = list(range(len(entries)))
    if len(idx) > MAX_ENTRIES:
        idx = sorted(random.Random(int(re.sub(r"\D", "", tid))).sample(idx, MAX_ENTRIES))  # "sl003" -> 3
    rows = []
    for i in idx:
        f = keep_written_ids(extract(entries[i], token), entries[i])
        rows.append({"i": i, "entry": entries[i], "fields": f, **classify(f, http)})
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps({"cond": cond, "tid": tid, "n_entries": len(entries), "checked": rows},
                               ensure_ascii=False, indent=1))
    counts: Dict[str, int] = {}
    for r in rows:
        counts[r["class"]] = counts.get(r["class"], 0) + 1
    logger.info("%s %s: %d entries, checked %d: %s", cond, tid, len(entries), len(rows), counts)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cond", required=True)
    ap.add_argument("--runs", type=Path, required=True, help="dir of <tid>/review/literature.md")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--only", default="")
    ap.add_argument("--parallel", type=int, default=6)
    args = ap.parse_args()
    token = os.environ["PAPERBYPASS_AUTH_TOKEN"]
    http = Http()
    tids = sorted(p.name for p in args.runs.iterdir()
                  if re.fullmatch(r"(sl)?\d{3}", p.name) and (p / "review" / "literature.md").exists())  # skips archived runs
    if args.only:
        tids = [t for t in tids if t in set(args.only.split(","))]
    with ThreadPoolExecutor(args.parallel) as ex:
        futs = [ex.submit(verify_survey, args.cond, t, args.runs / t / "review" / "literature.md", args.out, http, token)
                for t in tids]
        failed = 0
        for fu in futs:
            try:
                fu.result()
            except RuntimeError as exc:  # a source stayed unavailable: no result is written, the next pass redoes it
                failed += 1
                logger.error("survey skipped this pass: %s", exc)
    logger.info("pass done: %d surveys skipped", failed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
