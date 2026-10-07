#!/usr/bin/env python3
"""Supplementary analyses for the report (criterion-level, coverage sensitivity, rubric checks, attempts).

Usage: supp_analysis.py <das_eval dir> <watchdog_state.json> <out.json>
"""

from __future__ import annotations

import collections
import json
import statistics as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from aggregate import FAMILIES  # noqa: E402
from analyze_paper import BENCHES, CONDITIONS, load  # noqa: E402

TIDS = [f"{i:03d}" for i in range(1, 31)]


def cards(root: Path, bench: str, method: str, tid: str):
    f = root / "remote_results" / bench / method / "bsc/api_off" / f"{tid}.json"
    try:
        d = json.loads(f.read_text())["diagnostics"]
        return d.get("num_evidence_cards_built"), d.get("num_selected_claims_considered")
    except (FileNotFoundError, KeyError, json.JSONDecodeError):
        return None, None


def main() -> int:
    root, state_p, out_p = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    res: dict = {}
    full = CONDITIONS["Skill-Full"]
    abs_m = CONDITIONS["Skill-Abs"][0]

    # 1) Criterion-level BSC difference, Skill-Full (mean over runs) minus Skill-Abs, paired over topics
    res["bsc_criteria_full_minus_abs"] = {}
    for b in BENCHES:
        diffs = collections.defaultdict(list)
        for t in TIDS:
            fs = [s for m in full if (s := load(root, b, m, t))]
            a = load(root, b, abs_m, t)
            if not fs or not a:
                continue
            for c in FAMILIES["BSC"]:
                diffs[c].append(st.mean(s[c] for s in fs) - a[c])
        res["bsc_criteria_full_minus_abs"][b] = {c: {"n": len(v), "mean": round(st.mean(v), 3)} for c, v in diffs.items()}

    # 2) Sensitivity: BSC and total restricted to topics with >= 20 evidence cards in every run
    res["cards_ge20"] = {}
    for b in BENCHES:
        entry = {}
        for cond, runs in CONDITIONS.items():
            if cond == "Skill-Full-Opus":
                continue
            keep = [t for t in TIDS if all((cards(root, b, m, t)[0] or 0) >= 20 for m in runs)]
            vals = [[load(root, b, m, t) for m in runs] for t in keep]
            vals = [v for v in vals if all(v)]
            if not vals:
                continue
            bsc = st.mean(st.mean(st.mean(s[c] for c in FAMILIES["BSC"]) for s in v) for v in vals)
            tot = st.mean(st.mean(st.mean(s.values()) for s in v) for v in vals)
            entry[cond] = {"n_topics": len(vals), "BSC": round(bsc, 3), "Total": round(tot, 3)}
        res["cards_ge20"][b] = entry

    # 3) Rubric check: assessable claims < 20 yet a 5 on claim support or faithfulness
    viol = []
    for b in BENCHES:
        for runs in CONDITIONS.values():
            for m in runs:
                for t in TIDS:
                    f = root / "remote_results" / b / m / "bsc/api_off" / f"{t}.json"
                    if not f.exists():
                        continue
                    d = json.loads(f.read_text())
                    n_cards = d.get("diagnostics", {}).get("num_evidence_cards_built") or 0
                    sc = d.get("scores", {})
                    top = [sc.get(c, {}).get("score") for c in FAMILIES["BSC"][:2]]
                    if n_cards < 20 and 5 in top:
                        viol.append({"bench": b, "method": m, "tid": t, "cards": n_cards, "scores": top})
    res["rubric_violations_lt20_cards_score5"] = viol
    res["n_bsc_results_lt20_cards"] = sum(
        1 for b in BENCHES for runs in CONDITIONS.values() for m in runs for t in TIDS
        if (c := cards(root, b, m, t)[0]) is not None and c < 20)

    # 4) Judge attempts per (bench:method/topic) item that needed more than one attempt
    state = json.loads(state_p.read_text())
    retries = state.get("retries", {})
    dist = collections.Counter(retries.values())
    res["attempts"] = {"items_retried": len(retries), "distribution_of_attempts_used": dict(sorted(dist.items())),
                       "by_judge": dict(collections.Counter(k.split(":")[0] for k in retries))}
    out_p.write_text(json.dumps(res, indent=1) + "\n")
    sys.stdout.write(json.dumps(res, indent=1)[:4000] + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
