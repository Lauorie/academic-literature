#!/usr/bin/env python3
"""Analysis A of skillrefine/PAPER_ANALYSES.md: v3 and v1 against same-model baselines on held-out topics."""
import json
import statistics as st
import sys

sys.argv = [sys.argv[0], "v3"]
sys.path.insert(0, "skillrefine")
import compare_ver as c  # noqa: E402

out = {"das": {}, "sl": {}, "sb": {}}
BASE_DAS = {"Own": "naiverag-deepseek-v4.1-flash_own_r1", "Pool": "naiverag-deepseek-v4.1-flash_pool_r1",
            "Pool-Long": "naiverag-deepseek-v4.1-flash_poollong_r1"}
for bench in ("DAS-Bench", "DAS-Bench-xjudge"):
    for ver in ("v3", "v1"):
        for bname, bm in BASE_DAS.items():
            d = []
            for t in c.HELD["das"]:
                b = c.fam_scores(bench, bm, t)
                if ver == "v3":
                    a = c.fam_scores(bench, "skill_deepseek-v4.1-flash_full_v3", t)
                else:
                    xs = [x for m in c.V1_DAS if (x := c.fam_scores(bench, m, t))]
                    a = {k: st.mean(x[k] for x in xs) for k in xs[0]} if xs else None
                if a and b:
                    d.append(a["Total"] - b["Total"])
            out["das"][f"{bench}|{ver}-{bname}"] = {"n": len(d), "mean": round(st.mean(d), 3),
                                                   "wins": sum(x > 0 for x in d), "per_topic": [round(x, 3) for x in d]}
for conf in c.SL_CONF:
    for asp in ("outline", "content", "reference"):
        for ver, sysname in (("v3", "Skill-v3"), ("v1", "Skill-Full")):
            for base in ("NaiveRAG-Own", "NaiveRAG-Pool"):
                d = [a - b for s in c.HELD["sl"]
                     if (a := c.sl_score(s, sysname, conf, asp)) is not None and (b := c.sl_score(s, base, conf, asp)) is not None]
                out["sl"][f"{conf}|{asp}|{ver}-{base}"] = {"n": len(d), "mean": round(st.mean(d), 3),
                    "ci95": [round(x, 3) for x in c.ap.bootstrap_ci(d)], "wins": sum(x > 0 for x in d),
                    "ties": sum(x == 0 for x in d), "losses": sum(x < 0 for x in d)}
for sid in c.HELD["sb"]:
    row = {}
    for m in ("Skill-v3", "Skill-Full", "NaiveRAG-Own", "NaiveRAG-Pool"):
        v = []
        for p in ("p1", "p2"):
            f = c.H / "surveybench/results/qwen_qwen3.5-397b-a17b" / p / m / f"{c.SB_T[sid]}.json"
            if f.exists() and not (d := json.loads(f.read_text())).get("failed"):
                v.append((st.mean(d["content"].values()), st.mean(d["outline"].values())))
        if v:
            row[m] = {"content": round(st.mean(x[0] for x in v), 2), "outline": round(st.mean(x[1] for x in v), 2)}
    out["sb"][sid] = row
(c.H / "skillrefine/paper_analysis_a.json").write_text(json.dumps(out, indent=1))
for k, v in out["das"].items():
    print("DAS", k, v["mean"], f"wins {v['wins']}/{v['n']}")
for k, v in out["sl"].items():
    print("SL", k, v["mean"], v["ci95"], f"{v['wins']}/{v['ties']}/{v['losses']}")
print("SB", json.dumps(out["sb"]))
