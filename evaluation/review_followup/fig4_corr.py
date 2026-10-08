#!/usr/bin/env python3
"""N14(b), exploratory: Pearson r between arXiv coverage and BSC over the Skill-Full surveys of Fig. 4, per judge.

Reads the same inputs as tools/make_figures.fig_coverage (final/analysis_final.json, eval_inputs/*/stats_<t>.json).
Usage: fig4_corr.py <das_eval dir> <out.json>
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

for _d in ("tools", "das_bench"):  # das_eval layout, release layout
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / _d))
from analyze_paper import pearson  # noqa: E402
from make_figures import BENCH_NAMES, SKILL_RUNS  # noqa: E402

logger = logging.getLogger(__name__)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    root, out = Path(sys.argv[1]), Path(sys.argv[2])
    ptf = json.loads((root / "final/analysis_final.json").read_text())["per_topic_families"]
    res = {}
    for bench in BENCH_NAMES:
        xs, ys = [], []
        for m in SKILL_RUNS:
            for t, fam in ptf[bench].get(m, {}).items():
                f = root / "eval_inputs" / m / f"stats_{t}.json"
                if f.exists():
                    xs.append(json.loads(f.read_text())["arxiv_coverage"])
                    ys.append(fam["BSC"])
        res[bench] = {"n": len(xs), "pearson": round(pearson(xs, ys), 3)}
    out.write_text(json.dumps(res, indent=1) + "\n")
    logger.info(json.dumps(res))
    return 0


if __name__ == "__main__":
    sys.exit(main())
