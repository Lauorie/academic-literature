#!/usr/bin/env python3
"""NoRAG and Pool-Free conditions of citation_integrity/PROTOCOL.md: the model writes its own reference list.

Same generator, temperature, output cap, retry rule and (for Pool-Free) candidate pool as NaiveRAG-Pool
(tools/naive_rag.py); only the citation rule differs, and nothing is rendered from records.
Writes <out>/<cond>/<tid>/{review/literature.md, retrieved.json, usage.json, finish_reason, exit_code, ...}.
Kept outside pulled/ so the DAS-Bench watchdog does not convert or score these runs.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import naive_rag as nr  # noqa: E402

logger = logging.getLogger(__name__)

STRUCTURE = """Write the survey in English Markdown: a title, an abstract, an introduction, thematic sections organized by the field's main research questions, a critical discussion, open problems and future directions, and a conclusion. Synthesize across papers rather than summarizing them one by one."""

REFS = ("End with a section `## References` that lists every cited work as a numbered entry with its authors, "
        "title, venue, year, and DOI or arXiv identifier when you know it.")

NORAG = f"""You are writing a comprehensive academic survey of the field on the topic:

"{{topic}}"

Cite the literature with numbers in square brackets, e.g. [3] or [2, 7]. {REFS} Cite only works that exist.

{STRUCTURE}
"""

POOLFREE = f"""You are writing a comprehensive academic survey of the field on the topic:

"{{topic}}"

Use ONLY the {{n}} papers listed below. Cite them with numbers in square brackets, e.g. [3] or [2, 7]. Do not cite anything else. {REFS}

{STRUCTURE}

Papers:
{{papers}}
"""


def run_topic(cond: str, tid: str, topic: str, out: Path, model: str, token: str, max_tokens: int,
              pool_from: Path, abstract_chars: int) -> None:
    run = out / cond / tid
    if (run / "exit_code").exists():
        return
    (run / "review").mkdir(parents=True, exist_ok=True)
    (run / "started_at").write_text(nr.now() + "\n")
    code = 0
    try:
        if cond == "norag":
            prompt = NORAG.format(topic=topic)
        else:
            papers = [p for p in nr.pool_from_ledger(pool_from / tid) if str(p.get("title") or "").strip()]
            (run / "retrieved.json").write_text(json.dumps(papers, ensure_ascii=False, indent=1))
            prompt = POOLFREE.format(topic=topic, n=len(papers), papers="\n\n".join(
                nr.paper_block(i, p, abstract_chars) for i, p in enumerate(papers, 1)))
        (run / "prompt.txt").write_text(prompt)
        for attempt in (1, 2):  # protocol: one retry when the call returns no text
            resp = nr.generate(prompt, model, token, max_tokens)
            text = resp["choices"][0]["message"].get("content") or ""
            if text.strip():
                break
        (run / "generation_attempts").write_text(f"{attempt}\n")
        (run / "usage.json").write_text(json.dumps(resp.get("usage", {}), indent=1))
        (run / "finish_reason").write_text(f"{resp['choices'][0].get('finish_reason')}\n")
        if not text.strip():
            raise RuntimeError("empty completion after retry")
        (run / "review" / "literature.md").write_text(text.rstrip() + "\n")
        logger.info("%s %s: finish=%s body=%d words", cond, tid, resp["choices"][0].get("finish_reason"),
                    nr.body_words(text))
    except (requests.RequestException, RuntimeError, KeyError, ValueError) as exc:
        code = 1
        (run / "error.txt").write_text(str(exc))
        logger.error("%s %s failed: %s", cond, tid, exc)
    (run / "exit_code").write_text(f"{code}\n")
    (run / "finished_at").write_text(nr.now() + "\n")


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--topics", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--pool-from", type=Path, required=True)
    ap.add_argument("--conds", default="norag,poolfree")
    ap.add_argument("--model", default="deepseek/deepseek-v4.1-flash")
    ap.add_argument("--max-tokens", type=int, default=32000)
    ap.add_argument("--abstract-chars", type=int, default=1200)
    ap.add_argument("--parallel", type=int, default=6)
    ap.add_argument("--only", default="")
    args = ap.parse_args()
    token = os.environ["PAPERBYPASS_AUTH_TOKEN"]
    topics = json.loads(args.topics.read_text())
    if args.only:
        topics = [t for t in topics if t["topic_id"] in set(args.only.split(","))]
    with ThreadPoolExecutor(args.parallel) as pool:
        for cond in args.conds.split(","):
            for t in topics:
                pool.submit(run_topic, cond, t["topic_id"], t["topic"], args.out, args.model, token,
                            args.max_tokens, args.pool_from, args.abstract_chars)
    return 0


if __name__ == "__main__":
    sys.exit(main())
