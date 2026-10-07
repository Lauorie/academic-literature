#!/usr/bin/env python3
"""Per-topic SurveyBench content-based evaluation.

Calls the released scoring functions unchanged (evaluate_content_compare, evaluate_outline,
get_richness) and the released score parsing; the released driver (run_content_eval.py) keeps only
method averages, so this loop stores every topic's raw judge responses and parsed scores.
A topic whose judge output fails the released parser is re-judged, up to MAX_ATTEMPTS in total
(the same cap as the DAS-Bench runs); every attempt is logged.
Usage: run_sb_eval.py --method M --survey-dir D --human-dir H --model J --out O [--pass-tag p1] [--workers 8]
Reads the gateway token from PAPERBYPASS_AUTH_TOKEN.
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

SB_SRC = Path("/home/juli/citation/SurveyBench/src")
sys.path.insert(0, str(SB_SRC))
from content_based_eval.eval_content import evaluate_content_compare  # noqa: E402
from content_based_eval.eval_outline import evaluate_outline  # noqa: E402
from content_based_eval.richness import get_richness  # noqa: E402

API_URL = "https://aigateway.paperbypass.com/api/v1"
MAX_ATTEMPTS = 6
CONTENT_KEYS = ["coverage", "coherence", "depth", "focus", "fluency"]
logger = logging.getLogger("sb_eval")


def parse_outline(val: str) -> int:
    """Released parser from run_content_eval.py (mode == 'outline')."""
    return int(val.strip().replace("Score:", "").replace("score:", "").replace("Score", ""))


def judge_topic(topic: str, a: argparse.Namespace, key: str) -> Dict[str, Any]:
    survey = os.path.join(a.survey_dir, topic + ".md")
    human = os.path.join(a.human_dir, topic + ".md")
    errors = []
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            c = evaluate_content_compare(topic, a.model, survey, human, key, API_URL)[0]
            content = {k: int(c[f"{k}_score"]["response"]) for k in CONTENT_KEYS}
            o = evaluate_outline(topic, a.model, survey, human, key, API_URL)
            outline = {k: sum(parse_outline(o[f"{k}_score_{i}"]["response"]) for i in range(1, 4)) / 3
                       for k in ("coverage", "relevance", "structure")}
            figs, tabs, length, rich = get_richness(survey)
            return {"topic": topic, "method": a.method, "judge": a.model, "pass": a.pass_tag,
                    "attempts": attempt, "errors": errors, "content": content, "outline": outline,
                    "richness": {"figures": figs, "tables": tabs, "length": length, "richness": rich},
                    "raw": {"content": {k: v["response"] for k, v in c.items() if k != "topic"},
                            "outline": {k: v["response"] for k, v in o.items() if k != "topic"}}}
        except (ValueError, KeyError, TypeError) as e:  # judge output not in the released format
            errors.append(f"attempt {attempt}: {type(e).__name__}: {str(e)[:200]}")
        except Exception as e:  # noqa: BLE001  API/network failure: back off and retry
            errors.append(f"attempt {attempt}: {type(e).__name__}: {str(e)[:200]}")
            time.sleep(min(60, 10 * attempt))
        logger.warning("%s | %s", topic, errors[-1])
    return {"topic": topic, "method": a.method, "judge": a.model, "pass": a.pass_tag,
            "attempts": MAX_ATTEMPTS, "errors": errors, "failed": True}


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    p = argparse.ArgumentParser()
    for k in ("--method", "--survey-dir", "--human-dir", "--model", "--out"):
        p.add_argument(k, required=True)
    p.add_argument("--pass-tag", default="p1")
    p.add_argument("--workers", type=int, default=8)
    p.add_argument("--topics", nargs="*", default=None)
    a = p.parse_args()
    key = os.environ["PAPERBYPASS_AUTH_TOKEN"]
    out = Path(a.out) / a.model.replace("/", "_") / a.pass_tag / a.method
    out.mkdir(parents=True, exist_ok=True)
    topics = a.topics or sorted(f.stem for f in Path(a.survey_dir).glob("*.md"))
    todo = [t for t in topics if not (out / f"{t}.json").exists()
            or json.loads((out / f"{t}.json").read_text()).get("failed")]
    logger.info("%s %s %s: %d topics, %d to judge", a.model, a.pass_tag, a.method, len(topics), len(todo))
    with ThreadPoolExecutor(a.workers) as ex:
        futs = {ex.submit(judge_topic, t, a, key): t for t in todo}
        for f in as_completed(futs):
            r = f.result()
            (out / f"{r['topic']}.json").write_text(json.dumps(r, indent=1, ensure_ascii=False) + "\n")
            logger.info("%s %s attempts=%s %s", "FAILED" if r.get("failed") else "done", r["topic"], r["attempts"],
                        "" if r.get("failed") else r["content"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
