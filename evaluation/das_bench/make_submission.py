#!/usr/bin/env python3
"""Turn one academic-literature run into a DAS-Bench submission.

Writes, for a method/topic pair:
  <eval_inputs>/<method>/<tid>.pdf        the rendered survey (pandoc + xelatex, no restyling)
  <eval_inputs>/<method>/ref_<tid>.json   {"<citation number>": "<arXiv id>"} for BSC
  <eval_inputs>/<method>/stats_<tid>.json reference and arXiv-resolution statistics

Citation numbers are re-derived with the skill's own ledger code (first-appearance order),
so they match the [n] markers in literature.md. arXiv ids come from the ledger record
(arxiv_id field, arXiv DOI, or arxiv.org URL); records without one are matched to DAS-2M
by exact normalized title. The survey text itself is never modified.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

SKILL_SCRIPTS = Path.home() / ".claude/skills/academic-literature/scripts"
ARXIV_URL_RE = re.compile(r"arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5})", re.I)
REF_LINE_RE = re.compile(r"^\s*(?:\[(\d+)\]|(\d+)\.)\s+(.*)$")
PANDOC_ARGS = [
    "--pdf-engine=xelatex",
    "-V", "geometry:margin=1in",
    "-V", "fontsize=11pt",
    "-V", "mainfont=DejaVu Serif",
    "-V", "CJKmainfont=Noto Serif CJK SC",
    "-V", "colorlinks=true",
]


def norm_title(title: str) -> str:
    """Lowercase alphanumerics only; the join key against DAS-2M titles."""
    return re.sub(r"[^a-z0-9]", "", (title or "").lower())


def lookup_title(db: Optional[sqlite3.Connection], title: str) -> Optional[str]:
    """Exact normalized-title match; also tries each side without an "ACRONYM:" prefix.

    Only a unique hit counts, and the prefix-stripped variants need >= 20 chars, so a
    short generic title cannot be mapped to the wrong paper.
    """
    if db is None or len(norm_title(title)) < 12:
        return None
    full = norm_title(title)
    tail = norm_title(title.split(":", 1)[1]) if ":" in title else ""
    queries = [("norm_title", full), ("alt_title", full)]
    if len(tail) >= 20:
        queries.append(("norm_title", tail))
    for column, value in queries:
        rows = db.execute(f"SELECT arxiv_id FROM papers WHERE {column} = ?", (value,)).fetchall()
        if len(rows) == 1:
            return rows[0][0]
    return None


def numbered_records(review: Path) -> List[Tuple[int, Dict[str, Any]]]:
    """(number, ledger record) pairs in the order literature.md numbers them."""
    sys.path.insert(0, str(SKILL_SCRIPTS))
    import citation_ledger as cl  # noqa: E402

    draft = (review / "literature.draft.md").read_text(encoding="utf-8")
    ledger = cl.Ledger.load(review / "citations.jsonl")
    active = ledger.active()
    keys = [k for k in cl.collect_keys(draft) if k in active]
    return [(i, active[k].record) for i, k in enumerate(keys, start=1)]


def fallback_records(literature_md: str) -> List[Tuple[int, Dict[str, Any]]]:
    """Parse the References section when no draft/ledger pair exists."""
    refs = re.split(r"^#{1,3}\s*References\s*$", literature_md, flags=re.M | re.I)
    if len(refs) < 2:
        return []
    out: List[Tuple[int, Dict[str, Any]]] = []
    for line in refs[-1].splitlines():
        m = REF_LINE_RE.match(line)
        if not m:
            continue
        text = m.group(3)
        title = re.search(r"\*([^*]{8,})\*", text)
        out.append((int(m.group(1) or m.group(2)), {"title": title.group(1) if title else "", "url": text}))
    return out


def resolve_arxiv(rec: Dict[str, Any], db: Optional[sqlite3.Connection]) -> Tuple[Optional[str], str]:
    sys.path.insert(0, str(SKILL_SCRIPTS))
    import citation_ledger as cl  # noqa: E402

    if arx := cl._arxiv_of(rec):
        return arx, "ledger"
    for field in ("url", "pdf_url", "source_url"):
        if m := ARXIV_URL_RE.search(str(rec.get(field) or "")):
            return m.group(1), "url"
    if arx := lookup_title(db, str(rec.get("title") or "")):
        return arx, "das2m_title"
    return None, "unresolved"


def render_pdf(md_path: Path, pdf_path: Path) -> bool:
    """Render with default GFM; if LaTeX fails, retry once with $-math disabled (math shown literally).

    Returns True when the fallback was needed. Applied to every survey alike; only documents whose
    inline math does not compile (e.g. Markdown escapes such as $I^\\*$) take the fallback.
    """
    for fmt, fallback in (("gfm", False), ("gfm-tex_math_dollars", True)):
        cmd = ["pandoc", str(md_path), "-f", fmt, "-o", str(pdf_path), *PANDOC_ARGS]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if res.returncode == 0:
            return fallback
    raise RuntimeError(f"pandoc failed for {md_path}: {res.stderr[-2000:]}")


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--review", type=Path, required=True, help="run's review/ directory")
    ap.add_argument("--eval-inputs", type=Path, required=True)
    ap.add_argument("--method", required=True)
    ap.add_argument("--topic-id", required=True)
    ap.add_argument("--das2m-db", type=Path, default=None, help="SQLite with papers(arxiv_id, norm_title)")
    ap.add_argument("--skip-pdf", action="store_true")
    args = ap.parse_args()

    lit = args.review / "literature.md"
    if not lit.is_file():
        logger.error("missing %s", lit)
        return 2
    out = args.eval_inputs / args.method
    out.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(args.das2m_db)) if args.das2m_db else None

    source = "ledger"
    try:
        if (args.review / "records.json").is_file():
            # Baselines (naive_rag.py) write their cited records in citation order.
            source = "records_json"
            records = list(enumerate(json.loads((args.review / "records.json").read_text(encoding="utf-8")), start=1))
        else:
            records = numbered_records(args.review)
    except (FileNotFoundError, KeyError, ValueError) as exc:
        logger.warning("ledger numbering unavailable (%s); parsing References", exc)
        records, source = fallback_records(lit.read_text(encoding="utf-8")), "references_section"

    ref_map: Dict[str, str] = {}
    how: Dict[str, int] = {}
    for num, rec in records:
        arx, via = resolve_arxiv(rec, db)
        how[via] = how.get(via, 0) + 1
        if arx:
            ref_map[str(num)] = arx
    (out / f"ref_{args.topic_id}.json").write_text(json.dumps(ref_map, indent=2) + "\n", encoding="utf-8")

    body = lit.read_text(encoding="utf-8")
    stats = {
        "topic_id": args.topic_id,
        "method": args.method,
        "numbering_source": source,
        "n_references": len(records),
        "n_arxiv_mapped": len(ref_map),
        "arxiv_coverage": round(len(ref_map) / len(records), 4) if records else 0.0,
        "resolved_via": how,
        "n_words": len(re.findall(r"\w+", body.split("## References")[0])),
        "n_citation_markers": len(re.findall(r"\[\d+(?:[,\-–]\s*\d+)*\]", body)),
    }
    (out / f"stats_{args.topic_id}.json").write_text(json.dumps(stats, indent=2) + "\n", encoding="utf-8")
    logger.info("%s", json.dumps(stats))

    if not args.skip_pdf:
        stats["render_fallback_no_dollar_math"] = render_pdf(lit, out / f"{args.topic_id}.pdf")
        (out / f"stats_{args.topic_id}.json").write_text(json.dumps(stats, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
