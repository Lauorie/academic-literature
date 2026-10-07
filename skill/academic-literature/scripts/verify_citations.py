#!/usr/bin/env python3
"""
Citation verification for literature reviews.

Extracts every DOI from a finished review (markdown), checks that each one
actually resolves via doi.org, and pulls the CrossRef metadata so you can
confirm the DOI points at the paper you think it does. This is the empirical
backstop against fabricated or mis-attributed citations: a DOI that fails to
resolve, or resolves to a different title than what the review claims, is a
red flag to fix before the review goes out.

Only dependency: requests.

Usage:
    python verify_citations.py <review.md>

Exit code is non-zero if any DOI fails to resolve, so a caller/agent notices
rather than assuming everything checked out.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from typing import Dict, List, Tuple

import requests

# Public scholarly APIs with single canonical hosts (not secrets, not internal
# (env, region) infrastructure) — so naming them does not carry the routing
# hazard the "no hardcoded hosts" rule targets. Each stays env-overridable (with
# the canonical default) so a locked-down region can point at a mirror/proxy
# without a code change.
DOI_RESOLVER = os.environ.get("DOI_RESOLVER_BASE", "https://doi.org/api/handles/")
CROSSREF_WORKS = os.environ.get("CROSSREF_API_BASE", "https://api.crossref.org/works/")
ARXIV_API = os.environ.get("ARXIV_API_BASE", "https://export.arxiv.org/api/query")

# arXiv DOIs (registrant 10.48550) are registered with DataCite, not CrossRef, so
# CrossRef answers 404 for every one of them. Asking only CrossRef therefore
# yields no title to compare against — the "does this DOI point at the paper the
# review claims?" check silently does nothing for arXiv entries, which in an ML
# review are often most of the references. Route those to arXiv instead.
ARXIV_DOI_RE = re.compile(r"^10\.48550/arxiv\.(.+)$", re.I)


class CitationVerifier:
    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update(
            {"User-Agent": "academic-literature-skill/1.0 (citation verifier)"}
        )

    def extract_dois(self, text: str) -> List[str]:
        """Pull every DOI out of the text, de-duplicated, order preserved."""
        doi_pattern = r"10\.\d{4,}/[^\s\]\)\"<>]+"
        seen: Dict[str, None] = {}
        for raw in re.findall(doi_pattern, text):
            doi = raw.rstrip(".,;)")  # strip trailing punctuation from prose
            if doi not in seen:
                seen[doi] = None
        return list(seen)

    def verify_doi(self, doi: str) -> Tuple[bool, Dict]:
        """Return (resolves, crossref_metadata)."""
        try:
            resp = self.session.get(DOI_RESOLVER + doi, timeout=10)
            if resp.status_code == 200:
                return True, self._get_crossref_metadata(doi)
            return False, {}
        except requests.RequestException as e:
            return False, {"error": str(e)}

    def _get_arxiv_metadata(self, arxiv_id: str) -> Dict:
        """Authoritative title/authors for an arXiv paper, straight from arXiv."""
        try:
            resp = self.session.get(
                ARXIV_API, params={"id_list": arxiv_id, "max_results": 1}, timeout=15
            )
            if resp.status_code != 200:
                return {}
            entry = re.search(r"<entry>(.*?)</entry>", resp.text, re.S)
            if not entry:
                return {}
            body = entry.group(1)
            title = re.search(r"<title>(.*?)</title>", body, re.S)
            names = re.findall(r"<name>(.*?)</name>", body)
            published = re.search(r"<published>(\d{4})", body)
            return {
                "title": re.sub(r"\s+", " ", title.group(1)).strip() if title else "",
                "authors": ", ".join(names[:3]) + (", et al." if len(names) > 3 else ""),
                "year": published.group(1) if published else "",
                "journal": "arXiv preprint",
                "volume": "",
                "pages": "",
                "doi": f"10.48550/arXiv.{arxiv_id}",
            }
        except (requests.RequestException, ValueError) as e:
            return {"error": str(e)}

    def _get_crossref_metadata(self, doi: str) -> Dict:
        if m := ARXIV_DOI_RE.match(doi):
            return self._get_arxiv_metadata(m.group(1))
        try:
            resp = self.session.get(CROSSREF_WORKS + doi, timeout=10)
            if resp.status_code != 200:
                return {}
            msg = resp.json().get("message", {})
            return {
                "title": (msg.get("title") or [""])[0],
                "authors": self._format_authors(msg.get("author", [])),
                "year": self._extract_year(msg),
                "journal": (msg.get("container-title") or [""])[0],
                "volume": msg.get("volume", ""),
                "pages": msg.get("page", ""),
                "doi": doi,
            }
        except (requests.RequestException, ValueError) as e:
            return {"error": str(e)}

    @staticmethod
    def _format_authors(authors: List[Dict]) -> str:
        formatted = []
        for a in authors[:3]:
            given, family = a.get("given", ""), a.get("family", "")
            if family:
                formatted.append(f"{family}, {given[0]}." if given else family)
        if len(authors) > 3:
            formatted.append("et al.")
        return ", ".join(formatted)

    @staticmethod
    def _extract_year(msg: Dict) -> str:
        for key in ("published-print", "published-online", "issued"):
            parts = msg.get(key, {}).get("date-parts", [[]])
            if parts and parts[0]:
                return str(parts[0][0])
        return ""

    def verify_file(self, filepath: str) -> Dict:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        dois = self.extract_dois(content)
        report: Dict = {"total_dois": len(dois), "verified": [], "failed": [], "metadata": {}}

        for doi in dois:
            sys.stderr.write(f"Verifying DOI: {doi}\n")
            ok, meta = self.verify_doi(doi)
            if ok:
                report["verified"].append(doi)
                report["metadata"][doi] = meta
            else:
                report["failed"].append(doi)
            time.sleep(0.5)  # be polite to the public APIs

        return report


def main() -> None:
    if len(sys.argv) < 2:
        sys.stderr.write("Usage: python verify_citations.py <review.md>\n")
        sys.exit(2)

    filepath = sys.argv[1]
    verifier = CitationVerifier()
    sys.stderr.write(f"Verifying citations in: {filepath}\n")
    report = verifier.verify_file(filepath)

    print("=" * 60)
    print("CITATION VERIFICATION REPORT")
    print("=" * 60)
    print(f"Total DOIs found: {report['total_dois']}")
    print(f"Resolved:         {len(report['verified'])}")
    print(f"FAILED:           {len(report['failed'])}")

    if report["failed"]:
        print("\n⚠️  DOIs that did NOT resolve (fix or remove before finalizing):")
        for doi in report["failed"]:
            print(f"  - {doi}")

    if report["metadata"]:
        # Print the CrossRef-resolved title next to each DOI so the caller can
        # spot a DOI that resolves but points at a *different* paper than the
        # review claims — a subtle but real form of mis-citation.
        print("\nResolved DOIs (compare each title against what the review says):")
        for doi, meta in report["metadata"].items():
            title = meta.get("title", "") or "(no CrossRef title)"
            year = meta.get("year", "")
            journal = meta.get("journal", "")
            print(f"  - {doi}")
            print(f"      → {title} ({year}) {journal}".rstrip())

    out = filepath.rsplit(".md", 1)[0] + "_citation_report.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\nDetailed report saved to: {out}")

    # Non-zero exit if anything failed, so an agent/CI notices.
    sys.exit(1 if report["failed"] else 0)


if __name__ == "__main__":
    main()
