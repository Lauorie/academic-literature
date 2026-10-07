#!/usr/bin/env python3
"""Grade submission-mode test runs (skill-creator layout) with programmatic checks.

For each eval in academic-literature-workspace/evals.json and each configuration (with_skill = v4, old_skill = v3
under the same prompt), reads the pulled run, copies the deliverables into
iteration-1/eval-<name>/<config>/run-1/outputs/, and writes grading.json and timing.json there.
Usage: grade_sub.py
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

H = Path("/home/juli/citation/DAS/das_eval")
W = H / "skillrefine/v4/academic-literature-workspace"
SCRIPTS = H / "skillrefine/v4/academic-literature/scripts"
ITER = int(sys.argv[1]) if len(sys.argv) > 1 else 1
# with_skill = v4 of that iteration; old_skill = v3 under the same prompt (run once, in iteration 1, and reused).
WITH = {1: ("deepseek-v4.1-flash_sub_v4", "deepseek-v4.1-flash_sub_v4_sl"),
        2: ("deepseek-v4.1-flash_sub_v4b", "deepseek-v4.1-flash_sub_v4b_sl")}
RUNS = {"with_skill": WITH[ITER], "old_skill": ("deepseek-v4.1-flash_sub_v3base", "deepseek-v4.1-flash_sub_v3base_sl")}


def body_and_refs(md: str) -> tuple[str, list[str]]:
    parts = re.split(r"\n#+\s*References\b", md, maxsplit=1, flags=re.I)
    refs = re.findall(r"^\[\d+\].*$", parts[1], re.M) if len(parts) > 1 else []
    return parts[0], refs


def section(md: str, pattern: str) -> str:
    m = re.search(rf"^##[ \t]+[^\n]*{pattern}[^\n]*\n(.*?)(?=^##[ \t])", md, re.M | re.S | re.I)
    return m.group(m.lastindex) if m else ""  # the last group is the body; the pattern may carry its own group


def grade(run: Path) -> list[dict]:
    rv = run / "review"
    md = (rv / "literature.md").read_text(errors="replace") if (rv / "literature.md").exists() else ""
    body, refs = body_and_refs(md)
    words = len(body.split())
    h2 = re.findall(r"^## (?!#)(.+)$", body, re.M)
    h3 = re.findall(r"^### (?!#)", body, re.M)
    out = []

    def add(text: str, passed: bool, evidence: str) -> None:
        out.append({"text": text, "passed": bool(passed), "evidence": evidence})

    add("cites at least 100 papers", len(refs) >= 100, f"{len(refs)} reference entries")
    add("body of at least 12,000 words", words >= 12000, f"{words} words before References")
    add("body of at most 22,000 words", 0 < words <= 22000, f"{words} words before References")
    add("has an Abstract section", any(re.search(r"abstract|摘要", h, re.I) for h in h2), f"## headings: {h2[:12]}")
    meth = section(md, r"(methodolog|method|方法)")
    add("has a survey-methodology section", bool(meth.strip()), f"{len(meth.split())} words in the methods section")
    stats = {}
    if (rv / "citations.jsonl").exists() and (rv / "literature.draft.md").exists():
        r = subprocess.run([sys.executable, str(SCRIPTS / "survey_figures.py"), "stats", "--ledger", str(rv / "citations.jsonl"),
                            "--draft", str(rv / "literature.draft.md")], capture_output=True, text=True)
        stats = json.loads(r.stdout) if r.returncode == 0 else {}
    cited = stats.get("cited")
    add("methods section states the tool-computed number of cited papers",
        bool(cited) and re.search(rf"\b{cited}\b", meth) is not None, f"stats cited={cited}; found in methods: "
        f"{bool(cited) and re.search(rf'{cited}', meth) is not None}")
    # The harness used to delete every PNG under review/ after a session, figures included, so a figure counts as
    # produced when the file exists or the session log shows survey_figures.py writing it.
    log = (run / "stream.jsonl").read_text(errors="replace") if (run / "stream.jsonl").exists() else ""
    figs = [f for f in ("taxonomy.png", "timeline.png")
            if (rv / "figures" / f).exists() or re.search(rf"{f.split('.')[0]}: \d+ [^\n\\]*-> [^\s\\]*figures/{f}", log)]
    add("taxonomy and timeline figures exist and are embedded",
        len(figs) == 2 and all(f"figures/{f}" in md for f in figs), f"files: {figs}; embedded: "
        f"{[f for f in ('taxonomy.png', 'timeline.png') if f'figures/{f}' in md]}")
    add("at least 5 themes and 10 subsections", len(h2) >= 8 and len(h3) >= 10, f"{len(h2)} ## and {len(h3)} ### headings")
    ho = (rv / "handoff.md").read_text(errors="replace") if (rv / "handoff.md").exists() else ""
    add("handoff.md lists what the author must still do", len(ho.split()) >= 150, f"{len(ho.split())} words")
    log = rv / "search_log.tsv"
    nlog = len([x for x in log.read_text(errors="replace").splitlines()[1:] if x.strip()]) if log.exists() else 0
    add("scope.md and a search log with at least 20 calls", (rv / "scope.md").exists() and nlog >= 20,
        f"scope.md: {(rv / 'scope.md').exists()}; search_log rows: {nlog}")
    chk = ""
    if (rv / "citations.jsonl").exists() and md:
        r = subprocess.run([sys.executable, str(SCRIPTS / "citation_ledger.py"), "check", "--draft", str(rv / "literature.draft.md"),
                            "--ledger", str(rv / "citations.jsonl"), "--review", str(rv / "literature.md")],
                           capture_output=True, text=True)
        chk = r.stdout + r.stderr
    hard = re.search(r"hard failures:\s*(\d+)", chk)
    add("citation check: zero hard failures", hard is not None and hard.group(1) == "0",
        hard.group(0) if hard else "check did not run")
    core_full, core_n = 0, 0
    man = rv / "manifest.tsv"
    if man.exists():
        import csv
        sys.path.insert(0, str(SCRIPTS))
        from survey_figures import _depth  # noqa: E402
        rows = list(csv.DictReader(man.open(encoding="utf-8", errors="replace"), delimiter="\t"))
        kc = next((c for c in (rows[0] if rows else {}) if c and c.lower() in ("key", "ledger_key")), None)
        tc = next((c for c in (rows[0] if rows else {}) if c and c.lower() == "tier"), None)
        if kc and tc:
            core = [r[kc].strip() for r in rows if (r.get(tc) or "").strip().lower() == "core"]
            core_n = len(core)
            core_full = sum(_depth(rv / "evidence", k) == "full text" for k in core)
    add("at least 25 core papers read in full text", core_full >= 25, f"{core_full} of {core_n} core papers have full-text evidence")
    na = sum("[venue unavailable]" in x for x in refs) / max(1, len(refs))
    add("at most 25% of references lack a venue", na <= 0.25 and refs != [], f"{na:.0%} [venue unavailable]")
    return out


def timing(run: Path) -> dict:
    """Tokens and duration from the session's result event; wall time from started_at/finished_at as fallback."""
    import datetime as dt

    res: dict = {}
    s = run / "stream.jsonl"
    if s.exists():
        for line in s.open(errors="replace"):
            if '"result"' not in line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            if d.get("type") == "result":
                u = d.get("usage") or {}
                res = {"total_tokens": sum(v for k, v in u.items() if k.endswith("tokens") and isinstance(v, int)),
                       "duration_ms": d.get("duration_ms")}
    try:
        a = dt.datetime.fromisoformat((run / "started_at").read_text().strip())
        b = dt.datetime.fromisoformat((run / "finished_at").read_text().strip())
        res.setdefault("duration_ms", int((b - a).total_seconds() * 1000))
    except (FileNotFoundError, ValueError):
        pass
    res.setdefault("total_tokens", 0)
    res["total_duration_seconds"] = round((res.get("duration_ms") or 0) / 1000, 1)
    return res


def main() -> int:
    evals = json.loads((W / "evals.json").read_text())["evals"]
    for ev in evals:
        for cfg, (das_dir, sl_dir) in RUNS.items():
            run = H / "pulled" / (sl_dir if ev["tid"].startswith("sl") else das_dir) / ev["tid"]
            if not (run / "exit_code").exists():
                print("not finished:", cfg, ev["tid"])
                continue
            rd = W / f"iteration-{ITER}" / f"eval-{ev['name']}" / cfg / "run-1"
            (rd / "outputs").mkdir(parents=True, exist_ok=True)
            for f in ("literature.md", "handoff.md", "scope.md", "outline.md", "search_log.tsv"):
                if (run / "review" / f).exists():
                    shutil.copy(run / "review" / f, rd / "outputs" / f)
            if (run / "review/figures").is_dir():
                shutil.copytree(run / "review/figures", rd / "outputs/figures", dirs_exist_ok=True)
            exp = grade(run)
            n = sum(e["passed"] for e in exp)
            t = timing(run)
            (rd / "timing.json").write_text(json.dumps(t, indent=1))
            (rd / "grading.json").write_text(json.dumps({"expectations": exp, "summary": {
                "passed": n, "failed": len(exp) - n, "total": len(exp), "pass_rate": round(n / len(exp), 2)},
                "timing": {"total_duration_seconds": t.get("total_duration_seconds")}}, indent=1, ensure_ascii=False))
            meta = W / f"iteration-{ITER}" / f"eval-{ev['name']}" / "eval_metadata.json"
            meta.write_text(json.dumps({"eval_id": ev["id"], "eval_name": ev["name"], "prompt": ev["prompt"],
                                        "assertions": [e["text"] for e in exp]}, indent=1, ensure_ascii=False))
            print(f"{ev['name']:16s} {cfg:10s} {n}/{len(exp)}  " + " ".join("✓" if e["passed"] else "✗" for e in exp))
    return 0


if __name__ == "__main__":
    sys.exit(main())
