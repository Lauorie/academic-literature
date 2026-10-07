#!/usr/bin/env python3
"""Naive RAG baseline for DAS-Bench under the same retrieval and generator as the skill.

One retrieval call (the skill's own wis-scholar-search quick_search, query = topic, top-N)
and one generation call (same gateway model). The model may cite only the retrieved papers,
by their list index; the References section is built from the retrieval records, never by
the model, so no citation can be invented.

Writes, per topic, <out>/<tid>/review/literature.md and records.json (cited records in
citation order), plus exit_code / started_at / finished_at / usage.json, mirroring the
skill runs so the same conversion (make_submission.py) applies.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, List

import requests

logger = logging.getLogger(__name__)

SEARCH = Path.home() / ".claude/skills/academic-literature/scripts/wis_mcp_search.py"
GATEWAY = "https://aigateway.paperbypass.com/api/v1/chat/completions"
MIN_RETRIEVED = 10
PROMPT = """You are writing a comprehensive academic survey of the field on the topic:

"{topic}"

Use ONLY the {n} papers listed below. Cite them with their list numbers in square brackets, e.g. [3] or [2, 7]. Do not cite anything else and do not write a reference list; it is added automatically.

Write the survey in English Markdown: a title, an abstract, an introduction, thematic sections organized by the field's main research questions, a critical discussion, open problems and future directions, and a conclusion. Synthesize across papers rather than summarizing them one by one.{length_rule}

Papers:
{papers}
"""


LENGTH_RULE = "\nThe survey body, not counting the reference list, should be about {words} words long."


def body_words(md: str) -> int:
    """Words before the first References heading (the length measure of length_matched/PROTOCOL.md)."""
    return len(re.split(r"\n#+\s*References\b", md, flags=re.I)[0].split())


def target_words(tid: str, runs: List[Path]) -> int:
    """Mean body length of the topic's skill runs, rounded to the nearest 100."""
    counts = [body_words((r / tid / "review" / "literature.md").read_text()) for r in runs]
    return int(round(sum(counts) / len(counts), -2))


def now() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def retrieve(topic: str, top_n: int) -> List[Dict[str, Any]]:
    res = subprocess.run([sys.executable, str(SEARCH), topic, "--topn", str(top_n), "-q"],
                         capture_output=True, text=True, timeout=900)
    if res.returncode != 0:
        raise RuntimeError(f"retrieval failed ({res.returncode}): {res.stderr[-400:]}")
    return json.loads(res.stdout)["papers"]


def pool_from_ledger(run_dir: Path) -> List[Dict[str, Any]]:
    """All active records of a skill run's citation ledger: the skill's own candidate pool."""
    sys.path.insert(0, str(SEARCH.parent))
    import citation_ledger as cl  # noqa: E402
    return [e.record for e in cl.Ledger.load(run_dir / "review" / "citations.jsonl").active().values()]


def drop_excluded(papers: List[Dict[str, Any]], exclude_file: Path | None) -> tuple:
    """SurveyBench only: drop the topic's held-out human reference survey (same rule as the skill's search filter)."""
    if exclude_file is None:
        return papers, None
    ex = json.loads(exclude_file.read_text(encoding="utf-8"))
    norm = lambda s: re.sub(r"[^a-z0-9]+", " ", str(s or "").lower()).strip()  # noqa: E731
    titles = {norm(t) for t in ex.get("titles") or [ex["title"]]}
    aid, dois = ex.get("arxiv_id"), [d.lower() for d in ex["dois"]]

    def hit(p: Dict[str, Any]) -> bool:
        blob = " ".join(str(p.get(k) or "") for k in ("arxiv_id", "doi", "url", "pdf_url")).lower()
        return norm(p.get("title")) in titles or bool(aid and aid in blob) or any(d in blob for d in dois)

    kept = [p for p in papers if not hit(p)]
    return kept, len(papers) - len(kept)


def paper_block(i: int, p: Dict[str, Any], abstract_chars: int) -> str:
    authors = ", ".join((p.get("authors") or [])[:4])
    abstract = (p.get("abstract") or "N/A").replace("\n", " ")[:abstract_chars]
    return f"[{i}] {p.get('title')} ({authors}; {p.get('venue') or 'n/a'}, {p.get('year') or 'n/a'})\nAbstract: {abstract}"


def generate(prompt: str, model: str, token: str, max_tokens: int) -> Dict[str, Any]:
    r = requests.post(GATEWAY, headers={"Authorization": f"Bearer {token}"}, timeout=1800,
                      json={"model": model, "messages": [{"role": "user", "content": prompt}],
                            "max_tokens": max_tokens, "temperature": 0.7})
    r.raise_for_status()
    return r.json()


def render(text: str, papers: List[Dict[str, Any]]) -> tuple[str, List[Dict[str, Any]]]:
    """Renumber citations by first appearance and append a References section."""
    order: List[int] = []
    group_re = re.compile(r"\[(\s*\d+(?:\s*[,;–-]\s*\d+)*\s*)\]")

    def expand(g: str) -> List[int]:
        out: List[int] = []
        for part in re.split(r"[,;]", g):
            part = part.strip()
            if re.fullmatch(r"\d+\s*[–-]\s*\d+", part):
                a, b = [int(x) for x in re.split(r"[–-]", part)]
                out.extend(range(a, b + 1) if 0 < b - a < 30 else [a, b])
            elif part.isdigit():
                out.append(int(part))
        return [k for k in out if 1 <= k <= len(papers)]

    for m in group_re.finditer(text):
        for k in expand(m.group(1)):
            if k not in order:
                order.append(k)
    new = {old: i for i, old in enumerate(order, start=1)}

    def sub(m: re.Match) -> str:
        ks = [new[k] for k in dict.fromkeys(expand(m.group(1)))]
        return "[" + ",".join(str(k) for k in ks) + "]" if ks else m.group(0)

    body = group_re.sub(sub, text).rstrip()
    body = re.split(r"^#{1,3}\s*References\s*$", body, flags=re.M | re.I)[0].rstrip()
    refs = []
    for i, old in enumerate(order, start=1):
        p = papers[old - 1]
        link = f"https://doi.org/{p['doi']}" if p.get("doi") else (p.get("url") or "")
        authors = ", ".join((p.get("authors") or [])[:3]) + (", et al" if len(p.get("authors") or []) > 3 else "")
        where = ", ".join(str(x) for x in (p.get("venue"), p.get("year")) if x)
        parts = [f"{authors}." if authors else "", f"*{str(p.get('title')).rstrip('.')}.*", f"{where}." if where else "", link]
        refs.append(f"{i}. " + " ".join(x for x in parts if x))
    return body + "\n\n## References\n\n" + "\n".join(refs) + "\n", [papers[o - 1] for o in order]


def run_topic(tid: str, topic: str, out: Path, model: str, token: str, top_n: int, max_tokens: int,
              pool_from: Path | None, abstract_chars: int, exclude_dir: Path | None = None,
              match_length_of: List[Path] | None = None) -> None:
    run = out / tid
    if (run / "exit_code").exists():
        return
    (run / "review").mkdir(parents=True, exist_ok=True)
    (run / "started_at").write_text(now() + "\n")
    code = 0
    try:
        attempts = 1
        if (run / "retrieved.json").exists():
            # Resuming a run whose generation failed: keep its retrieval, do not re-query.
            source = json.loads((run / "retrieved.json").read_text())
        elif pool_from:
            source = pool_from_ledger(pool_from / tid)
        else:
            source = retrieve(topic, top_n)
            if len(source) < MIN_RETRIEVED:
                # Protocol rule, applied to every topic: one retry when the search returns
                # fewer than MIN_RETRIEVED papers; keep the larger result.
                attempts = 2
                again = retrieve(topic, top_n)
                source = again if len(again) > len(source) else source
        (run / "retrieval_attempts").write_text(f"{attempts}\n")
        papers = [p for p in source if str(p.get("title") or "").strip()]
        papers, n_excluded = drop_excluded(papers, exclude_dir / f"{tid}.json" if exclude_dir else None)
        if n_excluded is not None:
            (run / "excluded_reference").write_text(f"{n_excluded}\n")
        (run / "retrieved.json").write_text(json.dumps(papers, ensure_ascii=False, indent=1))
        length_rule = ""
        if match_length_of:
            words = target_words(tid, match_length_of)
            (run / "target_words").write_text(f"{words}\n")
            length_rule = LENGTH_RULE.format(words=words)
        prompt = PROMPT.format(topic=topic, n=len(papers), length_rule=length_rule,
                               papers="\n\n".join(paper_block(i, p, abstract_chars) for i, p in enumerate(papers, 1)))
        # Protocol rule, applied to every topic: one retry of the generation call (same prompt)
        # when it returns no text, e.g. when reasoning exhausts the output budget.
        for gen_attempt in (1, 2):
            resp = generate(prompt, model, token, max_tokens)
            text = resp["choices"][0]["message"].get("content") or ""
            if text.strip():
                break
        (run / "generation_attempts").write_text(f"{gen_attempt}\n")
        (run / "usage.json").write_text(json.dumps(resp.get("usage", {}), indent=1))
        if not text.strip():
            raise RuntimeError(f"empty completion (finish_reason={resp['choices'][0].get('finish_reason')})")
        md, cited = render(text, papers)
        (run / "review" / "literature.md").write_text(md)
        (run / "review" / "records.json").write_text(json.dumps(cited, ensure_ascii=False, indent=1))
        (run / "finish_reason").write_text(f"{resp['choices'][0].get('finish_reason')}\n")
        logger.info("%s: %d retrieved, %d cited, finish=%s, body=%d words", tid, len(papers), len(cited),
                    resp["choices"][0].get("finish_reason"), body_words(md))
    except (requests.RequestException, RuntimeError, KeyError, ValueError) as exc:
        code = 1
        (run / "error.txt").write_text(str(exc))
        logger.error("%s failed: %s", tid, exc)
    (run / "exit_code").write_text(f"{code}\n")
    (run / "finished_at").write_text(now() + "\n")


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--topics", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--model", default="deepseek/deepseek-v4.1-flash")
    ap.add_argument("--top-n", type=int, default=60)
    ap.add_argument("--max-tokens", type=int, default=32000)
    ap.add_argument("--parallel", type=int, default=3)
    ap.add_argument("--only", default="", help="comma-separated topic ids")
    ap.add_argument("--pool-from", type=Path, default=None,
                    help="use each topic's skill-run ledger (<dir>/<tid>/review/citations.jsonl) as the candidate pool")
    ap.add_argument("--abstract-chars", type=int, default=1200)
    ap.add_argument("--exclude-dir", type=Path, default=None,
                    help="SurveyBench: dir of <tid>.json held-out reference surveys to drop from the candidate list")
    ap.add_argument("--match-length-of", type=Path, nargs="+", default=None,
                    help="skill run dirs; ask for each topic's mean body length over them (length_matched/PROTOCOL.md)")
    args = ap.parse_args()
    token = os.environ["PAPERBYPASS_AUTH_TOKEN"]
    topics = json.loads(args.topics.read_text())
    if args.only:
        keep = set(args.only.split(","))
        topics = [t for t in topics if t["topic_id"] in keep]
    with ThreadPoolExecutor(args.parallel) as pool:
        for t in topics:
            pool.submit(run_topic, t["topic_id"], t["topic"], args.out, args.model, token, args.top_n, args.max_tokens,
                        args.pool_from, args.abstract_chars, args.exclude_dir, args.match_length_of)
    return 0


if __name__ == "__main__":
    sys.exit(main())
