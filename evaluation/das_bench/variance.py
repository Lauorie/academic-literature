#!/usr/bin/env python3
"""Judge noise versus generation noise for Skill-Full.

Judge noise: the r1 surveys were judged twice by each judge (first pass on 2026-09-29, aggregates in
final/final_skill_deepseek-v4.1-flash.json; second pass in remote_results). Generation noise: topic totals
across runs r1-r3 under the same (second-pass) judging.
Usage: variance.py <analysis.json> <first-pass json> <out.json>
"""

from __future__ import annotations

import json
import statistics as st
import sys
from pathlib import Path

RUNS = ["skill_deepseek-v4.1-flash", "skill_deepseek-v4.1-flash_full_r2", "skill_deepseek-v4.1-flash_full_r3"]


def pearson(x, y) -> float:
    mx, my = st.mean(x), st.mean(y)
    num = sum((p - mx) * (q - my) for p, q in zip(x, y))
    den = (sum((p - mx) ** 2 for p in x) * sum((q - my) ** 2 for q in y)) ** 0.5
    return num / den


def main() -> int:
    ptf = json.loads(Path(sys.argv[1]).read_text())["per_topic_families"]
    first = json.loads(Path(sys.argv[2]).read_text())["topics"]
    out = {}
    for bench, key in (("DAS-Bench", "main"), ("DAS-Bench-xjudge", "xjudge")):
        new = ptf[bench][RUNS[0]]
        topics = [t for t in new if t in first]
        x = [first[t][key]["Total"] for t in topics]
        y = [new[t]["Total"] for t in topics]
        common = [t for t in new if all(t in ptf[bench].get(r, {}) for r in RUNS)]
        out[key] = {
            "rejudge_n": len(topics),
            "rejudge_pearson": round(pearson(x, y), 3),
            "rejudge_mean_abs_diff": round(st.mean(abs(p - q) for p, q in zip(x, y)), 3),
            "rejudge_mean_diff_old_minus_new": round(st.mean(p - q for p, q in zip(x, y)), 3),
            "per_topic_judge_sd": round(st.mean(abs(p - q) / 2 ** 0.5 for p, q in zip(x, y)), 3),
            "per_topic_generation_sd_3runs": round(st.mean(st.stdev([ptf[bench][r][t]["Total"] for r in RUNS]) for t in common), 3),
            "n_common_3runs": len(common),
        }
    Path(sys.argv[3]).write_text(json.dumps(out, indent=1) + "\n")
    sys.stdout.write(json.dumps(out) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
