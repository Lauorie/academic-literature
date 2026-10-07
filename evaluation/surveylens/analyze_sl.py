#!/usr/bin/env python3
"""Aggregate SurveyLens judging results.

For each (rubric, judge): per-system means of the outline / content / reference scores (each 1-5; pass-averaged
per survey), the number of surveys scored, per-discipline reference means, pass-to-pass agreement, and paired
comparisons Skill-Full vs NaiveRAG-Own / NaiveRAG-Pool per topic (bootstrap 95% CI, wins/ties/losses).
"mean3" is the unweighted mean of the three components; it is not the paper's BT-weighted score.
AutoSurvey2/Biology is excluded (a byte copy of AutoSurvey2/Business in the release).
Usage: analyze_sl.py <results dir> <out.json>
"""
from __future__ import annotations

import json
import random
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

ASPECTS = ("outline", "content", "reference")
OURS = ["Skill-Full", "NaiveRAG-Own", "NaiveRAG-Pool"]
SEED, N_BOOT = 42, 10000


def load(root: Path) -> dict:
    """data[(rubric, judge)][system][(discipline, file)][pass] = {aspect: score}"""
    data: dict = defaultdict(lambda: defaultdict(lambda: defaultdict(dict)))
    unscored: dict = defaultdict(lambda: defaultdict(int))
    for f in root.rglob("*_split.json"):
        parts = f.relative_to(root).parts
        rubric, rest = ("discipline", parts[1:]) if parts[0] == "discipline" else ("generic", parts)
        if len(rest) != 5:
            continue
        judge, pas, system, disc, _ = rest
        if system == "AutoSurvey2" and disc == "Biology":
            continue
        r = json.loads(f.read_text())
        if r.get("failed"):
            unscored[(rubric, judge)][system] += 1
            continue
        data[(rubric, judge)][system][(disc, f.name)][pas] = {a: float(r["scores"][a]["score"]) for a in ASPECTS}
    return data, unscored


def avg_passes(per_pass: dict) -> dict:
    return {a: st.mean(p[a] for p in per_pass.values()) for a in ASPECTS}


def boot_ci(d: list, rng: random.Random) -> list:
    means = sorted(st.mean(rng.choices(d, k=len(d))) for _ in range(N_BOOT))
    return [round(means[int(0.025 * N_BOOT)], 3), round(means[int(0.975 * N_BOOT) - 1], 3)]


def pearson(x: list, y: list) -> float:
    mx, my = st.mean(x), st.mean(y)
    den = (sum((a - mx) ** 2 for a in x) * sum((b - my) ** 2 for b in y)) ** 0.5
    return round(sum((a - mx) * (b - my) for a, b in zip(x, y)) / den, 3) if den else float("nan")


def main() -> int:
    data, unscored = load(Path(sys.argv[1]))
    out: dict = {}
    for key in sorted(data):
        rubric, judge = key
        systems = data[key]
        block: dict = {"systems": {}, "paired": {}, "pass_agreement": {}}
        for sysname, surveys in sorted(systems.items()):
            per = {k: avg_passes(v) for k, v in surveys.items()}
            row = {"n": len(per), "unscored": unscored[key].get(sysname, 0)}
            for a in ASPECTS:
                row[a] = round(st.mean(v[a] for v in per.values()), 3)
            row["mean3"] = round(st.mean(st.mean(v.values()) for v in per.values()), 3)
            by_disc = defaultdict(list)
            for (disc, _), v in per.items():
                by_disc[disc].append(v)
            row["by_discipline"] = {d: {a: round(st.mean(x[a] for x in vs), 2) for a in ASPECTS} | {"n": len(vs)}
                                    for d, vs in sorted(by_disc.items())}
            block["systems"][sysname] = row
            passes = sorted({p for v in surveys.values() for p in v})
            if len(passes) > 1:
                both = [v for v in surveys.values() if passes[0] in v and passes[1] in v]
                block["pass_agreement"][sysname] = {
                    a: {"r": pearson([v[passes[0]][a] for v in both], [v[passes[1]][a] for v in both]),
                        "identical": round(sum(v[passes[0]][a] == v[passes[1]][a] for v in both) / len(both), 3)}
                    for a in ASPECTS}
        if "Skill-Full" in systems:
            rng = random.Random(SEED)
            skill = {k: avg_passes(v) for k, v in systems["Skill-Full"].items()}
            for base in OURS[1:]:
                if base not in systems:
                    continue
                other = {k: avg_passes(v) for k, v in systems[base].items()}
                common = sorted(set(skill) & set(other))
                if not common:
                    continue
                res = {"n": len(common)}
                for a in list(ASPECTS) + ["mean3"]:
                    get = (lambda v, a=a: st.mean(v.values()) if a == "mean3" else v[a])
                    d = [get(skill[t]) - get(other[t]) for t in common]
                    res[a] = {"mean": round(st.mean(d), 3), "ci95": boot_ci(d, rng),
                              "wins": sum(x > 1e-9 for x in d), "ties": sum(abs(x) <= 1e-9 for x in d),
                              "losses": sum(x < -1e-9 for x in d)}
                block["paired"][f"Skill-Full - {base}"] = res
        out[f"{rubric}|{judge}"] = block
    Path(sys.argv[2]).write_text(json.dumps(out, indent=1) + "\n")
    for k, b in out.items():
        print(f"== {k}")
        for s, r in sorted(b["systems"].items(), key=lambda kv: -kv[1]["mean3"]):
            print(f"  {s:18s} n={r['n']:3d} unscored={r['unscored']} outline={r['outline']:.2f} content={r['content']:.2f} "
                  f"reference={r['reference']:.2f} mean3={r['mean3']:.2f}")
        for p, r in b["paired"].items():
            print(f"  {p:28s} n={r['n']} " + "  ".join(
                f"{a}={r[a]['mean']:+.2f} {r[a]['ci95']} {r[a]['wins']}/{r[a]['ties']}/{r[a]['losses']}"
                for a in list(ASPECTS) + ["mean3"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
