#!/usr/bin/env python3
"""N11 (second re-review): facts on how the Skill-Full and NoSkill-Agent DAS-Bench runs differ besides the skill.

Descriptive, no test. Per DAS-Bench condition: the dates its sessions started (started_at) and the dates its
judgments were written (evaluated_at of every metric family, both judges), in UTC+8. For the Skill-Full and
NoSkill-Agent sessions: the Claude Code version and tools in each stream's init event. For NoSkill-Agent: the
papers whose full text reached the agent, in two ways. Web: a WebFetch of an ar5iv page or an arXiv HTML or PDF page
whose result describes the paper (not an error, an unfollowed redirect, or the fetch model's statement that the page
was unreadable); WebFetch hands back a digest written by a model, not the page. PDF: a PDF the agent converted to text
and then printed, counted by the .txt file names its commands read (an arXiv id in the name, or ALIAS).
Usage: n11_facts.py <das_eval dir> <out.json>
"""

from __future__ import annotations

import glob
import json
import logging
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Set

logger = logging.getLogger(__name__)
TZ = timezone(timedelta(hours=8))
JUDGES = {"main": "DAS-Bench", "cross": "DAS-Bench-xjudge"}
CONDITIONS = {  # condition: (pulled run dir or None, judged method)
    "Skill-Full r1": ("deepseek-v4.1-flash", "skill_deepseek-v4.1-flash"),
    "Skill-Full r2": ("deepseek-v4.1-flash_full_r2", "skill_deepseek-v4.1-flash_full_r2"),
    "Skill-Full r3": ("deepseek-v4.1-flash_full_r3", "skill_deepseek-v4.1-flash_full_r3"),
    "Skill-Abs": ("deepseek-v4.1-flash_abs_r1", "skill_deepseek-v4.1-flash_abs_r1"),
    "Opus pilot": ("claude-opus-5.5", "skill_claude-opus-5.5"),
    "NaiveRAG-Own": (None, "naiverag-deepseek-v4.1-flash_own_r1"),
    "NaiveRAG-Pool": (None, "naiverag-deepseek-v4.1-flash_pool_r1"),
    "NaiveRAG-Pool-Long": (None, "naiverag-deepseek-v4.1-flash_poollong_r1"),
    "NoSkill-Agent": ("deepseek-v4.1-flash_noskill_r1", "noskill_deepseek-v4.1-flash_r1"),
}
AGENT_RUNS = ["Skill-Full r1", "Skill-Full r2", "Skill-Full r3", "NoSkill-Agent"]
FULLTEXT_URL = re.compile(r"ar5iv|arxiv\.org/(pdf|html)/|\.pdf($|\?)")
ARXIV_ID = re.compile(r"\d{4}\.\d{4,5}")
NO_CONTENT = re.compile(r"^(REDIRECT DETECTED|I can't|I cannot)|rather than readable text")
TXT_NAME = re.compile(r"([\w.:-]+)\.txt\b")
# Session 020 saved its WebFetch of arxiv.org/pdf/2102.11107 (unreadable to the fetch model) and copied the
# file to scholkopf2021.pdf before converting it (cp command in the trace).
ALIAS = {("020", "scholkopf2021"): "2102.11107"}


def day(ts: str) -> str:
    return datetime.fromisoformat(ts).astimezone(TZ).strftime("%Y-%m-%d")


def sessions(run: str, root: Path) -> List[Path]:
    return sorted(Path(p) for p in glob.glob(str(root / "pulled" / run / "[0-9][0-9][0-9]")))


def events(stream: Path):
    with stream.open() as f:
        for line in f:
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def fulltext_papers(stream: Path, sid: str) -> Dict[str, Set[str]]:
    uses, got = {}, {"web": set(), "pdf": set()}
    for e in events(stream):
        content = e.get("message", {}).get("content")
        if not isinstance(content, list):
            continue
        for x in content:
            if x.get("type") == "tool_use" and x["name"] in ("WebFetch", "Bash"):
                uses[x["id"]] = (x["name"], x.get("input", {}))
            elif x.get("type") == "tool_result" and x.get("tool_use_id") in uses and not x.get("is_error"):
                body = x.get("content")
                body = body if isinstance(body, str) else " ".join(y.get("text", "") for y in body or []
                                                                   if isinstance(y, dict))
                name, inp = uses[x["tool_use_id"]]
                if name == "WebFetch" and FULLTEXT_URL.search(url := inp.get("url", "")) \
                        and not NO_CONTENT.search(body):
                    ids = ARXIV_ID.findall(url)
                    got["web"].add(ids[0] if ids else url)
                elif name == "Bash" and "open(" in (cmd := inp.get("command", "")) and len(body) > 1000:
                    for stem in TXT_NAME.findall(cmd):
                        pid = ALIAS.get((sid, stem)) or next(iter(ARXIV_ID.findall(stem)), None)
                        if pid:
                            got["pdf"].add(pid)
    return got


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    root, out = Path(sys.argv[1]), Path(sys.argv[2])
    res: Dict = {"conditions": {}}
    for cond, (run, method) in CONDITIONS.items():
        r: Dict = {"judged": {}}
        for j, bench in JUDGES.items():
            files = glob.glob(str(root / "remote_results" / bench / method / "*/api_off/*.json"))
            r["judged"][j] = {"n": len(files),
                              "dates": sorted({day(json.loads(Path(f).read_text())["evaluated_at"]) for f in files})}
        if run:
            r["generated"] = sorted({day((s / "started_at").read_text().strip())
                                     for s in sessions(run, root) if (s / "started_at").exists()})
        res["conditions"][cond] = r
    versions, tools = {}, {}
    for cond in AGENT_RUNS:
        v, t = set(), set()
        for s in sessions(CONDITIONS[cond][0], root):
            init = next((e for e in events(s / "stream.jsonl")
                         if e.get("type") == "system" and e.get("subtype") == "init"), {})
            v.add(init.get("claude_code_version"))
            t.add(tuple(sorted(init.get("tools", []))))
        versions[cond], tools[cond] = sorted(v), [list(x) for x in t]
    res["claude_code_versions"] = versions
    res["tools"] = tools
    per = {s.name: fulltext_papers(s / "stream.jsonl", s.name) for s in sessions(CONDITIONS["NoSkill-Agent"][0], root)}
    both = {k: v["web"] | v["pdf"] for k, v in per.items()}
    res["noskill_fulltext"] = {"sessions": len(per), "sessions_with_any": sum(bool(v) for v in both.values()),
                               "papers": sum(len(v) for v in both.values()),
                               "papers_web": sum(len(v["web"] - v["pdf"]) for v in per.values()),
                               "papers_pdf": sum(len(v["pdf"]) for v in per.values()),
                               "max_in_one_session": max(len(v) for v in both.values()),
                               "per_session": {k: {"web": sorted(v["web"]), "pdf": sorted(v["pdf"])}
                                               for k, v in per.items() if both[k]}}
    out.write_text(json.dumps(res, indent=1) + "\n")
    logger.info(json.dumps({k: v for k, v in res.items() if k != "tools"}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
