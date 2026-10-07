#!/usr/bin/env python3
"""C4 part A: what `check` says about the evidence files of all 120 skill sessions (see PLAN_C3_C4.md).

Per session, with the ledger code version under which the delivered file re-checks (c7_result.json):
- warnings by type (cited paper without evidence file; figure not in the cited paper's evidence; record warnings);
- every claim number (check's `_claim_numbers`) in a sentence or table row of the draft that cites papers, traced to
  the cited papers' evidence files, to another paper's evidence file only, or to none.
Usage: c4_partA.py <das_eval dir> <out.json>
"""

from __future__ import annotations

import contextlib
import io
import json
import logging
import statistics as st
import sys
from pathlib import Path
from typing import Any, Dict

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from c7_check import RUNS, renderers  # noqa: E402

logger = logging.getLogger(__name__)
TRACE = ("in_cited_evidence", "cited_paper_has_no_file", "only_in_other_paper_file", "in_no_file")


def warning_type(msg: str) -> str:
    if "has no evidence file" in msg:
        return "no_evidence_file"
    if "is not in the cited paper's evidence" in msg:
        return "figure_not_in_evidence"
    if "no DOI, arXiv id or URL" in msg:
        return "record_no_identifier"
    if "venue says" in msg:
        return "record_venue_vs_arxiv_doi"
    return "record_other"


def session(run: Path, cl: Any) -> Dict[str, Any]:
    review = run / "review"
    draft = (review / "literature.draft.md").read_text(encoding="utf-8")
    ledger = cl.Ledger.load(review / "citations.jsonl")
    evdir = review / "evidence"
    with contextlib.redirect_stdout(io.StringIO()):
        warns = cl._check_evidence(draft, ledger, evdir) if evdir.exists() else []
    active = ledger.active()
    for key in cl.collect_keys(draft):
        if key in active:
            warns.extend(cl._record_warnings(active[key].record))
    wtypes: Dict[str, int] = {}
    for w in warns:
        wtypes[warning_type(w)] = wtypes.get(warning_type(w), 0) + 1

    files = {p.stem: cl._evidence_numbers(p.read_text(encoding="utf-8", errors="replace"))
             for p in evdir.glob("*.md")} if evdir.exists() else {}
    every = set().union(*files.values()) if files else set()
    trace = {t: 0 for t in TRACE}
    table_rows = prose = 0
    for sentence in cl._sentences(draft):
        keys = [k for m in cl.CITE_RE.finditer(sentence) for k in cl.KEY_RE.findall(m.group(1))]
        nums = cl._claim_numbers(cl.CITE_RE.sub("", sentence)) if keys else set()
        if not nums:
            continue
        if sentence.lstrip().startswith("|"):
            table_rows += len(nums)
        else:
            prose += len(nums)
        cited = [files[k] for k in keys if k in files]
        pool = set().union(*cited) if cited else set()
        for n in nums:
            if not cited:
                trace["cited_paper_has_no_file"] += 1
            elif n in pool:
                trace["in_cited_evidence"] += 1
            elif n in every:
                trace["only_in_other_paper_file"] += 1
            else:
                trace["in_no_file"] += 1
    return {"warnings": len(warns), "warning_types": wtypes, "claim_numbers": sum(trace.values()),
            "in_table_rows": table_rows, "in_prose": prose, "trace": trace}


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    root, out = Path(sys.argv[1]), Path(sys.argv[2])
    mods = renderers()
    c7 = {r["session"]: r for r in json.loads((HERE / "c7_result.json").read_text())["sessions"]}
    rows = []
    for cond, method in RUNS.items():
        for d in sorted((root / "pulled" / method).glob("[0-9][0-9][0-9]")):
            version = c7[f"{method}/{d.name}"]["recheck_pass_versions"][0]
            rows.append({"session": f"{method}/{d.name}", "condition": cond, "version": version,
                         **session(d, mods[version])})
    summary: Dict[str, Any] = {}
    for cond in list(RUNS) + ["all"]:
        sel = [r for r in rows if cond in ("all", r["condition"])]
        tot = sum(r["claim_numbers"] for r in sel)
        wt: Dict[str, int] = {}
        for r in sel:
            for k, v in r["warning_types"].items():
                wt[k] = wt.get(k, 0) + v
        summary[cond] = {"sessions": len(sel), "warnings_mean": round(st.mean(r["warnings"] for r in sel), 2),
                         "warning_types_mean": {k: round(v / len(sel), 2) for k, v in sorted(wt.items())},
                         "claim_numbers_mean": round(tot / len(sel), 1),
                         "share_in_table_rows": round(sum(r["in_table_rows"] for r in sel) / tot, 3),
                         "trace_share": {t: round(sum(r["trace"][t] for r in sel) / tot, 3) for t in TRACE}}
    out.write_text(json.dumps({"summary": summary, "sessions": rows}, indent=1) + "\n")
    logger.info(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
