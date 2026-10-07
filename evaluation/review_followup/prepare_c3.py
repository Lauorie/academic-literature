#!/usr/bin/env python3
"""C3: draw the stratified, blinded sample of verifier labels (see PLAN_C3_C4.md).

Writes c3/blind/batch_<k>.json (what auditors see: aid and normalized entry text) and c3/key/key.json (aid -> condition,
topic, entry index, verifier class). Usage: prepare_c3.py <das_eval dir> <n batches>
"""

from __future__ import annotations

import glob
import json
import random
import re
import sys
from pathlib import Path

SEED = 20261007
PER_CELL = 25
CLASSES = ("verified", "metadata_error", "not_found")
MARKS = re.compile(r"\[(venue unavailable|authors unavailable|no locator|unverified)\]", re.I)


def normalize(entry: str) -> str:
    """Strip the list number, markdown emphasis and the skill's placeholder marks; change nothing else."""
    text = re.sub(r"^\s*(\[\d+\]|\d+\.)\s*", "", entry)
    # A removed mark takes its own trailing comma with it: "Title.* [venue unavailable], 2020" -> "Title. 2020".
    text = re.sub(r"\s*" + MARKS.pattern + r"\s*,?", " ", text.replace("*", ""), flags=re.I)
    return re.sub(r"\s+", " ", text).strip()


def main() -> int:
    root, n_batches = Path(sys.argv[1]), int(sys.argv[2])
    cells: dict = {}
    for f in sorted(glob.glob(str(root / "citation_integrity/results_v3/*/*.json"))):
        d = json.loads(Path(f).read_text())
        for e in d["checked"]:
            if e["class"] in CLASSES:
                cells.setdefault((d["cond"], e["class"]), []).append((d["tid"], e["i"], e["entry"]))
    rng = random.Random(SEED)
    items = []
    for (cond, cls), rows in sorted(cells.items()):
        for tid, i, entry in rng.sample(rows, min(PER_CELL, len(rows))):
            items.append({"cond": cond, "class": cls, "tid": tid, "i": i, "text": normalize(entry)})
    rng.shuffle(items)
    out = Path(__file__).parent / "c3"
    (out / "blind").mkdir(parents=True, exist_ok=True)
    (out / "key").mkdir(parents=True, exist_ok=True)
    key = {}
    for k, it in enumerate(items, 1):
        it["aid"] = f"R{k:03d}"
        key[it["aid"]] = {x: it[x] for x in ("cond", "class", "tid", "i")}
    for b in range(n_batches):
        batch = [{"aid": it["aid"], "entry": it["text"]} for it in items[b::n_batches]]
        (out / "blind" / f"batch_{b + 1}.json").write_text(json.dumps(batch, indent=1, ensure_ascii=False) + "\n")
    (out / "key" / "key.json").write_text(json.dumps(key, indent=1) + "\n")
    counts = {f"{c}/{k}": sum(1 for it in items if (it["cond"], it["class"]) == (c, k)) for c, k in sorted(cells)}
    print(json.dumps({"items": len(items), "cells": counts}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
