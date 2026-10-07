#!/usr/bin/env python3
"""Aggregate DAS-Eval results into the 16-criterion table (protocol: criterion mean over topics,
family avg = mean of 4 criteria, Total = mean of 16).

Usage: aggregate.py <DAS-Bench root> <method> [<method> ...] [--topics 003,027] [--csv out.csv]
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from statistics import mean
from typing import Dict, List, Optional

FAMILIES = {
    "BSC": ["Claim-Level Citation Support", "Reference Faithfulness and Attribution Accuracy",
            "Multi-Reference Synthesis Coverage and Quality", "Citation Distribution Balance and Non-Redundancy"],
    "TSQ": ["Research-Space Coverage", "Taxonomy Clarity and Boundary Control",
            "Survey Organization and Functional Coherence", "Synthesis Insight and Gap Analysis"],
    "HDQ": ["Multi-Level Goal Alignment", "Paragraph Argument Progression",
            "Atomic Claim Specificity and Technical Concreteness", "Local Synthesis and Non-Enumerative Writing"],
    "MAR": ["Citation and Reference Presentation Integrity", "Figure/Table Quality and Textual Integration",
            "Layout and Formatting Professionalism", "Manuscript Component Completeness"],
}


def load_topic(root: Path, method: str, tid: str) -> Optional[Dict[str, float]]:
    """All 16 criterion scores for one method/topic, or None if any family is missing/failed."""
    base = root / "results" / method
    out: Dict[str, float] = {}
    try:
        bsc = json.loads((base / "bsc/api_off" / f"{tid}.json").read_text())["scores"]
        mar = json.loads((base / "mar/api_off" / f"{tid}.json").read_text())["scores"]
        th = json.loads((base / "tsq_hdq/api_off" / f"{tid}.json").read_text())
    except (FileNotFoundError, KeyError, json.JSONDecodeError):
        return None
    if th.get("status") != "done":
        return None
    for fam, src in (("BSC", bsc), ("MAR", mar), ("TSQ", th["scores"]["TSQ"]), ("HDQ", th["scores"]["HDQ"])):
        for crit in FAMILIES[fam]:
            if crit not in src:
                return None
            out[crit] = float(src[crit]["score"])
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("root", type=Path)
    ap.add_argument("methods", nargs="+")
    ap.add_argument("--topics", default="")
    ap.add_argument("--csv", type=Path, default=None)
    args = ap.parse_args()

    rows: List[Dict[str, object]] = []
    for m in args.methods:
        tids = args.topics.split(",") if args.topics else sorted(
            p.stem for p in (args.root / "results" / m / "mar/api_off").glob("*.json"))
        per_topic = {t: s for t in tids if (s := load_topic(args.root, m, t))}
        missing = [t for t in tids if t not in per_topic]
        if not per_topic:
            continue
        crit = {c: mean(s[c] for s in per_topic.values()) for f in FAMILIES.values() for c in f}
        row: Dict[str, object] = {"method": m, "n_topics": len(per_topic), "missing": ",".join(missing)}
        for fam, cs in FAMILIES.items():
            row[f"{fam} Avg."] = round(mean(crit[c] for c in cs), 2)
        row["Total Avg."] = round(mean(crit.values()), 2)
        row.update({c: round(v, 2) for c, v in crit.items()})
        rows.append(row)
        for t, s in sorted(per_topic.items()):
            fam_avgs = {f: round(mean(s[c] for c in cs), 2) for f, cs in FAMILIES.items()}
            sys.stdout.write(f"{m} {t} {json.dumps(fam_avgs)} total={round(mean(s.values()), 2)}\n")

    for r in rows:
        sys.stdout.write(json.dumps({k: r[k] for k in list(r)[:8]}) + "\n")
    if args.csv and rows:
        with args.csv.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
    return 0


if __name__ == "__main__":
    sys.exit(main())
