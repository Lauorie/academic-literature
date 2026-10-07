#!/usr/bin/env python3
"""Find and fetch open-access full text for ledger entries -- the routes WisDoc alone misses.

    locate  --ledger L (--keys k1 k2 ... | --manifest manifest.tsv [--tier core])   TSV: key, route, url
    epmc    --pmcid PMC1234567 --out <dir>/<key>.md                                 Europe PMC full text -> Markdown

Routes, in order: an arXiv id (PDF via arxiv.org, parse with WisDoc); Europe PMC's open-access subset, found by
DOI or, failing that, an exact title match (fetched as JATS XML and converted here, no WisDoc queue); a
search-result `pdf_url` ending in .pdf (WisDoc; publisher links often refuse scripted downloads). `none` means no open route was found: the paper stays abstract-only
unless the user supplies the PDF. Nothing is guessed: every URL comes from the ledger record or Europe PMC's answer.
Only dependency: requests.
"""
from __future__ import annotations

import argparse
import csv
import os
import re
import sys
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
from citation_ledger import Ledger, _arxiv_of, _doi_of, _norm_text  # noqa: E402

EPMC = os.environ.get("EUROPEPMC_API_BASE", "https://www.ebi.ac.uk/europepmc/webservices/rest")


def _get(url: str, params: Optional[dict] = None):
    import requests

    for attempt in range(4):
        try:
            r = requests.get(url, params=params, timeout=30, headers={"User-Agent": "academic-literature-skill/1.0"})
        except requests.RequestException:
            r = None
        if r is not None and r.status_code not in (429, 500, 502, 503, 504):
            return r
        time.sleep(2 ** attempt)
    return None


def _epmc_hit(rec: dict) -> Optional[str]:
    """PMCID of the record in Europe PMC's open-access subset, or None."""
    doi = _doi_of(rec)
    title = (rec.get("title") or "").strip()
    queries = [f'DOI:"{doi}"'] if doi else []
    if len(title.split()) >= 4:
        queries.append(f'TITLE:"{title}"')
    for q in queries:
        r = _get(f"{EPMC}/search", {"query": q, "format": "json", "resultType": "lite", "pageSize": 5})
        if r is None or r.status_code != 200:
            continue
        for hit in r.json().get("resultList", {}).get("result", []):
            same = (doi and (hit.get("doi") or "").lower() == doi.lower()) or \
                   (_norm_text(hit.get("title") or "") == _norm_text(title))
            if same and hit.get("isOpenAccess") == "Y" and hit.get("pmcid"):
                return hit["pmcid"]
    return None


def locate_one(key: str, rec: dict) -> Tuple[str, str, str]:
    if aid := _arxiv_of(rec):
        return key, "arxiv", f"https://arxiv.org/pdf/{aid}.pdf"
    # Europe PMC before a search-result pdf_url: an open-access PMC copy downloads; a publisher PDF link often 403s.
    if pmcid := _epmc_hit(rec):
        return key, "europepmc", pmcid
    pdf = (rec.get("pdf_url") or "").strip()
    if pdf.lower().split("?")[0].endswith(".pdf"):
        return key, "pdf_url", pdf
    return key, "none", ""


def cmd_locate(args: argparse.Namespace) -> int:
    active = Ledger.load(Path(args.ledger)).active()
    keys: List[str] = list(args.keys or [])
    if args.manifest:
        with open(args.manifest, newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh, delimiter="\t"))
        kcol = next((c for c in (rows[0].keys() if rows else []) if c.lower() in ("key", "ledger_key")), None)
        tcol = next((c for c in (rows[0].keys() if rows else []) if c.lower() == "tier"), None)
        if not kcol:
            sys.stderr.write("manifest needs a 'key' column\n")
            return 2
        keys += [r[kcol].strip() for r in rows if not args.tier or (tcol and r[tcol].strip().lower() == args.tier)]
    keys = [k for k in dict.fromkeys(keys) if k in active]
    with ThreadPoolExecutor(4) as pool:
        found = list(pool.map(lambda k: locate_one(k, active[k].record), keys))
    print("key\troute\turl")
    for row in found:
        print("\t".join(row))
    n = {r: sum(1 for _, x, _ in found if x == r) for r in ("arxiv", "pdf_url", "europepmc", "none")}
    sys.stderr.write(f"locate: {len(found)} keys; arxiv {n['arxiv']}, pdf_url {n['pdf_url']}, "
                     f"europepmc {n['europepmc']}, none {n['none']}\n")
    return 0


def _text(el: Optional[ET.Element]) -> str:
    return re.sub(r"\s+", " ", "".join(el.itertext())).strip() if el is not None else ""


def jats_to_markdown(xml: str) -> str:
    """Title, abstract, section headings and paragraphs, figure/table captions. References are left out:
    they are not evidence, and the ledger is the review's bibliography."""
    root = ET.fromstring(xml)
    out = [f"# {_text(root.find('.//article-meta//article-title'))}", ""]
    for ab in root.findall(".//article-meta/abstract"):
        out += ["## Abstract", "", *[_text(p) for p in ab.iter("p")], ""]

    def walk(sec: ET.Element, depth: int) -> None:
        title = _text(sec.find("title"))
        if title:
            out.extend(["#" * min(depth, 6) + " " + title, ""])
        for child in sec:
            if child.tag == "p":
                out.extend([_text(child), ""])
            elif child.tag == "sec":
                walk(child, depth + 1)
            elif child.tag in ("fig", "table-wrap"):
                cap = _text(child.find("caption"))
                label = _text(child.find("label"))
                if cap:
                    out.extend([f"*{label} {cap}*".replace("* ", "*", 1), ""])

    body = root.find(".//body")
    if body is not None:
        for sec in body:
            if sec.tag == "sec":
                walk(sec, 2)
            elif sec.tag == "p":
                out.extend([_text(sec), ""])
    return "\n".join(out).strip() + "\n"


def cmd_epmc(args: argparse.Namespace) -> int:
    pmcid = args.pmcid if args.pmcid.upper().startswith("PMC") else f"PMC{args.pmcid}"
    r = _get(f"{EPMC}/{pmcid}/fullTextXML")
    if r is None or r.status_code != 200 or not r.text.lstrip().startswith("<"):
        sys.stderr.write(f"Europe PMC has no open full text for {pmcid} (HTTP {getattr(r, 'status_code', 'none')})\n")
        return 1
    md = jats_to_markdown(r.text)
    if len(md.split()) < 300:
        sys.stderr.write(f"{pmcid}: full text too short ({len(md.split())} words); treat as abstract-only\n")
        return 1
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md, encoding="utf-8")
    print(f'{{"markdown_path": "{out}", "words": {len(md.split())}, "source": "europepmc {pmcid}"}}')
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("locate", help="find an open full-text route for ledger keys")
    p.add_argument("--ledger", required=True)
    p.add_argument("--keys", nargs="*")
    p.add_argument("--manifest")
    p.add_argument("--tier", help="only manifest rows with this tier, e.g. core")
    p.set_defaults(fn=cmd_locate)
    p = sub.add_parser("epmc", help="fetch Europe PMC open-access full text as Markdown")
    p.add_argument("--pmcid", required=True)
    p.add_argument("--out", required=True)
    p.set_defaults(fn=cmd_epmc)
    args = ap.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
