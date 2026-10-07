#!/usr/bin/env python3
"""C4 descriptive additions (PLAN_C3_C4.md): eligible numeric sentences per survey, and claim numbers per 1,000 words of prose.

Usage: c4_density.py <das_eval dir> <out.json>
"""

from __future__ import annotations

import json
import statistics as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import prepare_c4 as p4  # noqa: E402


def main() -> int:
    root, out = Path(sys.argv[1]), Path(sys.argv[2])
    res = {}
    for cond, method in p4.CONDS.items():
        n, per1k = [], []
        for i in range(1, 31):
            body, refs = p4.split((root / "pulled" / method / f"{i:03d}" / "review" / "literature.md").read_text(encoding="utf-8"))
            n.append(len(p4.eligible(body, refs)))
            # Added after the audit: claim numbers in all prose, whatever the citation style.
            prose = "\n".join(ln for ln in body.splitlines() if not ln.lstrip().startswith(("|", "#")))
            nums = sum(len(p4.cl._claim_numbers(p4.CITE.sub("", s))) for s in p4.cl._sentences(prose))
            per1k.append(1000 * nums / len(prose.split()))
        res[cond] = {"mean": round(st.mean(n), 1), "median": st.median(n), "total": sum(n), "zero": sum(x == 0 for x in n),
                     "claim_numbers_per_1k_prose_words": round(st.mean(per1k), 1)}
    out.write_text(json.dumps(res, indent=1) + "\n")
    print(json.dumps(res))
    return 0


if __name__ == "__main__":
    sys.exit(main())
