#!/usr/bin/env python3
"""Per-run process statistics of skill runs: what the agent actually did.

From each run's stream.jsonl and review/ directory: search calls (quick / deep), ledger
adds / drops / active / cited, evidence files and their read depth, sub-agents, whether
`check` was run and passed, turns, wall time and cost.
Usage: process_stats.py <pulled/run-dir-glob ...> --out stats.json
"""

from __future__ import annotations

import argparse
import glob
import json
import re
import statistics as st
import sys
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).parent))
from run_stats import run_summary  # noqa: E402

SKILL_SCRIPTS = Path.home() / ".claude/skills/academic-literature/scripts"


def tool_calls(stream: Path) -> List[Dict[str, Any]]:
    calls: List[Dict[str, Any]] = []
    results: Dict[str, str] = {}
    for line in stream.open(encoding="utf-8", errors="replace"):
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        msg = ev.get("message") if isinstance(ev.get("message"), dict) else {}
        for c in msg.get("content", []) if isinstance(msg.get("content"), list) else []:
            if c.get("type") == "tool_use":
                calls.append({"id": c.get("id"), "name": c.get("name"), "input": c.get("input") or {}})
            elif c.get("type") == "tool_result":
                out = c.get("content")
                results[c.get("tool_use_id")] = out if isinstance(out, str) else json.dumps(out)
    for c in calls:
        c["result"] = results.get(c["id"], "")
    return calls


def run_process(run: Path) -> Dict[str, Any]:
    calls = tool_calls(run / "stream.jsonl")
    bash = [str(c["input"].get("command", "")) for c in calls if c["name"] == "Bash"]
    # Agents call the search script directly or via a shell variable (S=.../wis_mcp_search.py; "$S" ...),
    # often several per command; every search invocation carries --topn, so count those lines.
    search_lines = [ln for cmd in bash for ln in cmd.splitlines()
                    if "--topn" in ln and "citation_ledger" not in ln and not ln.strip().startswith("#")]
    deep = sum("--tool deep_search" in ln for ln in search_lines)
    check_calls = [c for c in calls if c["name"] == "Bash" and "citation_ledger.py check" in str(c["input"].get("command", ""))]
    # The final check decides delivery; earlier ones may fail and be fixed.
    last = check_calls[-1]["result"] if check_calls else ""
    check_pass = bool(re.search(r"hard failures:\s*0\b", last))
    m_warn = re.search(r"warnings\s*:\s*(\d+)", last)
    check_warnings = int(m_warn.group(1)) if m_warn else None

    sys.path.insert(0, str(SKILL_SCRIPTS))
    import citation_ledger as cl  # noqa: E402
    review = run / "review"
    adds = drops = active = cited = ingested_files = 0
    if (review / "citations.jsonl").exists():
        events = [json.loads(ln) for ln in (review / "citations.jsonl").read_text().splitlines() if ln.strip()]
        adds = sum(e.get("event") == "add" for e in events)
        ingested_files = len({(e.get("provenance") or {}).get("file") for e in events if e.get("event") == "add"})
        drops = sum(e.get("event") == "drop" for e in events)
        active = len(cl.Ledger.load(review / "citations.jsonl").active())
    if (review / "literature.draft.md").exists():
        cited = len(set(cl.collect_keys((review / "literature.draft.md").read_text())))
    ev_files = list((review / "evidence").glob("*.md")) if (review / "evidence").exists() else []
    full = abstract = 0
    for f in ev_files:
        head = f.read_text(errors="replace")[:400]
        if re.search(r"全文|full[ -]?text", head, re.I) and not re.search(r"abstract[- ]only|摘要", head, re.I):
            full += 1
        elif re.search(r"abstract|摘要", head, re.I):
            abstract += 1
    s = run_summary(run)
    return {"run": f"{run.parent.name}/{run.name}", "search_calls": len(search_lines), "deep_search_calls": deep, "ingested_result_files": ingested_files,
            "ledger_adds": adds, "ledger_drops": drops, "ledger_active": active, "cited": cited,
            "evidence_files": len(ev_files), "evidence_full": full, "evidence_abstract": abstract,
            "subagents": s["tool_calls"].get("Agent", 0) + s["tool_calls"].get("Task", 0),
            "check_runs": len(check_calls), "check_pass": check_pass, "check_warnings_final": check_warnings, "turns": s["num_turns"],
            "wall_min": s["wall_min"], "cost_usd": s["cost_usd"], "exit_code": s["exit_code"]}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("runs", nargs="+")
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    rows = [run_process(Path(p)) for g in args.runs for p in sorted(glob.glob(g)) if Path(p, "stream.jsonl").exists()]
    keys = [k for k in rows[0] if isinstance(rows[0][k], (int, float)) and not isinstance(rows[0][k], bool)]
    summary = {k: {"mean": round(st.mean(r[k] for r in rows if r[k] is not None), 2),
                   "median": st.median(r[k] for r in rows if r[k] is not None)} for k in keys}
    summary["check_pass_rate"] = round(sum(r["check_pass"] for r in rows) / len(rows), 3)
    summary["n_runs"] = len(rows)
    args.out.write_text(json.dumps({"summary": summary, "runs": rows}, indent=1) + "\n")
    sys.stdout.write(json.dumps(summary, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
