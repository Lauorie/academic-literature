#!/usr/bin/env python3
"""Aggregate SurveyBench judging results.

Per judge: method means (content = mean of 5 criteria, outline = mean of 3; pass-averaged per topic),
SD of method means across passes, paired Skill-Full minus each baseline per topic with a bootstrap CI,
pass-to-pass agreement per topic, richness, and the published SurveyBench numbers for reference.
Usage: analyze_sb.py <results dir> <out.json>
"""
from __future__ import annotations

import json
import random
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

SKILL = "Skill-Full"
BASELINES = ["OpenAI_DeepResearch", "AutoSurvey", "SurveyForge", "LLMxMR-V2"]
# SurveyBench README, Table 1 (content-based, with human reference)
PUBLISHED = {"OpenAI_DeepResearch": {"outline": 3.57, "content": 4.42}, "AutoSurvey": {"outline": 3.88, "content": 4.03},
             "SurveyForge": {"outline": 4.01, "content": 4.03}, "LLMxMR-V2": {"outline": 4.37, "content": 4.20}}
SEED, N_BOOT = 42, 10000


def scores(r: dict) -> dict:
    c, o = r["content"], r["outline"]
    content, outline = st.mean(c.values()), st.mean(o.values())
    return {"content": content, "outline": outline, "overall": (content + outline) / 2,
            **{f"c_{k}": v for k, v in c.items()}, **{f"o_{k}": v for k, v in o.items()}}


def boot_ci(d: list, rng: random.Random) -> list:
    means = sorted(st.mean(rng.choices(d, k=len(d))) for _ in range(N_BOOT))
    return [round(means[int(0.025 * N_BOOT)], 3), round(means[int(0.975 * N_BOOT) - 1], 3)]


def pearson(x: list, y: list) -> float:
    mx, my = st.mean(x), st.mean(y)
    num = sum((a - mx) * (b - my) for a, b in zip(x, y))
    den = (sum((a - mx) ** 2 for a in x) * sum((b - my) ** 2 for b in y)) ** 0.5
    return num / den if den else float("nan")


def main() -> int:
    root = Path(sys.argv[1])
    data = defaultdict(lambda: defaultdict(lambda: defaultdict(dict)))  # judge -> method -> topic -> pass -> scores
    rich, attempts, failed = defaultdict(list), defaultdict(list), []
    for f in root.glob("*/*/*/*.json"):
        judge, pas, method = f.parts[-4], f.parts[-3], f.parts[-2]
        r = json.loads(f.read_text())
        if r.get("failed"):
            failed.append(str(f.relative_to(root)))
            continue
        data[judge][method][r["topic"]][pas] = scores(r)
        attempts[judge].append(r["attempts"])
        if pas == "p1":
            rich[method].append(r["richness"])
    out = {"failed": failed, "judges": {}, "richness": {}, "published": PUBLISHED}
    for m, rs in rich.items():
        out["richness"][m] = {k: round(st.mean(x[k] for x in rs), 2) for k in ("figures", "tables", "length", "richness")}
    for judge, methods in data.items():
        rng = random.Random(SEED)
        J = {"retried_items": sum(a > 1 for a in attempts[judge]), "items": len(attempts[judge]), "methods": {}, "paired": {},
             "pass_agreement": {}}
        topic_avg = {}
        for m, topics in methods.items():
            passes = sorted({p for t in topics.values() for p in t})
            complete = [t for t in topics if all(p in topics[t] for p in passes)]
            topic_avg[m] = {t: {k: st.mean(topics[t][p][k] for p in passes) for k in topics[t][passes[0]]} for t in complete}
            per_pass = {p: {k: st.mean(topics[t][p][k] for t in complete) for k in ("content", "outline", "overall")} for p in passes}
            J["methods"][m] = {"n_topics": len(complete), "passes": passes,
                               **{k: round(st.mean(topic_avg[m][t][k] for t in complete), 3) for k in topic_avg[m][complete[0]]},
                               "sd_across_passes": {k: round(st.stdev([per_pass[p][k] for p in passes]), 3) if len(passes) > 1 else None
                                                    for k in ("content", "outline", "overall")}}
            if len(passes) > 1:
                J["pass_agreement"][m] = {k: round(pearson([topics[t][passes[0]][k] for t in complete],
                                                           [topics[t][passes[1]][k] for t in complete]), 3)
                                          for k in ("content", "outline", "overall")}
        if SKILL in topic_avg:
            for b in BASELINES:
                if b not in topic_avg:
                    continue
                common = sorted(set(topic_avg[SKILL]) & set(topic_avg[b]))
                J["paired"][b] = {"n": len(common)}
                for k in ("content", "outline", "overall"):
                    d = [topic_avg[SKILL][t][k] - topic_avg[b][t][k] for t in common]
                    J["paired"][b][k] = {"mean": round(st.mean(d), 3), "ci95": boot_ci(d, rng),
                                         "wins": sum(x > 1e-9 for x in d), "ties": sum(abs(x) <= 1e-9 for x in d),
                                         "losses": sum(x < -1e-9 for x in d)}
        out["judges"][judge] = J
    Path(sys.argv[2]).write_text(json.dumps(out, indent=1) + "\n")
    for judge, J in out["judges"].items():
        print(f"== {judge}  (retried {J['retried_items']}/{J['items']})")
        for m, v in sorted(J["methods"].items(), key=lambda kv: -kv[1]["overall"]):
            pub = PUBLISHED.get(m, {})
            print(f"  {m:22s} n={v['n_topics']:2d} content={v['content']:.2f} outline={v['outline']:.2f} overall={v['overall']:.2f} "
                  f"sd={v['sd_across_passes']}  published c/o={pub.get('content', '-')}/{pub.get('outline', '-')}  "
                  f"agree={J['pass_agreement'].get(m)}")
        for b, v in J["paired"].items():
            print(f"  Skill - {b:20s} " + "  ".join(f"{k}={v[k]['mean']:+.2f} {v[k]['ci95']} W/T/L={v[k]['wins']}/{v[k]['ties']}/{v[k]['losses']}"
                                                  for k in ("content", "outline", "overall")))
    print("richness", out["richness"])
    print("failed", failed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
