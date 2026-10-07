#!/usr/bin/env python3
"""Numbers and figures for a submission-grade review, computed from the ledger and the outline.

Nothing here is typed by the model: counts come from citations.jsonl, the draft and the evidence files;
figures are drawn from those counts and from outline.md. That keeps the methodology section and the
figures under the same guarantee as the reference list.

Subcommands:
    stats     --ledger L [--draft D] [--evidence DIR]          JSON: identified / dropped / cited / years / read depth
    timeline  --ledger L --draft D --outline O --out fig.png   cited papers per year, stacked by theme
    taxonomy  --outline O --title T --out fig.png              theme -> subsection tree with paper counts

Figures need matplotlib; without it they exit 4 with an install hint and the review goes on without them.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import textwrap
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
from citation_ledger import KEY_RE, Ledger, collect_keys  # noqa: E402

THEME_RE = re.compile(r"^##\s+(?!#)(.+?)\s*$")
SUB_RE = re.compile(r"^###\s+(?!#)(.+?)\s*$")


def parse_outline(text: str) -> List[Tuple[str, List[Tuple[str, List[str]]]]]:
    """[(theme, [(subsection, [keys...]), ...]), ...] in outline order; keys under a theme but
    before its first subsection go to a subsection named ''."""
    themes: List[Tuple[str, List[Tuple[str, List[str]]]]] = []
    for line in text.splitlines():
        if m := THEME_RE.match(line):
            themes.append((m.group(1), []))
        elif (m := SUB_RE.match(line)) and themes:
            themes[-1][1].append((m.group(1), []))
        elif themes and (keys := KEY_RE.findall(line)):
            if not themes[-1][1]:
                themes[-1][1].append(("", []))
            sub = themes[-1][1][-1][1]
            sub.extend(k for k in keys if k not in sub)
    return themes


def _drop_reasons(path: Path) -> Counter:
    reasons: Counter = Counter()
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            ev = json.loads(line)
            if ev.get("event") == "drop":
                reasons[(ev.get("reason") or "unspecified").strip()[:60]] += 1
    return reasons


def _depth(evidence: Path, key: str) -> str:
    f = evidence / f"{key}.md"
    if not f.exists():
        return "no evidence file"
    head = f.read_text(encoding="utf-8", errors="replace")[:600].lower()
    if "abstract-only" in head or "abstract only" in head or "摘要" in head:
        return "abstract"
    if "全文" in head or "full text" in head:
        return "full text"
    return "unlabeled"


def cmd_stats(args: argparse.Namespace) -> int:
    path = Path(args.ledger)
    ledger = Ledger.load(path)
    active = ledger.active()
    out: Dict[str, object] = {"identified_unique": len(ledger.entries), "dropped": len(ledger.dropped),
                              "drop_reasons": dict(_drop_reasons(path).most_common()), "retained": len(active)}
    if args.draft:
        cited = [k for k in collect_keys(Path(args.draft).read_text(encoding="utf-8")) if k in active]
        out["cited"] = len(cited)
        years = Counter(str(active[k].record.get("year") or "n.d.") for k in cited)
        out["cited_by_year"] = dict(sorted(years.items()))
        if args.evidence:
            out["cited_read_depth"] = dict(Counter(_depth(Path(args.evidence), k) for k in cited))
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0


def _plt():
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        return plt
    except ImportError:
        sys.stderr.write("matplotlib is not installed: `python3 -m pip install --user matplotlib`, then re-run. "
                         "If it cannot be installed, deliver without figures and list them in handoff.md.\n")
        sys.exit(4)


def _short(label: str, width: int) -> str:
    label = re.sub(r"\s*\(F\d+\)\s*$", "", label)  # facet tags from the outline
    return "\n".join(textwrap.wrap(label, width)[:3])


def cmd_timeline(args: argparse.Namespace) -> int:
    plt = _plt()
    active = Ledger.load(Path(args.ledger)).active()
    cited = [k for k in collect_keys(Path(args.draft).read_text(encoding="utf-8")) if k in active]
    theme_of: Dict[str, str] = {}
    for theme, subs in parse_outline(Path(args.outline).read_text(encoding="utf-8")):
        for _, keys in subs:
            for k in keys:
                theme_of.setdefault(k, theme)
    counts: Dict[str, Counter] = defaultdict(Counter)
    for k in cited:
        y = str(active[k].record.get("year") or "").strip()
        if y.isdigit():
            counts[theme_of.get(k, "Other")][int(y)] += 1
    if not counts:
        sys.stderr.write("no cited paper has a year; no timeline drawn\n")
        return 1
    years = list(range(min(min(c) for c in counts.values()), max(max(c) for c in counts.values()) + 1))
    themes = [t for t in dict.fromkeys(list(theme_of.values()) + ["Other"]) if t in counts]
    fig, ax = plt.subplots(figsize=(max(7, len(years) * 0.35 + 3), 4.2))
    bottom = [0] * len(years)
    for t in themes:
        vals = [counts[t].get(y, 0) for y in years]
        ax.bar(years, vals, bottom=bottom, label=_short(t, 40), width=0.8)
        bottom = [b + v for b, v in zip(bottom, vals)]
    ax.set_xlabel("Publication year")
    ax.set_ylabel("Cited papers")
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(fontsize=7, frameon=False, loc="upper left", bbox_to_anchor=(1.01, 1))
    fig.tight_layout()
    fig.savefig(args.out, dpi=200)
    sys.stderr.write(f"timeline: {sum(bottom)} cited papers with a year, {len(themes)} themes -> {args.out}\n")
    return 0


def cmd_taxonomy(args: argparse.Namespace) -> int:
    plt = _plt()
    tree = parse_outline(Path(args.outline).read_text(encoding="utf-8"))
    tree = [(t, [(s, k) for s, k in subs if s]) for t, subs in tree if any(s for s, _ in subs)]
    if not tree:
        sys.stderr.write("outline has no '## theme' with '### subsection' headings; no taxonomy drawn\n")
        return 1
    rows = sum(len(subs) for _, subs in tree)
    fig, ax = plt.subplots(figsize=(11, max(3.5, rows * 0.42 + 1)))
    ax.axis("off")
    ax.set_xlim(0, 1)
    ax.set_ylim(-0.5, rows + 0.5)
    box = dict(boxstyle="round,pad=0.3", linewidth=0.8)
    root_y = (rows - 1) / 2
    ax.text(0.02, root_y, _short(args.title, 22), va="center", ha="left", fontsize=9, fontweight="bold",
            bbox={**box, "facecolor": "#e8eef7"})
    y = rows - 1
    for theme, subs in tree:
        ys = list(range(y, y - len(subs), -1))
        ty = sum(ys) / len(ys)
        ax.plot([0.2, 0.27], [root_y, ty], color="#888", linewidth=0.7)
        ax.text(0.27, ty, _short(theme, 30), va="center", ha="left", fontsize=8, bbox={**box, "facecolor": "#f4f1e8"})
        for (sub, keys), sy in zip(subs, ys):
            ax.plot([0.5, 0.6], [ty, sy], color="#888", linewidth=0.7)
            ax.text(0.6, sy, f"{_short(sub, 48)}  ({len(keys)})", va="center", ha="left", fontsize=7.5)
        y -= len(subs)
    fig.tight_layout()
    fig.savefig(args.out, dpi=200)
    sys.stderr.write(f"taxonomy: {len(tree)} themes, {rows} subsections -> {args.out}\n")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("stats")
    p.add_argument("--ledger", required=True)
    p.add_argument("--draft")
    p.add_argument("--evidence")
    p.set_defaults(fn=cmd_stats)
    p = sub.add_parser("timeline")
    for a in ("--ledger", "--draft", "--outline", "--out"):
        p.add_argument(a, required=True)
    p.set_defaults(fn=cmd_timeline)
    p = sub.add_parser("taxonomy")
    for a in ("--outline", "--title", "--out"):
        p.add_argument(a, required=True)
    p.set_defaults(fn=cmd_taxonomy)
    args = ap.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
