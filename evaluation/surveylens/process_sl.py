#!/usr/bin/env python3
"""Convert one condition's SurveyLens runs into the benchmark's processed JSON.

1. Stage each run's review/literature.md as staging/original/<method>/<Discipline>/<topic_filename>.md
   (the file-name convention of the published ASG systems).
2. Run the released data_processing_pipeline.py on the staging tree only (never on SurveyLens/results/original,
   which the pipeline would rewrite), with the released config values and the judge model for reference
   title extraction.
3. Set each reference's `text` back to the raw entry. The current pipeline sets text = bare title, but eight of
   the nine published systems' processed files keep the raw formatted entry, and the reference rubric reads
   `text`; restoring it scores every system on the same kind of input.
Usage: process_sl.py <runs dir> <exclude.json> <method> <staging root>
Reads API_KEY / BASE_URL from the environment (the pipeline's own convention).
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

SL = Path("/home/juli/citation/SurveyLens")
MODEL = "qwen/qwen3-30b-a3b-instruct-2507"


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(s or "").lower()).strip()


def main() -> int:
    runs, method, stage = Path(sys.argv[1]).resolve(), sys.argv[3], Path(sys.argv[4]).resolve()
    topics = {e["sl_id"]: e for e in json.loads(Path(sys.argv[2]).read_text())}
    tmap = {(r["discipline"], r["topic"]): r["topic_filename"]
            for r in json.loads((Path(sys.argv[2]).parent / "topics_map.json").read_text())}
    orig = stage / "original" / method
    n = 0  # incremental: already staged surveys keep their _split.json, so the pipeline skips them
    for sl_id, e in sorted(topics.items()):
        src = runs / sl_id / "review" / "literature.md"
        if not src.exists():
            print(f"MISSING {sl_id}", file=sys.stderr)
            continue
        dst = orig / e["discipline"] / f"{tmap[(e['discipline'], e['topic'])]}.md"
        dst.parent.mkdir(parents=True, exist_ok=True)
        if not dst.exists() or dst.read_bytes() != src.read_bytes():
            shutil.copy(src, dst)
        n += 1
    cfg = json.loads((SL / "scripts/config/data_processing_config.json").read_text())
    cfg.update({"input_dir": str(stage / "original"), "output_dir": str(stage / "processed"), "systems": [method],
                "llm_model": MODEL, "log_file": str(stage / f"processing_{method}.log"),
                "overwrite_original_json": False})  # keep existing _split.json; only new surveys are converted
    cfg_path = stage / f"processing_{method}.json"
    cfg_path.write_text(json.dumps(cfg, indent=1))
    subprocess.run([sys.executable, "scripts/data_processing_pipeline.py", "--batch", "--config", str(cfg_path)], cwd=SL, check=True)
    fixed = 0
    for pj in (stage / "processed" / method).rglob("*_split.json"):
        raw_refs = json.loads((orig / pj.relative_to(stage / "processed" / method)).with_name(
            pj.stem.removesuffix("_split") + "_split.json").read_text()).get("references") or []
        d = json.loads(pj.read_text())
        for ref in d.get("references") or []:
            t = norm(ref.get("title"))
            raw = next((r for r in raw_refs if t and t in norm(r)), None)
            if raw:
                ref["text"] = raw.strip()
                fixed += 1
        pj.write_text(json.dumps(d, ensure_ascii=False, indent=2))
    print(f"{method}: staged {n} surveys; processed {len(list((stage / 'processed' / method).rglob('*_split.json')))}; "
          f"references restored to raw text: {fixed}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
