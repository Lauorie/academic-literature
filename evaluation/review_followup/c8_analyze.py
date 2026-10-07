#!/usr/bin/env python3
"""C8 (PLAN_C6_C8.md): Skill-Full against the same agent without the skill (NoSkill-Agent), DAS-Bench.

DAS-Bench: Skill-Full (mean of three runs) minus NoSkill-Agent per judge, total and families, paired over topics
scored in both, bootstrap 95% CI; the total without the figure/table criterion; body words.
Reference integrity: verifier defective rate per survey, Skill-Full run 1 (results_v3) minus NoSkill-Agent
(results_c8), paired; and, when the label audit exists (c8audit/), the corrected rates as in C3.
Usage: c8_analyze.py <das_eval dir> <out.json>
"""

from __future__ import annotations

import glob
import json
import logging
import random
import re
import statistics as st
import sys
from pathlib import Path
from typing import Dict, List

HERE = Path(__file__).resolve().parent
for _d in ("tools", "das_bench"):
    sys.path.insert(0, str(HERE.parent / _d))
sys.path.insert(0, str(HERE))
from aggregate import FAMILIES  # noqa: E402
from analyze_paper import BENCHES, CONDITIONS, bootstrap_ci, load, topic_total  # noqa: E402
from c3_analyze import CLASSES, truth  # noqa: E402

logger = logging.getLogger(__name__)
FIG = "Figure/Table Quality and Textual Integration"
CRIT = [c for cs in FAMILIES.values() for c in cs]
NOSKILL = CONDITIONS["NoSkill-Agent"][0]


def das(root: Path) -> Dict:
    tids = [f"{i:03d}" for i in range(1, 31)]
    out = {}
    for b in BENCHES:
        reps = {m: {t: s for t in tids if (s := load(root, b, m, t))} for m in CONDITIONS["Skill-Full"]}
        base = {t: s for t in tids if (s := load(root, b, NOSKILL, t))}
        common = sorted(set(base).intersection(*(set(v) for v in reps.values())))
        sk = {t: {c: st.mean(reps[m][t][c] for m in reps) for c in CRIT} for t in common}

        def diff(crits: List[str]) -> Dict:
            d = [st.mean(sk[t][c] for c in crits) - st.mean(base[t][c] for c in crits) for t in common]
            return {"mean": round(st.mean(d), 4), "ci95": [round(x, 4) for x in bootstrap_ci(d)],
                    "wins": sum(x > 0 for x in d), "n": len(d)}
        out[b] = {"total": diff(CRIT), "without_fig": diff([c for c in CRIT if c != FIG]),
                  "families": {f: diff(cs) for f, cs in FAMILIES.items()},
                  "noskill_total_mean": round(st.mean(topic_total(base[t]) for t in common), 4)}
    return out


def words(md: Path) -> int:
    return len(re.split(r"\n#+\s*References\b", md.read_text(errors="replace"), flags=re.I)[0].split())


def integrity(root: Path) -> Dict:
    def rates(cond_dir: Path) -> Dict[str, Dict[str, int]]:
        out = {}
        for f in glob.glob(str(cond_dir / "*.json")):
            d = json.loads(Path(f).read_text())
            cnt = {k: sum(e["class"] == k for e in d["checked"]) for k in CLASSES}
            if sum(cnt.values()):
                out[d["tid"]] = cnt
        return out
    sk = rates(root / "citation_integrity/results_v3/skill_full")
    ns = rates(root / "citation_integrity/results_c8/noskill")
    common = sorted(set(sk) & set(ns))
    defect = lambda c: (c["metadata_error"] + c["not_found"]) / sum(c.values())  # noqa: E731
    d = [100 * (defect(sk[t]) - defect(ns[t])) for t in common]
    res = {"n": len(common), "verifier_skill": round(100 * st.mean(defect(sk[t]) for t in common), 2),
           "verifier_noskill": round(100 * st.mean(defect(ns[t]) for t in common), 2),
           "verifier_diff": round(st.mean(d), 2), "verifier_ci95": [round(x, 2) for x in bootstrap_ci(d)],
           "noskill_class_counts": {k: sum(c[k] for c in ns.values()) for k in CLASSES}}
    key_f = HERE / "c8audit/key/key.json"
    if not key_f.exists():
        return res
    key = json.loads(key_f.read_text())
    aud = {a["aid"]: a for f in glob.glob(str(HERE / "c8audit/out/*.json")) for a in json.loads(Path(f).read_text())}
    cells_ns: Dict[str, List] = {k: [] for k in CLASSES}
    for aid, k in key.items():
        if aid in aud and (t := truth(aud[aid])) is not None:
            cells_ns[k["class"]].append(t)
    c3key = json.loads((HERE / "c3/key/key.json").read_text())
    c3aud = {a["aid"]: a for f in glob.glob(str(HERE / "c3/out/*.json")) for a in json.loads(Path(f).read_text())}
    cells_sk: Dict[str, List] = {k: [] for k in CLASSES}
    for aid, k in c3key.items():
        if k["cond"] == "skill_full" and (t := truth(c3aud[aid])) is not None:
            cells_sk[k["class"]].append(t)
    rate = lambda cnt, p: sum(cnt[k] * p[k] for k in CLASSES) / sum(cnt.values())  # noqa: E731
    p_ns = {k: st.mean(t[1] for t in v) for k, v in cells_ns.items()}
    p_sk = {k: st.mean(t[1] for t in v) for k, v in cells_sk.items()}
    g_ns = {k: st.mean(not t[0] for t in v) for k, v in cells_ns.items()}
    res["audit_cells"] = {k: {"n": len(v), "defective": sum(t[1] for t in v), "not_exist": sum(not t[0] for t in v)}
                          for k, v in cells_ns.items()}
    res["corrected_skill"] = round(100 * st.mean(rate(sk[t], p_sk) for t in common), 2)
    res["corrected_noskill"] = round(100 * st.mean(rate(ns[t], p_ns) for t in common), 2)
    res["not_exist_noskill"] = round(100 * st.mean(rate(ns[t], g_ns) for t in common), 2)
    rng, boots = random.Random(0), []
    for _ in range(10000):
        ps = {k: st.mean(t[1] for t in [rng.choice(v) for _ in v]) for k, v in cells_sk.items()}
        pn = {k: st.mean(t[1] for t in [rng.choice(v) for _ in v]) for k, v in cells_ns.items()}
        tids = [rng.choice(common) for _ in common]
        boots.append(100 * (st.mean(rate(sk[t], ps) for t in tids) - st.mean(rate(ns[t], pn) for t in tids)))
    boots.sort()
    res["corrected_diff"] = round(res["corrected_skill"] - res["corrected_noskill"], 2)
    res["corrected_ci95"] = [round(boots[250], 2), round(boots[9749], 2)]
    return res


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    root, out = Path(sys.argv[1]), Path(sys.argv[2])
    res = {"das": das(root)}
    runs = sorted((root / "pulled/deepseek-v4.1-flash_noskill_r1").glob("[0-9][0-9][0-9]"))
    res["words_noskill_median"] = st.median(words(d / "review/literature.md") for d in runs if (d / "review/literature.md").exists())
    res["words_skill_median"] = st.median(words(root / "pulled/deepseek-v4.1-flash" / f"{i:03d}/review/literature.md") for i in range(1, 31))
    res["integrity"] = integrity(root)
    out.write_text(json.dumps(res, indent=1) + "\n")
    logger.info(json.dumps(res, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
