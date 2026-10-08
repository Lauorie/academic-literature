#!/usr/bin/env python3
"""Two analyses on existing outputs, after the internal review (exploratory).

R1-10: DAS-Bench scores of the two-topic Opus pilot, next to the deepseek Skill-Full runs on the same topics.
R3-8: session-level test of the account in Sec. 5.5 (full-text reading -> fewer cited papers -> lower citation
distribution balance): Pearson r between papers cited and the balance criterion over all skill sessions, per judge,
and within each condition (Skill-Full's three runs; Skill-Abs), and the longest session against the 3-hour limit.
Usage: r1_10_r3_8.py <das_eval dir> <out.json>
"""

from __future__ import annotations

import json
import statistics as st
import sys
from pathlib import Path

for _d in ("tools", "das_bench"):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / _d))
from analyze_paper import BENCHES, CONDITIONS, load, pearson, topic_total  # noqa: E402

BAL = "Citation Distribution Balance and Non-Redundancy"
RUNSTATS = {"skill_deepseek-v4.1-flash": "full_r1", "skill_deepseek-v4.1-flash_full_r2": "full_r2",
            "skill_deepseek-v4.1-flash_full_r3": "full_r3", "skill_deepseek-v4.1-flash_abs_r1": "abs_r1"}


def main() -> int:
    root, out = Path(sys.argv[1]), Path(sys.argv[2])
    tids = [f"{i:03d}" for i in range(1, 31)]
    res: dict = {"opus": {}, "balance": {}}
    opus = CONDITIONS["Skill-Full-Opus"][0]
    for b in BENCHES:
        got = {t: s for t in tids if (s := load(root, b, opus, t))}
        rows = {}
        for t, s in got.items():
            ds = [load(root, b, m, t) for m in CONDITIONS["Skill-Full"]]
            ds = [d for d in ds if d]
            rows[t] = {"opus_total": round(topic_total(s), 3),
                       "deepseek_total_mean_runs": round(st.mean(topic_total(d) for d in ds), 3) if ds else None}
        res["opus"][b] = rows
    stats = {}
    for name in RUNSTATS.values():
        for r in json.loads((root / "final" / f"process_stats_{name}.json").read_text())["runs"]:
            stats[r["run"]] = r
    for b in BENCHES:
        xs, ys, cond = [], [], []
        for meth, name in RUNSTATS.items():
            run_dir = meth.removeprefix("skill_")
            for t in tids:
                s = load(root, b, meth, t)
                r = stats.get(f"{run_dir}/{t}")
                if s and r and r["cited"]:
                    xs.append(r["cited"])
                    ys.append(s[BAL])
                    cond.append("abs" if name == "abs_r1" else "full")
        res["balance"][b] = {"n_sessions": len(xs), "pearson_cited_vs_balance": round(pearson(xs, ys), 3)}
        for c in ("full", "abs"):
            cx = [x for x, k in zip(xs, cond) if k == c]
            cy = [y for y, k in zip(ys, cond) if k == c]
            res["balance"][b][f"within_{c}"] = {"n": len(cx), "pearson": round(pearson(cx, cy), 3)}
    walls = [r["wall_min"] for r in stats.values() if r.get("wall_min") is not None]
    res["wall_min_max"] = round(max(walls), 1)
    res["sessions_over_150_min"] = sum(w > 150 for w in walls)
    out.write_text(json.dumps(res, indent=1) + "\n")
    print(json.dumps(res, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
