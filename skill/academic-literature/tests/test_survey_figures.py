#!/usr/bin/env python3
"""Tests for survey_figures.py: counts come from the ledger and the outline, figures are written."""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(HERE))
from citation_ledger import mint_key  # noqa: E402
from survey_figures import parse_outline  # noqa: E402

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  {'✓' if cond else '✗'} {name}" + (f"\n      {detail}" if not cond and detail else ""))


def run(*a, cwd):
    return subprocess.run([sys.executable, *a], cwd=cwd, capture_output=True, text=True)


papers = [dict(title=f"Paper number {i} about things", authors=["A B"], venue="V", year=2015 + i % 5,
               doi=f"10.9/{i}", arxiv_id=None, url=None, pdf_url=None, citations=1, abstract="x") for i in range(6)]
keys = [mint_key(p) for p in papers]
outline = f"""# Outline
## 1. First theme (F1)
### 1.1 A question
- claim — {keys[0]} (全文), {keys[1]} (摘要)
### 1.2 Another question
- claim — {keys[2]} (摘要)
## 2. Second theme
### 2.1 Third question
- claim — {keys[3]} (全文); also {keys[0]}
"""
tree = parse_outline(outline)
check("outline: two themes", [t for t, _ in tree] == ["1. First theme (F1)", "2. Second theme"], tree)
check("outline: keys per subsection", [len(k) for _, s in tree for _, k in s] == [2, 1, 2], tree)

with tempfile.TemporaryDirectory() as td:
    td = Path(td)
    (td / "f.json").write_text(json.dumps({"papers": papers, "stats": {}}))
    run(str(HERE / "citation_ledger.py"), "add", "--from-search", "f.json", "--ledger", "l.jsonl", cwd=td)
    run(str(HERE / "citation_ledger.py"), "drop", "--key", keys[5], "--ledger", "l.jsonl", "--reason", "off-topic", cwd=td)
    (td / "d.md").write_text("# T\n" + " ".join(f"x [{k}]." for k in keys[:4]) + "\n")
    (td / "o.md").write_text(outline)
    ev = td / "ev"; ev.mkdir()
    (ev / f"{keys[0]}.md").write_text("**来源：全文**\n")
    (ev / f"{keys[1]}.md").write_text("**来源：abstract-only（全文不可得）**\n")
    r = run(str(HERE / "survey_figures.py"), "stats", "--ledger", "l.jsonl", "--draft", "d.md", "--evidence", "ev", cwd=td)
    st = json.loads(r.stdout)
    check("stats: identified, dropped, retained, cited",
          (st["identified_unique"], st["dropped"], st["retained"], st["cited"]) == (6, 1, 5, 4), st)
    check("stats: drop reason recorded", st["drop_reasons"] == {"off-topic": 1}, st)
    check("stats: read depth from evidence headers (abstract-only is not counted as full text)",
          st["cited_read_depth"] == {"full text": 1, "abstract": 1, "no evidence file": 2}, st)
    try:
        import matplotlib  # noqa: F401
        has_mpl = True
    except ImportError:
        has_mpl = False
    r1 = run(str(HERE / "survey_figures.py"), "timeline", "--ledger", "l.jsonl", "--draft", "d.md", "--outline", "o.md",
             "--out", "t.png", cwd=td)
    r2 = run(str(HERE / "survey_figures.py"), "taxonomy", "--outline", "o.md", "--title", "Topic", "--out", "x.png", cwd=td)
    if has_mpl:
        check("timeline png written", r1.returncode == 0 and (td / "t.png").stat().st_size > 1000, r1.stderr)
        check("taxonomy png written", r2.returncode == 0 and (td / "x.png").stat().st_size > 1000, r2.stderr)
    else:
        check("without matplotlib: exit 4 with install hint", r1.returncode == 4 and "pip install" in r1.stderr, r1.stderr)

print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
sys.exit(1 if FAIL else 0)
