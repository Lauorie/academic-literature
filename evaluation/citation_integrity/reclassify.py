#!/usr/bin/env python3
"""Reclassify stored v2 extractions with keep_written_ids (PROTOCOL Deviations, v3); lookups come from the cache."""
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import verify_refs as v  # noqa: E402

src, dst = Path(sys.argv[1]), Path(sys.argv[2])
http = v.Http()


def one(f: Path) -> None:
    d = json.loads(f.read_text())
    rows = []
    for r in d["checked"]:
        fields = v.keep_written_ids(r["fields"], r["entry"])
        rows.append({"i": r["i"], "entry": r["entry"], "fields": fields, "fields_extracted": r["fields"],
                     **v.classify(fields, http)})
    out = dst / f.parent.name / f.name
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({**d, "checked": rows}, ensure_ascii=False, indent=1))


with ThreadPoolExecutor(4) as ex:
    list(ex.map(one, sorted(src.glob("*/*.json"))))
print("done", len(list(dst.glob("*/*.json"))))
