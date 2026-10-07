#!/usr/bin/env python3
"""Summarize token usage, cost, tool calls and wall time for generation runs.

Usage: run_stats.py <runs_root> [--json out.json]
Cost uses PaperBypass gateway list prices (USD per 1M tokens) fetched 2026-09-29.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict

PRICES = {  # input, output, cache_read, cache_write
    "claude-opus-5.5": (4.0, 20.0, 0.2, 1.3),
    "deepseek-v4.1-flash": (0.12, 0.48, 0.03, 0.195),
}


def run_summary(run: Path) -> Dict[str, Any]:
    tools: Counter = Counter()
    usage = Counter()
    result: Dict[str, Any] = {}
    seen_ids = set()
    stream = run / "stream.jsonl"
    for line in stream.open(encoding="utf-8", errors="replace") if stream.exists() else []:
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if ev.get("type") == "assistant":
            msg = ev.get("message", {})
            for c in msg.get("content", []):
                if c.get("type") == "tool_use":
                    tools[c.get("name")] += 1
            if msg.get("id") not in seen_ids:  # one API response may span several events
                seen_ids.add(msg.get("id"))
                u = msg.get("usage") or {}
                for k in ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"):
                    usage[k] += int(u.get(k) or 0)
        elif ev.get("type") == "result":
            result = ev
    # Per-message usage in the stream is the message_start snapshot (output tokens ~0);
    # the final result event carries the true session totals, so prefer it.
    # modelUsage also covers subagents, so it is the fuller total.
    if result.get("modelUsage"):
        usage = Counter()
        for mu in result["modelUsage"].values():
            usage["input_tokens"] += int(mu.get("inputTokens") or 0)
            usage["output_tokens"] += int(mu.get("outputTokens") or 0)
            usage["cache_read_input_tokens"] += int(mu.get("cacheReadInputTokens") or 0)
            usage["cache_creation_input_tokens"] += int(mu.get("cacheCreationInputTokens") or 0)
    model = run.parent.name
    # Run dirs are named <model>[_<mode>_<rep>]; price by the model part.
    p = PRICES.get(model) or next((v for k, v in PRICES.items() if model.startswith(k + "_")), (0, 0, 0, 0))
    cost = (usage["input_tokens"] * p[0] + usage["output_tokens"] * p[1]
            + usage["cache_read_input_tokens"] * p[2] + usage["cache_creation_input_tokens"] * p[3]) / 1e6

    def ts(name: str):
        f = run / name
        return dt.datetime.fromisoformat(f.read_text().strip()) if f.exists() else None

    start, end = ts("started_at"), ts("finished_at")
    review = run / "review"
    return {
        "model": model,
        "topic_id": run.name,
        "exit_code": (run / "exit_code").read_text().strip() if (run / "exit_code").exists() else None,
        "result_subtype": result.get("subtype"),
        "num_turns": result.get("num_turns"),
        "wall_min": round((end - start).total_seconds() / 60, 1) if start and end else None,
        "api_calls": len(seen_ids),
        "tool_calls": dict(tools),
        "usage": dict(usage),
        "cost_usd": round(cost, 3),
        "has_literature_md": (review / "literature.md").exists(),
        "n_evidence_files": len(list((review / "evidence").glob("*.md"))) if (review / "evidence").exists() else 0,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("runs_root", type=Path)
    ap.add_argument("--json", type=Path, default=None)
    args = ap.parse_args()
    rows = [run_summary(r) for r in sorted(args.runs_root.glob("*/*")) if r.is_dir()]
    for r in rows:
        sys.stdout.write(json.dumps(r, ensure_ascii=False) + "\n")
    if args.json:
        args.json.write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
