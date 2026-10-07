#!/usr/bin/env python3
"""C6 (PLAN_C6_C8.md): does mechanical heading depth earn the outline gain? Held-out SurveyLens topics.

Per judge configuration and component: v1-split minus v1, v3 minus v1, v3-flat minus v3, paired over the 20 topics,
bootstrap 95% CI (10,000 resamples, seed 0); and the share of v3's gain that v1-split reaches (ratio of means).
Usage: c6_analyze.py <out.json>
"""

from __future__ import annotations

import json
import logging
import statistics as st
import sys
from pathlib import Path

H = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(H / "skillrefine"))
sys.path.insert(0, str(H / "tools"))
import analyze_paper as ap  # noqa: E402
from compare_ver import HELD, SL_CONF, sl_score  # noqa: E402

logger = logging.getLogger(__name__)
PAIRS = {"v1split_minus_v1": ("Skill-v1split", "Skill-Full"), "v3_minus_v1": ("Skill-v3", "Skill-Full"),
         "v3flat_minus_v3": ("Skill-v3flat", "Skill-v3")}


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    out = Path(sys.argv[1])
    res: dict = {}
    for conf in SL_CONF:
        for asp in ("outline", "content", "reference"):
            for name, (a_sys, b_sys) in PAIRS.items():
                d = []
                for sid in HELD["sl"]:
                    a, b = sl_score(sid, a_sys, conf, asp), sl_score(sid, b_sys, conf, asp)
                    if a is not None and b is not None:
                        d.append(a - b)
                if d:
                    res[f"{conf}|{asp}|{name}"] = {"n": len(d), "mean": round(st.mean(d), 3),
                                                   "ci95": [round(x, 3) for x in ap.bootstrap_ci(d)],
                                                   "wins": sum(x > 0 for x in d), "losses": sum(x < 0 for x in d)}
            s, v = res.get(f"{conf}|{asp}|v1split_minus_v1"), res.get(f"{conf}|{asp}|v3_minus_v1")
            if s and v and v["mean"]:
                res[f"{conf}|{asp}|share_of_v3_gain"] = round(s["mean"] / v["mean"], 3)
    counts = json.loads((H / "review_followup/c6/counts.json").read_text())
    res["h3_per_survey"] = {k: round(st.mean(c[k] for c in counts.values()), 1) for k in ("v1_h3", "v1split_h3", "v3_h3", "v3flat_h3")}
    out.write_text(json.dumps(res, indent=1) + "\n")
    for k, v in res.items():
        if "outline" in k or k == "h3_per_survey":
            logger.info(f"{k}: {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
