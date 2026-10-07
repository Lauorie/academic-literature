#!/usr/bin/env python3
"""Statistics for the technical report, from mirrored raw DAS-Eval results.

Reads remote_results/<bench>/<method>/<family>/api_off/<tid>.json (bench = DAS-Bench | DAS-Bench-xjudge)
and eval_inputs/<method>/stats_<tid>.json. Writes one JSON with:
  per_topic[bench][method][tid] = {criteria, families, total}
  condition[bench][cond]        = family/total means over topics, averaged over runs, with SD across runs
  paired[bench][a_vs_b]          = mean paired difference of totals over topics + 95% bootstrap CI
  judge_agreement[method]       = Pearson r of topic totals between judges, and mean |diff|
  coverage[method]              = mean arXiv coverage (CS / non-CS)
Usage: analyze_paper.py <das_eval dir> <out.json>
"""

from __future__ import annotations

import json
import random
import statistics as st
import sys
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).parent))
from aggregate import FAMILIES  # noqa: E402

BENCHES = ("DAS-Bench", "DAS-Bench-xjudge")
CONDITIONS = {  # condition -> list of run methods (repetitions)
    "Skill-Full": ["skill_deepseek-v4.1-flash", "skill_deepseek-v4.1-flash_full_r2", "skill_deepseek-v4.1-flash_full_r3"],
    "Skill-Abs": ["skill_deepseek-v4.1-flash_abs_r1"],
    "NaiveRAG-Own": ["naiverag-deepseek-v4.1-flash_own_r1"],
    "NaiveRAG-Pool": ["naiverag-deepseek-v4.1-flash_pool_r1"],
    "NaiveRAG-Pool-Long": ["naiverag-deepseek-v4.1-flash_poollong_r1"],  # length_matched/PROTOCOL.md
    "Skill-Full-Opus": ["skill_claude-opus-5.5"],
}
CS = {f"{i:03d}" for i in range(1, 22)}


def load(root: Path, bench: str, method: str, tid: str) -> Optional[Dict[str, float]]:
    base = root / "remote_results" / bench / method
    out: Dict[str, float] = {}
    try:
        bsc = json.loads((base / "bsc/api_off" / f"{tid}.json").read_text())
        mar = json.loads((base / "mar/api_off" / f"{tid}.json").read_text())
        th = json.loads((base / "tsq_hdq/api_off" / f"{tid}.json").read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return None
    if bsc.get("status") != "success" or mar.get("status") != "success" or th.get("status") != "done":
        return None
    for fam, src in (("BSC", bsc["scores"]), ("MAR", mar["scores"]), ("TSQ", th["scores"]["TSQ"]), ("HDQ", th["scores"]["HDQ"])):
        for c in FAMILIES[fam]:
            out[c] = float(src[c]["score"])
    return out


def summarize(scores: Dict[str, Dict[str, float]]) -> Dict[str, float]:
    """Protocol aggregation over topics: criterion means, then family means, total = mean of 16."""
    crit = {c: st.mean(s[c] for s in scores.values()) for f in FAMILIES.values() for c in f}
    out = {f: st.mean(crit[c] for c in cs) for f, cs in FAMILIES.items()}
    out["Total"] = st.mean(crit.values())
    return out


def topic_total(s: Dict[str, float]) -> float:
    return st.mean(s.values())


def bootstrap_ci(diffs: List[float], n: int = 10000, seed: int = 0) -> List[float]:
    rng = random.Random(seed)
    means = sorted(st.mean(rng.choice(diffs) for _ in diffs) for _ in range(n))
    return [means[int(0.025 * n)], means[int(0.975 * n) - 1]]


def pearson(a: List[float], b: List[float]) -> float:
    ma, mb = st.mean(a), st.mean(b)
    num = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    den = (sum((x - ma) ** 2 for x in a) * sum((y - mb) ** 2 for y in b)) ** 0.5
    return num / den if den else float("nan")


def main() -> int:
    root, out_path = Path(sys.argv[1]), Path(sys.argv[2])
    tids = [f"{i:03d}" for i in range(1, 31)]
    per: Dict[str, Dict[str, Dict[str, Dict[str, float]]]] = {}
    for b in BENCHES:
        per[b] = {}
        for runs in CONDITIONS.values():
            for m in runs:
                got = {t: s for t in tids if (s := load(root, b, m, t))}
                if got:
                    per[b][m] = got

    res: Dict[str, object] = {"per_topic_totals": {b: {m: {t: round(topic_total(s), 4) for t, s in v.items()}
                                                        for m, v in per[b].items()} for b in BENCHES}}
    res["per_topic_families"] = {b: {m: {t: {**{f: round(st.mean(sc[c] for c in cs), 4) for f, cs in FAMILIES.items()},
                                                "Total": round(topic_total(sc), 4)}
                                            for t, sc in v.items()} for m, v in per[b].items()} for b in BENCHES}
    cond: Dict[str, Dict[str, object]] = {}
    for b in BENCHES:
        cond[b] = {}
        for c, runs in CONDITIONS.items():
            present = [m for m in runs if m in per[b]]
            if not present:
                continue
            # Topics scored in every present run, so repetitions are compared on the same set.
            common = sorted(set.intersection(*(set(per[b][m]) for m in present)))
            if not common:
                continue
            by_run = [summarize({t: per[b][m][t] for t in common}) for m in present]
            entry: Dict[str, object] = {"runs": present, "n_topics": len(common)}
            for k in list(FAMILIES) + ["Total"]:
                vals = [r[k] for r in by_run]
                entry[k] = round(st.mean(vals), 3)
                entry[f"{k}_sd_runs"] = round(st.stdev(vals), 3) if len(vals) > 1 else None
            for name, sub in (("cs", [t for t in common if t in CS]), ("noncs", [t for t in common if t not in CS])):
                if sub:
                    entry[name] = {k: round(st.mean(summarize({t: per[b][m][t] for t in sub})[k] for m in present), 3)
                                   for k in list(FAMILIES) + ["Total"]}
            cond[b][c] = entry
    res["condition"] = cond

    paired: Dict[str, Dict[str, object]] = {}
    ref = CONDITIONS["Skill-Full"]
    for b in BENCHES:
        paired[b] = {}
        for other in ("Skill-Abs", "NaiveRAG-Own", "NaiveRAG-Pool", "NaiveRAG-Pool-Long"):
            om = CONDITIONS[other][0]
            if om not in per[b]:
                continue
            reps = [m for m in ref if m in per[b]]
            common = sorted(set(per[b][om]).intersection(*(set(per[b][m]) for m in reps)))
            if len(common) < 5:
                continue
            diffs = [st.mean(topic_total(per[b][m][t]) for m in reps) - topic_total(per[b][om][t]) for t in common]
            fam_diffs = {f: round(st.mean(st.mean(st.mean(per[b][m][t][c] for c in FAMILIES[f]) for m in reps)
                                         - st.mean(per[b][om][t][c] for c in FAMILIES[f]) for t in common), 3)
                         for f in FAMILIES}
            per_run = [(topic_total(per[b][m][t]) - topic_total(per[b][om][t])) for m in reps for t in common]
            paired[b][f"Skill-Full_vs_{other}"] = {"n": len(common), "mean_diff_total": round(st.mean(diffs), 3),
                                                  "per_run_pairs": len(per_run), "per_run_wins": sum(d > 0 for d in per_run),
                                                  "per_run_ties": sum(d == 0 for d in per_run),
                                                  "ci95": [round(x, 3) for x in bootstrap_ci(diffs)],
                                                  "wins": sum(d > 0 for d in diffs), "ties": sum(d == 0 for d in diffs),
                                                  "family_diffs": fam_diffs}
    res["paired"] = paired

    agree: Dict[str, object] = {}
    for m in per[BENCHES[0]]:
        if m not in per[BENCHES[1]]:
            continue
        common = sorted(set(per[BENCHES[0]][m]) & set(per[BENCHES[1]][m]))
        if len(common) < 5:
            continue
        a = [topic_total(per[BENCHES[0]][m][t]) for t in common]
        bb = [topic_total(per[BENCHES[1]][m][t]) for t in common]
        agree[m] = {"n": len(common), "pearson_topic_total": round(pearson(a, bb), 3),
                    "mean_abs_diff": round(st.mean(abs(x - y) for x, y in zip(a, bb)), 3),
                    "mean_diff_main_minus_x": round(st.mean(x - y for x, y in zip(a, bb)), 3)}
    res["judge_agreement"] = agree

    cov: Dict[str, object] = {}
    for runs in CONDITIONS.values():
        for m in runs:
            stats = {}
            for t in tids:
                f = root / "eval_inputs" / m / f"stats_{t}.json"
                if f.exists():
                    stats[t] = json.loads(f.read_text())
            if stats:
                cov[m] = {"n": len(stats),
                          "refs_mean": round(st.mean(s["n_references"] for s in stats.values()), 1),
                          "words_mean": round(st.mean(s["n_words"] for s in stats.values())),
                          "cov_cs": round(st.mean(s["arxiv_coverage"] for t, s in stats.items() if t in CS), 3),
                          "cov_noncs": round(st.mean(s["arxiv_coverage"] for t, s in stats.items() if t not in CS), 3)
                          if any(t not in CS for t in stats) else None}
    res["coverage"] = cov
    out_path.write_text(json.dumps(res, indent=1) + "\n")
    for b in BENCHES:
        for c, e in cond[b].items():
            sys.stdout.write(f"{b:18s} {c:16s} n={e['n_topics']:2d} runs={len(e['runs'])} "
                             + " ".join(f"{k}={e[k]}" for k in list(FAMILIES) + ["Total"]) + f" sd={e['Total_sd_runs']}\n")
    sys.stdout.write(json.dumps(paired, indent=1) + "\n" + json.dumps(agree) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
