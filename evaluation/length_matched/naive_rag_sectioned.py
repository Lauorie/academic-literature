#!/usr/bin/env python3
"""NaiveRAG-Pool-Long, variant B (length_matched/PROTOCOL.md): outline call, then one call per section.

Same pool, generator, temperature, paper list and citation rule as NaiveRAG-Pool (tools/naive_rag.py);
the reference list is rendered from the records by naive_rag.render, so no citation can be invented.
Writes <out>/<tid>/{retrieved.json, outline.json, target_words, usage.json, finish_reason,
review/literature.md, review/records.json, exit_code, started_at, finished_at}.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, List, Tuple

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import naive_rag as nr  # noqa: E402

logger = logging.getLogger(__name__)

OUTLINE_RULE = """
First, plan the survey. Return ONLY a JSON object, with no other text:
{{"title": "<survey title>", "sections": [{{"heading": "<section heading>", "words": <integer>, "plan": "<what the section covers and which papers it draws on>"}}, ...]}}
Make the abstract the first section. The word budgets must sum to about {words}, the length of the survey body without the reference list."""

SECTION_PROMPT = """You are writing one section of a comprehensive academic survey of the field on the topic:

"{topic}"

The survey follows this outline (word budget per section in brackets):
{outline}

Write ONLY the section "{heading}", about {words} words long, in English Markdown. Start with the line "## {heading}".
Use ONLY the {n} papers listed below. Cite them with their list numbers in square brackets, e.g. [3] or [2, 7]. Do not cite anything else and do not write a reference list; it is added automatically.
Synthesize across papers rather than summarizing them one by one.

Papers:
{papers}
"""


def call(prompt: str, model: str, token: str, max_tokens: int, usage: Dict[str, int]) -> Tuple[str, str]:
    """One generation call with the protocol's single retry on empty text; usage is summed in place."""
    for _ in (1, 2):
        resp = nr.generate(prompt, model, token, max_tokens)
        for k, v in resp.get("usage", {}).items():
            if isinstance(v, int):
                usage[k] = usage.get(k, 0) + v
        text = resp["choices"][0]["message"].get("content") or ""
        if text.strip():
            return text, str(resp["choices"][0].get("finish_reason"))
    raise RuntimeError("empty completion after retry")


def parse_outline(text: str) -> Dict[str, Any]:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("no JSON object in outline reply")
    o = json.loads(m.group(0))
    secs = o.get("sections")
    if not (isinstance(o.get("title"), str) and isinstance(secs, list) and secs
            and all(isinstance(s.get("heading"), str) and isinstance(s.get("words"), int) for s in secs)):
        raise ValueError("outline JSON lacks title / sections[heading, words]")
    return o


def run_topic(tid: str, topic: str, out: Path, model: str, token: str, max_tokens: int,
              pool_from: Path, match_length_of: List[Path], abstract_chars: int, parallel_sections: int) -> None:
    run = out / tid
    if (run / "exit_code").exists():
        return
    (run / "review").mkdir(parents=True, exist_ok=True)
    (run / "started_at").write_text(nr.now() + "\n")
    code, usage, finishes = 0, {}, []
    try:
        papers = [p for p in nr.pool_from_ledger(pool_from / tid) if str(p.get("title") or "").strip()]
        (run / "retrieved.json").write_text(json.dumps(papers, ensure_ascii=False, indent=1))
        words = nr.target_words(tid, match_length_of)
        (run / "target_words").write_text(f"{words}\n")
        plist = "\n\n".join(nr.paper_block(i, p, abstract_chars) for i, p in enumerate(papers, 1))
        base = nr.PROMPT.format(topic=topic, n=len(papers), length_rule="", papers=plist)
        outline = None
        for attempt in (1, 2):  # protocol: one repeat when the outline does not parse
            text, fin = call(base + OUTLINE_RULE.format(words=words), model, token, max_tokens, usage)
            finishes.append(fin)
            try:
                outline = parse_outline(text)
                break
            except (ValueError, json.JSONDecodeError) as exc:
                logger.warning("%s: outline attempt %d unparsable: %s", tid, attempt, exc)
        if outline is None:
            raise RuntimeError("outline unparsable after retry")
        (run / "outline.json").write_text(json.dumps(outline, ensure_ascii=False, indent=1))
        secs = outline["sections"]
        olines = "\n".join(f"- {s['heading']} [{s['words']}]: {s.get('plan', '')}" for s in secs)

        def write(s: Dict[str, Any]) -> Tuple[str, str]:
            return call(SECTION_PROMPT.format(topic=topic, outline=olines, heading=s["heading"], words=s["words"],
                                              n=len(papers), papers=plist), model, token, max_tokens, usage)

        with ThreadPoolExecutor(parallel_sections) as ex:
            parts = list(ex.map(write, secs))
        finishes += [f for _, f in parts]
        # A References heading inside one section would make render() drop every later section: cut it there.
        cut = [re.split(r"^#{1,6}\s*References\s*$", t, flags=re.M | re.I)[0].strip() for t, _ in parts]
        body = f"# {outline['title']}\n\n" + "\n\n".join(cut)
        md, cited = nr.render(body, papers)
        (run / "review" / "literature.md").write_text(md)
        (run / "review" / "records.json").write_text(json.dumps(cited, ensure_ascii=False, indent=1))
        logger.info("%s: %d sections, %d cited, target=%d body=%d words, finish=%s", tid, len(secs), len(cited),
                    words, nr.body_words(md), ",".join(sorted(set(finishes))))
    except (requests.RequestException, RuntimeError, KeyError, ValueError) as exc:
        code = 1
        (run / "error.txt").write_text(str(exc))
        logger.error("%s failed: %s", tid, exc)
    (run / "usage.json").write_text(json.dumps(usage, indent=1))
    (run / "finish_reason").write_text(",".join(finishes) + "\n")
    (run / "exit_code").write_text(f"{code}\n")
    (run / "finished_at").write_text(nr.now() + "\n")


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--topics", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--pool-from", type=Path, required=True)
    ap.add_argument("--match-length-of", type=Path, nargs="+", required=True)
    ap.add_argument("--model", default="deepseek/deepseek-v4.1-flash")
    ap.add_argument("--max-tokens", type=int, default=64000)
    ap.add_argument("--abstract-chars", type=int, default=1200)
    ap.add_argument("--parallel", type=int, default=3, help="topics at once")
    ap.add_argument("--parallel-sections", type=int, default=4)
    ap.add_argument("--only", default="")
    args = ap.parse_args()
    token = os.environ["PAPERBYPASS_AUTH_TOKEN"]
    topics = json.loads(args.topics.read_text())
    if args.only:
        topics = [t for t in topics if t["topic_id"] in set(args.only.split(","))]
    with ThreadPoolExecutor(args.parallel) as pool:
        for t in topics:
            pool.submit(run_topic, t["topic_id"], t["topic"], args.out, args.model, token, args.max_tokens,
                        args.pool_from, args.match_length_of, args.abstract_chars, args.parallel_sections)
    return 0


if __name__ == "__main__":
    sys.exit(main())
