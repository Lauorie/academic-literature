#!/usr/bin/env python3
"""C4 part B: draw the blinded sample of numeric claims (see PLAN_C3_C4.md).

Unit: a prose sentence of the survey body that cites exactly one reference and holds at least one claim number under
check's own rule (`_claim_numbers` of the ledger code the runs used). Two per topic per condition, Skill-Full run 1
and NaiveRAG-Pool. Writes c4/blind/batch_<k>.json and c4/key/key.json. Usage: prepare_c4.py <das_eval dir> <n batches>
"""

from __future__ import annotations

import importlib.util
import json
import random
import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple

HERE = Path(__file__).parent
SEED = 20261007
PER_TOPIC = 2
CONDS = {"skill_full_r1": "deepseek-v4.1-flash", "naiverag_pool": "naiverag-deepseek-v4.1-flash_pool_r1"}
CITE = re.compile(r"\[(\d+(?:\s*[,–-]\s*\d+)*)\]")
REF_HEAD = re.compile(r"^##+\s*(References|Bibliography)\s*$", re.M | re.I)
ENTRY = re.compile(r"^\s*(?:\[(\d+)\]|(\d+)\.)\s+(.*\S)")
MARKS = re.compile(r"\[(venue unavailable|authors unavailable|no locator|unverified)\]", re.I)

spec = importlib.util.spec_from_file_location("ledger_8fc3", HERE / "ledger_das" / "citation_ledger.py")
cl = importlib.util.module_from_spec(spec)
sys.modules["ledger_8fc3"] = cl
spec.loader.exec_module(cl)


def clean_entry(text: str) -> str:
    text = re.sub(r"\s*" + MARKS.pattern + r"\s*,?", " ", text.replace("*", ""), flags=re.I)
    return re.sub(r"\s+", " ", text).strip()


def split(md: str) -> Tuple[str, Dict[int, str]]:
    parts = REF_HEAD.split(md)
    body, refs = parts[0], {}
    for ln in (parts[-1] if len(parts) > 1 else "").splitlines():
        if m := ENTRY.match(ln):
            refs[int(m.group(1) or m.group(2))] = clean_entry(m.group(3))
    return body, refs


def eligible(body: str, refs: Dict[int, str]) -> List[Dict[str, object]]:
    prose = "\n".join(ln for ln in body.splitlines() if not ln.lstrip().startswith(("|", "#")))
    out = []
    for k, sent in enumerate(cl._sentences(prose)):
        groups = CITE.findall(sent)
        nums = [int(n) for g in groups for n in re.findall(r"\d+", g)]
        if len(groups) != 1 or len(nums) != 1 or nums[0] not in refs:
            continue
        claims = cl._claim_numbers(CITE.sub("", sent))
        if claims:
            out.append({"k": k, "sentence": CITE.sub("[cited]", re.sub(r"\s+", " ", sent).strip()),
                        "ref": refs[nums[0]], "numbers": sorted(claims)})
    return out


def main() -> int:
    root, n_batches = Path(sys.argv[1]), int(sys.argv[2])
    rng = random.Random(SEED)
    items, short = [], {}
    for tid in (f"{i:03d}" for i in range(1, 31)):
        for cond, method in CONDS.items():
            body, refs = split((root / "pulled" / method / tid / "review" / "literature.md").read_text(encoding="utf-8"))
            pool = eligible(body, refs)
            if len(pool) < PER_TOPIC:
                short[f"{cond}/{tid}"] = len(pool)
            for it in rng.sample(pool, min(PER_TOPIC, len(pool))):
                items.append({"cond": cond, "tid": tid, **it})
    rng.shuffle(items)
    out = HERE / "c4"
    (out / "blind").mkdir(parents=True, exist_ok=True)
    (out / "key").mkdir(parents=True, exist_ok=True)
    key = {}
    for n, it in enumerate(items, 1):
        it["cid"] = f"N{n:03d}"
        key[it["cid"]] = {x: it[x] for x in ("cond", "tid", "k")}
    for b in range(n_batches):
        batch = [{x: it[x] for x in ("cid", "sentence", "ref", "numbers")} for it in items[b::n_batches]]
        (out / "blind" / f"batch_{b + 1}.json").write_text(json.dumps(batch, indent=1, ensure_ascii=False) + "\n")
    (out / "key" / "key.json").write_text(json.dumps(key, indent=1) + "\n")
    print(json.dumps({"items": len(items), "by_cond": {c: sum(it["cond"] == c for it in items) for c in CONDS},
                      "topics_short": short}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
