#!/usr/bin/env python3
"""C8 label audit (PLAN_C6_C8.md): the C3 procedure on the NoSkill-Agent verifier labels.

Up to 25 entries per class (verified, metadata_error, not_found) from citation_integrity/results_c8, seed 20261007,
normalized as in C3, shuffled into batches. Writes c8audit/blind/batch_<k>.json and c8audit/key/key.json.
Usage: prepare_c8audit.py <das_eval dir> <n batches>
"""

from __future__ import annotations

import glob
import json
import random
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from prepare_c3 import CLASSES, PER_CELL, SEED, normalize  # noqa: E402


def main() -> int:
    root, n_batches = Path(sys.argv[1]), int(sys.argv[2])
    cells: dict = {}
    for f in sorted(glob.glob(str(root / "citation_integrity/results_c8/noskill/*.json"))):
        d = json.loads(Path(f).read_text())
        for e in d["checked"]:
            if e["class"] in CLASSES:
                cells.setdefault(e["class"], []).append((d["tid"], e["i"], e["entry"]))
    rng = random.Random(SEED)
    items = []
    for cls in CLASSES:
        rows = cells.get(cls, [])
        for tid, i, entry in rng.sample(rows, min(PER_CELL, len(rows))):
            items.append({"class": cls, "tid": tid, "i": i, "text": normalize(entry)})
    rng.shuffle(items)
    out = HERE / "c8audit"
    (out / "blind").mkdir(parents=True, exist_ok=True)
    (out / "key").mkdir(parents=True, exist_ok=True)
    key = {}
    for k, it in enumerate(items, 1):
        it["aid"] = f"S{k:03d}"
        key[it["aid"]] = {"cond": "noskill", "class": it["class"], "tid": it["tid"], "i": it["i"]}
    for b in range(n_batches):
        batch = [{"aid": it["aid"], "entry": it["text"]} for it in items[b::n_batches]]
        (out / "blind" / f"batch_{b + 1}.json").write_text(json.dumps(batch, indent=1, ensure_ascii=False) + "\n")
    (out / "key" / "key.json").write_text(json.dumps(key, indent=1) + "\n")
    print(json.dumps({"items": len(items), "cells": {c: sum(it["class"] == c for it in items) for c in CLASSES},
                      "available": {c: len(cells.get(c, [])) for c in CLASSES}}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
