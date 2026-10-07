#!/usr/bin/env python3
"""C3: label accuracy per cell and corrected defect rates per condition (see PLAN_C3_C4.md).

Usage: c3_analyze.py <das_eval dir> <out.json>
"""

from __future__ import annotations

import glob
import json
import logging
import math
import random
import statistics as st
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

HERE = Path(__file__).parent
CONDS = ("skill_full", "norag", "poolfree")
CLASSES = ("verified", "metadata_error", "not_found")
B, SEED = 10000, 0
logger = logging.getLogger(__name__)


def wilson(k: int, n: int) -> List[float]:
    if n == 0:
        return [float("nan"), float("nan")]
    z, p = 1.96, k / n
    c = (p + z * z / (2 * n)) / (1 + z * z / n)
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return [round(c - h, 3), round(c + h, 3)]


def truth(a: Dict) -> Optional[Tuple[bool, bool]]:
    """(exists, defective), or None when the auditor was unsure."""
    if a["exists"] == "unsure":
        return None
    if a["exists"] == "no":
        return False, True
    bad = any(a.get(f) == "no" for f in ("title_ok", "first_author_ok", "year_ok")) \
        or a.get("identifier") in ("another_work", "does_not_resolve")
    return True, bad


def agrees(cls: str, t: Tuple[bool, bool]) -> bool:
    exists, bad = t
    return {"verified": not bad, "metadata_error": exists and bad, "not_found": not exists}[cls]


def survey_counts(root: Path) -> Dict[str, Dict[str, Dict[str, int]]]:
    out: Dict[str, Dict[str, Dict[str, int]]] = {c: {} for c in CONDS}
    for f in glob.glob(str(root / "citation_integrity/results_v3/*/*.json")):
        d = json.loads(Path(f).read_text())
        cnt = {k: sum(e["class"] == k for e in d["checked"]) for k in CLASSES}
        if sum(cnt.values()):
            out[d["cond"]][d["tid"]] = cnt
    return out


def rate(cnt: Dict[str, int], p: Dict[str, float]) -> float:
    n = sum(cnt.values())
    return sum(cnt[k] * p[k] for k in CLASSES) / n


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    root, out = Path(sys.argv[1]), Path(sys.argv[2])
    key = json.loads((HERE / "c3/key/key.json").read_text())
    audits = {a["aid"]: a for f in sorted(glob.glob(str(HERE / "c3/out/batch_*.json"))) for a in json.loads(Path(f).read_text())}
    missing = sorted(set(key) - set(audits))
    cells: Dict[Tuple[str, str], List[Tuple[bool, bool]]] = {}
    unsure: Dict[str, int] = {}
    for aid, k in key.items():
        if aid not in audits:
            continue
        t = truth(audits[aid])
        cell = (k["cond"], k["class"])
        if t is None:
            unsure[f"{cell[0]}/{cell[1]}"] = unsure.get(f"{cell[0]}/{cell[1]}", 0) + 1
        else:
            cells.setdefault(cell, []).append(t)
    per_cell = {}
    for (c, k), ts in sorted(cells.items()):
        n, agree = len(ts), sum(agrees(k, t) for t in ts)
        bad, gone = sum(t[1] for t in ts), sum(not t[0] for t in ts)
        per_cell[f"{c}/{k}"] = {"n": n, "agree": agree, "agree_ci": wilson(agree, n), "defective": bad,
                                "defective_share": round(bad / n, 3), "defective_ci": wilson(bad, n),
                                "not_exist": gone, "not_exist_ci": wilson(gone, n)}

    counts = survey_counts(root)
    p_hat = {c: {k: st.mean(t[1] for t in cells[(c, k)]) for k in CLASSES} for c in CONDS}
    p_gone = {c: {k: st.mean(not t[0] for t in cells[(c, k)]) for k in CLASSES} for c in CONDS}
    # Decomposition of "defective" (added after the audit, exploratory): a real work with a wrong field.
    p_field = {c: {k: st.mean(t[0] and t[1] for t in cells[(c, k)]) for k in CLASSES} for c in CONDS}
    verifier = {c: {k: float(k != "verified") for k in CLASSES} for c in CONDS}
    def cond_rate(c: str, p: Dict[str, Dict[str, float]], tids: List[str]) -> float:
        return st.mean(rate(counts[c][t], p[c]) for t in tids)
    common = sorted(set(counts["skill_full"]) & set(counts["norag"]) & set(counts["poolfree"]))
    est = {name: {c: round(100 * cond_rate(c, p, common), 2) for c in CONDS}
           for name, p in (("verifier", verifier), ("corrected_defective", p_hat), ("corrected_not_exist", p_gone),
                           ("corrected_field_error", p_field))}

    rng = random.Random(SEED)
    pairs = [(m, o) for m in ("defective", "not_exist", "field_error") for o in ("norag", "poolfree")]
    boots: Dict[Tuple[str, str], List[float]] = {pr: [] for pr in pairs}
    for _ in range(B):
        ps: Dict[str, Dict[str, Dict[str, float]]] = {"defective": {}, "not_exist": {}, "field_error": {}}
        for c in CONDS:
            ps["defective"][c], ps["not_exist"][c], ps["field_error"][c] = {}, {}, {}
            for k in CLASSES:
                s = [rng.choice(cells[(c, k)]) for _ in cells[(c, k)]]
                ps["defective"][c][k] = st.mean(t[1] for t in s)
                ps["not_exist"][c][k] = st.mean(not t[0] for t in s)
                ps["field_error"][c][k] = st.mean(t[0] and t[1] for t in s)
        tids = [rng.choice(common) for _ in common]
        for m, o in pairs:
            boots[(m, o)].append(100 * (cond_rate("skill_full", ps[m], tids) - cond_rate(o, ps[m], tids)))
    diffs = {}
    for (m, o), vals in boots.items():
        vals.sort()
        point = est[f"corrected_{m}"]
        diffs[f"{m}_vs_{o}"] = {"diff": round(point["skill_full"] - point[o], 2),
                                "ci95": [round(vals[int(0.025 * B)], 2), round(vals[int(0.975 * B) - 1], 2)]}
    res = {"missing_audits": missing, "unsure": unsure, "per_cell": per_cell, "rates_pct": est,
           "skill_minus": diffs, "n_topics": len(common)}
    out.write_text(json.dumps(res, indent=1) + "\n")
    logger.info(json.dumps(res, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
