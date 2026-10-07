#!/usr/bin/env python3
"""C1: which DAS-Bench criteria carry the skill's lead over NaiveRAG-Pool-Long and NaiveRAG-Pool (see PLAN.md).

Per judge: paired differences per criterion (Skill-Full = mean of its three runs per topic), and the total without
the figure/table criterion, and without it and the reference-presentation criterion, each with a bootstrap 95% CI.
Usage: c1_criteria.py <das_eval dir> <out.json>
"""

from __future__ import annotations

import json
import logging
import statistics as st
import sys
from pathlib import Path
from typing import Dict, List

# Analysis code: tools/ in our working tree, evaluation/das_bench/ in the release.
for _d in ("tools", "das_bench"):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / _d))
from aggregate import FAMILIES  # noqa: E402
from analyze_paper import BENCHES, CONDITIONS, bootstrap_ci, load  # noqa: E402

logger = logging.getLogger(__name__)

FIG = "Figure/Table Quality and Textual Integration"
REF = "Citation and Reference Presentation Integrity"
CRITERIA = [c for cs in FAMILIES.values() for c in cs]


def paired(root: Path, bench: str, other: str) -> Dict[str, object]:
    tids = [f"{i:03d}" for i in range(1, 31)]
    reps = {m: {t: s for t in tids if (s := load(root, bench, m, t))} for m in CONDITIONS["Skill-Full"]}
    om = CONDITIONS[other][0]
    base = {t: s for t in tids if (s := load(root, bench, om, t))}
    common = sorted(set(base).intersection(*(set(v) for v in reps.values())))
    skill = {t: {c: st.mean(reps[m][t][c] for m in reps) for c in CRITERIA} for t in common}

    def diff_of(crits: List[str]) -> Dict[str, object]:
        d = [st.mean(skill[t][c] for c in crits) - st.mean(base[t][c] for c in crits) for t in common]
        return {"mean": round(st.mean(d), 4), "ci95": [round(x, 4) for x in bootstrap_ci(d)],
                "wins": sum(x > 0 for x in d), "ties": sum(x == 0 for x in d)}

    per_crit = {c: {**diff_of([c]), "skill": round(st.mean(skill[t][c] for t in common), 4),
                    "baseline": round(st.mean(base[t][c] for t in common), 4)} for c in CRITERIA}
    return {"n": len(common), "total": diff_of(CRITERIA),
            "without_fig": diff_of([c for c in CRITERIA if c != FIG]),
            "without_fig_ref": diff_of([c for c in CRITERIA if c not in (FIG, REF)]),
            "per_criterion": per_crit}


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    root, out = Path(sys.argv[1]), Path(sys.argv[2])
    res = {b: {o: paired(root, b, o) for o in ("NaiveRAG-Pool-Long", "NaiveRAG-Pool")} for b in BENCHES}
    out.write_text(json.dumps(res, indent=1) + "\n")
    for b in BENCHES:
        for o, r in res[b].items():
            logger.info(f"{b} Skill-Full - {o} (n={r['n']}): total {r['total']['mean']} {r['total']['ci95']}; "
                        f"w/o fig {r['without_fig']['mean']} {r['without_fig']['ci95']}; "
                        f"w/o fig+ref {r['without_fig_ref']['mean']} {r['without_fig_ref']['ci95']}")
            for c, v in sorted(r["per_criterion"].items(), key=lambda kv: -abs(kv[1]["mean"]))[:6]:
                logger.info(f"    {v['mean']:+.2f} {v['ci95']}  {v['skill']:.2f} vs {v['baseline']:.2f}  {c}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
