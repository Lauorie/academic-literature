#!/usr/bin/env python3
"""C4 part B: are sampled numeric claims supported by the cited paper? (see PLAN_C3_C4.md)

A claim is an error if any of its numbers is misattributed or absent; supported if every number left after
dropping not_a_claim is supported; unverifiable otherwise. Claims with only not_a_claim numbers drop out.
Usage: c4_analyze.py <out.json>
"""

from __future__ import annotations

import glob
import json
import logging
import random
import sys
from pathlib import Path
from typing import Dict, List

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from c3_analyze import wilson  # noqa: E402

CONDS = ("skill_full_r1", "naiverag_pool")
B, SEED = 10000, 0
logger = logging.getLogger(__name__)


def claim_verdict(nums: List[Dict]) -> str:
    v = [n["verdict"] for n in nums if n["verdict"] != "not_a_claim"]
    if not v:
        return "no_claim"
    if any(x in ("misattributed", "absent") for x in v):
        return "error"
    return "supported" if all(x == "supported" for x in v) else "unverifiable"


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    out = Path(sys.argv[1])
    key = json.loads((HERE / "c4/key/key.json").read_text())
    audits = {a["cid"]: a for f in sorted(glob.glob(str(HERE / "c4/out/batch_*.json"))) for a in json.loads(Path(f).read_text())}
    rows = [{"cid": cid, **k, "verdict": claim_verdict(audits[cid]["numbers"]), "text": audits[cid]["text_accessed"],
             "numbers": [n["verdict"] for n in audits[cid]["numbers"]]} for cid, k in key.items() if cid in audits]
    res: Dict = {"missing_audits": sorted(set(key) - set(audits)), "by_condition": {}}
    for c in CONDS:
        sel = [r for r in rows if r["cond"] == c]
        cnt = {v: sum(r["verdict"] == v for r in sel) for v in ("supported", "error", "unverifiable", "no_claim")}
        ver = cnt["supported"] + cnt["error"]
        nums = [x for r in sel for x in r["numbers"] if x != "not_a_claim"]
        res["by_condition"][c] = {"claims": len(sel), **cnt, "full_text": sum(r["text"] == "full" for r in sel),
                                  "error_share_of_verifiable": round(cnt["error"] / ver, 3) if ver else None,
                                  "error_ci": wilson(cnt["error"], ver),
                                  "numbers": {v: nums.count(v) for v in sorted(set(nums))}}
    topics = sorted({r["tid"] for r in rows})
    rng = random.Random(SEED)

    def err(sel: List[Dict]) -> float:
        v = [r for r in sel if r["verdict"] in ("supported", "error")]
        return sum(r["verdict"] == "error" for r in v) / len(v) if v else float("nan")
    point = err([r for r in rows if r["cond"] == CONDS[0]]) - err([r for r in rows if r["cond"] == CONDS[1]])
    boots = []
    for _ in range(B):
        tids = [rng.choice(topics) for _ in topics]
        sel = [r for t in tids for r in rows if r["tid"] == t]
        d = err([r for r in sel if r["cond"] == CONDS[0]]) - err([r for r in sel if r["cond"] == CONDS[1]])
        if d == d:
            boots.append(d)
    boots.sort()
    res["skill_minus_pool_error_share"] = {"diff": round(point, 3), "ci95": [round(boots[int(0.025 * len(boots))], 3),
                                                                             round(boots[int(0.975 * len(boots)) - 1], 3)]}
    res["claims"] = rows
    out.write_text(json.dumps(res, indent=1) + "\n")
    logger.info(json.dumps({k: v for k, v in res.items() if k != "claims"}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
