#!/usr/bin/env python3
"""Per-file SurveyLens generic-rubric evaluation (released eval_ablation.py prompts, unchanged).

Instantiates the released AblationEvaluator and calls its evaluate_file() for each processed survey; this loop
only adds per-file result files, parallelism, and re-judging when a score is missing or outside 1-5
(the released script records such outputs as None), up to MAX_ATTEMPTS, every attempt logged.
Usage: run_sl_eval.py --processed-root R --system S --model M --out O [--pass-tag p1] [--workers 8]
Reads the gateway token from PAPERBYPASS_AUTH_TOKEN and passes it as API_KEY / BASE_URL (the released convention).
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict

SL_SCRIPTS = Path("/home/juli/citation/SurveyLens/scripts")
os.environ["API_KEY"] = os.environ["PAPERBYPASS_AUTH_TOKEN"]
os.environ["BASE_URL"] = "https://aigateway.paperbypass.com/api/v1"
sys.path.insert(0, str(SL_SCRIPTS / "evaluation"))
sys.path.insert(0, str(SL_SCRIPTS))
from eval_ablation import AblationEvaluator  # noqa: E402
from eval_qualitative import EvaluationConfig, QuantitativeEvaluator  # noqa: E402

CRITERIA_DIR = Path(__file__).resolve().parent / "criteria_gen" / "outputs" / "criteria"

DISCIPLINES = ["Biology", "Business", "Computer Science", "Education", "Engineering", "Environmental Science",
               "Medicine", "Physics", "Psychology", "Sociology"]
MAX_ATTEMPTS = 6
ASPECTS = ("outline", "content", "reference")
logger = logging.getLogger("sl_eval")


def valid(scores: Dict[str, Any]) -> bool:
    return all(isinstance((scores.get(a) or {}).get("score"), (int, float)) and 1 <= scores[a]["score"] <= 5
               for a in ASPECTS)


def judge(ev: AblationEvaluator, path: Path, category: str) -> Dict[str, Any]:
    errors = []
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            r = ev.evaluate_file(path, category)
            if valid(r["scores"]):
                return {**r, "attempts": attempt, "errors": errors}
            errors.append(f"attempt {attempt}: invalid scores "
                          + json.dumps({a: (r['scores'].get(a) or {}).get('score') for a in ASPECTS}))
        except Exception as e:  # noqa: BLE001  API/network failure: back off and retry
            errors.append(f"attempt {attempt}: {type(e).__name__}: {str(e)[:200]}")
            time.sleep(min(60, 10 * attempt))
        logger.warning("%s | %s", path.name, errors[-1])
    return {"file": str(path), "category": category, "attempts": MAX_ATTEMPTS, "errors": errors, "failed": True}


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    p = argparse.ArgumentParser()
    for k in ("--processed-root", "--system", "--model", "--out"):
        p.add_argument(k, required=True)
    p.add_argument("--pass-tag", default="p1")
    p.add_argument("--workers", type=int, default=8)
    p.add_argument("--rubric", choices=["generic", "discipline"], default="generic",
                   help="generic = released eval_ablation.py; discipline = released eval_qualitative.py with "
                        "criteria regenerated in criteria_gen/ (per-aspect + per-criterion, as the released config)")
    a = p.parse_args()
    if a.rubric == "generic":
        cfg = EvaluationConfig(processed_dir=a.processed_root, llm_model=a.model, llm_temperature=0.0,
                               max_total_tokens_in_prompt=32768)
        ev = AblationEvaluator(cfg)
    else:
        cfg = EvaluationConfig(processed_dir=a.processed_root, llm_model=a.model, llm_temperature=0.0,
                               max_total_tokens_in_prompt=32768, criteria_base_dir=str(CRITERIA_DIR),
                               per_aspect_scoring=True, per_criterion_scoring=True)
        ev = QuantitativeEvaluator(cfg)
    canon = {d.lower(): d for d in DISCIPLINES}
    files = []
    for ddir in sorted((Path(a.processed_root) / a.system).iterdir()):
        if ddir.is_dir() and ddir.name.lower() in canon:
            files += [(f, canon[ddir.name.lower()]) for f in sorted(ddir.glob("*_split.json"))]  # skip processing_summary.json
    out = Path(a.out) / (a.rubric if a.rubric != "generic" else "") / a.model.replace("/", "_") / a.pass_tag / a.system
    todo = []
    for f, cat in files:
        o = out / cat / f.name
        if not o.exists() or json.loads(o.read_text()).get("failed"):
            todo.append((f, cat, o))
    logger.info("%s %s %s: %d files, %d to judge", a.model, a.pass_tag, a.system, len(files), len(todo))
    with ThreadPoolExecutor(a.workers) as pool:
        futs = {pool.submit(judge, ev, f, cat): o for f, cat, o in todo}
        for fut in as_completed(futs):
            o = futs[fut]
            r = fut.result()
            o.parent.mkdir(parents=True, exist_ok=True)
            o.write_text(json.dumps(r, indent=1, ensure_ascii=False) + "\n")
            logger.info("%s %s attempts=%s %s", "FAILED" if r.get("failed") else "done", o.name[:50], r["attempts"],
                        "" if r.get("failed") else {k: r["scores"][k]["score"] for k in ASPECTS})
    return 0


if __name__ == "__main__":
    sys.exit(main())
