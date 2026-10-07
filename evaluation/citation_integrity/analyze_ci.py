#!/usr/bin/env python3
"""Pre-registered analysis of citation_integrity/PROTOCOL.md.

Per survey: defective rate = (metadata_error + not_found) / (checked - unparseable); not_found rate likewise.
Per condition: pooled class shares, mean per-survey rates. Paired Skill-Full minus each baseline over topics
present in both, bootstrap 95% CI with tools/analyze_paper.bootstrap_ci (seed 0), wins/ties/losses.
Usage: analyze_ci.py <results dir> <out.json>
"""
from __future__ import annotations

import json
import statistics as st
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
from analyze_paper import bootstrap_ci  # noqa: E402

CONDS = ("skill_full", "norag", "poolfree")
CLASSES = ("verified", "metadata_error", "not_found", "unparseable")


def survey_rates(rows: list) -> dict:
    c = Counter(r["class"] for r in rows)
    denom = len(rows) - c["unparseable"]
    return {"checked": len(rows), **{k: c[k] for k in CLASSES},
            "defective": (c["metadata_error"] + c["not_found"]) / denom if denom else None,
            "not_found_rate": c["not_found"] / denom if denom else None}


def main() -> int:
    root, out = Path(sys.argv[1]), Path(sys.argv[2])
    per: dict = {c: {} for c in CONDS}
    for c in CONDS:
        for f in sorted((root / c).glob("*.json")):
            d = json.loads(f.read_text())
            per[c][d["tid"]] = {"n_entries": d["n_entries"], **survey_rates(d["checked"])}
    res: dict = {"per_survey": per, "condition": {}, "paired": {}}
    for c in CONDS:
        v = per[c]
        pooled = Counter()
        for s in v.values():
            pooled.update({k: s[k] for k in CLASSES})
        tot = sum(pooled.values())
        rated = [s for s in v.values() if s["defective"] is not None]
        res["condition"][c] = {
            "surveys": len(v), "surveys_without_reference_list": sum(s["n_entries"] == 0 for s in v.values()),
            "entries_total": sum(s["n_entries"] for s in v.values()), "checked": tot,
            "pooled_share": {k: round(pooled[k] / tot, 4) if tot else None for k in CLASSES},
            "mean_defective": round(st.mean(s["defective"] for s in rated), 4) if rated else None,
            "mean_not_found": round(st.mean(s["not_found_rate"] for s in rated), 4) if rated else None}
    for base in CONDS[1:]:
        for metric in ("defective", "not_found_rate"):
            common = sorted(t for t in per["skill_full"] if t in per[base]
                            and per["skill_full"][t][metric] is not None and per[base][t][metric] is not None)
            if len(common) < 5:
                continue
            d = [per["skill_full"][t][metric] - per[base][t][metric] for t in common]
            res["paired"][f"skill_full - {base} | {metric}"] = {
                "n": len(common), "mean": round(st.mean(d), 4), "ci95": [round(x, 4) for x in bootstrap_ci(d)],
                "wins(lower for skill)": sum(x < 0 for x in d), "ties": sum(x == 0 for x in d),
                "losses": sum(x > 0 for x in d)}
    out.write_text(json.dumps(res, indent=1) + "\n")
    for c, r in res["condition"].items():
        print(c, json.dumps(r))
    for k, r in res["paired"].items():
        print(k, json.dumps(r))
    return 0


if __name__ == "__main__":
    sys.exit(main())
