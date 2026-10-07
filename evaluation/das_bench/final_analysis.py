#!/usr/bin/env python3
"""Collect everything the final DAS-Bench report needs into one JSON.

Per topic and judge: 16 criterion scores, family averages, total; plus arXiv coverage
(stats_<tid>.json) and BSC evidence-card count. Aggregates: all 30, CS 001-021, non-CS 022-030,
and a BSC sensitivity subset (>= 20 evidence cards under the main judge).
Usage: final_analysis.py <dasbench_root> <method> <out.json>
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from statistics import mean
from typing import Dict, List

sys.path.insert(0, str(Path(__file__).parent))
from aggregate import FAMILIES, load_topic  # noqa: E402

BENCHES = {"main": "DAS-Bench", "xjudge": "DAS-Bench-xjudge"}
CS = [f"{i:03d}" for i in range(1, 22)]
NONCS = [f"{i:03d}" for i in range(22, 31)]
MIN_CARDS = 20


def summarize(per_topic: Dict[str, Dict[str, float]], tids: List[str]) -> Dict[str, float]:
    rows = [per_topic[t] for t in tids if t in per_topic]
    if not rows:
        return {}
    crit = {c: mean(r[c] for r in rows) for cs in FAMILIES.values() for c in cs}
    out = {f"{f}": round(mean(crit[c] for c in cs), 3) for f, cs in FAMILIES.items()}
    out["Total"] = round(mean(crit.values()), 3)
    out["n"] = len(rows)
    out["criteria"] = {c: round(v, 3) for c, v in crit.items()}
    return out


def main() -> int:
    root, method, out_path = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3])
    main_bench = root / "DAS-Bench"
    tids = sorted(p.stem for p in (main_bench / "eval_inputs" / method).glob("*.pdf"))
    report: Dict[str, object] = {"method": method, "topics": {}, "aggregates": {}}
    scores: Dict[str, Dict[str, Dict[str, float]]] = {}
    for tag, bench in BENCHES.items():
        scores[tag] = {t: s for t in tids if (s := load_topic(root / bench, method, t))}
    for t in tids:
        stats = json.loads((main_bench / "eval_inputs" / method / f"stats_{t}.json").read_text())
        row: Dict[str, object] = {"arxiv_coverage": stats["arxiv_coverage"], "n_references": stats["n_references"],
                                  "n_words": stats["n_words"]}
        for tag, bench in BENCHES.items():
            bsc = json.loads((root / bench / "results" / method / "bsc/api_off" / f"{t}.json").read_text())
            row[f"{tag}_cards"] = bsc["diagnostics"].get("num_evidence_cards_built")
            s = scores[tag].get(t)
            if s:
                row[tag] = {f: round(mean(s[c] for c in cs), 3) for f, cs in FAMILIES.items()}
                row[tag]["Total"] = round(mean(s.values()), 3)
        report["topics"][t] = row
    well = [t for t in tids if (report["topics"][t].get("main_cards") or 0) >= MIN_CARDS]
    for tag in BENCHES:
        report["aggregates"][tag] = {
            "all": summarize(scores[tag], tids),
            "cs21": summarize(scores[tag], [t for t in tids if t in CS]),
            "noncs9": summarize(scores[tag], [t for t in tids if t in NONCS]),
            f"cards>={MIN_CARDS}": summarize(scores[tag], well),
        }
    report["cards_ge_20_topics"] = well
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
