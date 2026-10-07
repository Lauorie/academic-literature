#!/usr/bin/env python3
"""C7: do delivered reference lists stay inside the ledger, including sessions whose final check looked failed?

For every skill session (Skill-Full runs 1-3, Skill-Abs):
  1. in-session: find every `check` call in stream.jsonl, including calls through a shell variable ("$L" check),
     and read "hard failures: N" from the last one when the agent's own pipe left it visible;
  2. post hoc: re-run check's three hard-failure tests on the delivered files with each renderer version deployed
     during the runs, and count the warnings check reports with the evidence directory;
  3. audit the delivered References entry by entry against every record version the ledger ever held.
Renderer versions: ledger_das/ (md5 8fc3d113, deployed before the runs), the same plus the DOI view-suffix fix
(reconstructed: ledger_v1/ with its display clean-up disabled), ledger_v1/ (md5 142f8a1b, remote copy as of
2026-10-01 17:55). See PLAN.md.
Usage: c7_check.py <das_eval dir> <out.json>
"""

from __future__ import annotations

import contextlib
import difflib
import importlib.util
import io
import json
import logging
import re
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, Dict, List, Optional, Tuple

HERE = Path(__file__).parent
# Analysis code: tools/ in our working tree, evaluation/das_bench/ in the release.
for _d in ("tools", "das_bench"):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / _d))
from process_stats import tool_calls  # noqa: E402

logger = logging.getLogger(__name__)

RUNS = {"Skill-Full r1": "deepseek-v4.1-flash", "Skill-Full r2": "deepseek-v4.1-flash_full_r2",
        "Skill-Full r3": "deepseek-v4.1-flash_full_r3", "Skill-Abs": "deepseek-v4.1-flash_abs_r1"}
CHECK_RE = re.compile(r"(citation_ledger\.py|\$\{?\w+\}?\"?)\s+check\b")
HARD_RE = re.compile(r"hard failures:\s*(\d+)")
ENTRY_RE = re.compile(r"^\[(\d+)\]\s+(.*\S)\s*$")
TITLE_RE = re.compile(r"\*\"?([^*]+?)\"?\*")
TITLE_MATCH = 0.95
CLASSES = ("a_identical", "b_ledger_paper_edited", "c_outside_ledger")


def load_module(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod  # dataclasses look the module up while the class is built
    spec.loader.exec_module(mod)
    return mod


def renderers() -> Dict[str, ModuleType]:
    das = load_module(HERE / "ledger_das" / "citation_ledger.py", "ledger_8fc3")
    mid = load_module(HERE / "ledger_v1" / "citation_ledger.py", "ledger_mid")
    mid._display = lambda text: text  # 8fc3 plus the DOI view-suffix fix, without the display clean-up
    late = load_module(HERE / "ledger_v1" / "citation_ledger.py", "ledger_142f")
    return {"8fc3": das, "8fc3+doi_fix": mid, "142f": late}


def norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", re.sub(r"<[^>]+>", "", text).lower()).strip()


def references(cl: ModuleType, text: str) -> List[Tuple[int, str]]:
    """Numbered entries of the last References section; a line not starting with [n] continues the entry."""
    parts = cl.REFS_HEADING_RE.split(text)
    tail = parts[-1] if len(parts) > 1 else ""
    out: List[Tuple[int, str]] = []
    for ln in tail.splitlines():
        if m := ENTRY_RE.match(ln.strip()):
            out.append((int(m.group(1)), m.group(2)))
        elif out and ln.strip() and not ln.lstrip().startswith("<!--"):
            out[-1] = (out[-1][0], out[-1][1] + "\n" + ln)
    return out


def in_session(stream: Path) -> Dict[str, Any]:
    """The last check call as the agent saw it, and whether the delivered files changed after it."""
    calls = tool_calls(stream)
    idx = [i for i, c in enumerate(calls) if c["name"] == "Bash" and CHECK_RE.search(str(c["input"].get("command", "")))]
    if not idx:
        return {"check_calls": 0, "last_check_hard": None}
    last = idx[-1]
    hard = HARD_RE.findall(calls[last].get("result") or "")
    later = [c for c in calls[last + 1:] if (c["name"] in ("Write", "Edit") and "literature" in str(c["input"].get("file_path", "")))
             or (c["name"] == "Bash" and re.search(r"render\b|sed -i[^|]*literature", str(c["input"].get("command", ""))))]
    return {"check_calls": len(idx), "last_check_hard": int(hard[-1]) if hard else None,
            "edits_after_last_check": len(later)}


def recheck(cl: ModuleType, review: Path, draft: str, delivered: str) -> Tuple[List[str], int]:
    """check's hard-failure tests and its warning count, for one renderer version."""
    ledger = cl.Ledger.load(review / "citations.jsonl")
    expected, unknown = cl.render(draft, ledger, cl.style_of(delivered))
    hard = [t for t, bad in (("unknown_keys", unknown), ("delivered_differs_from_render", expected != delivered),
                             ("unrendered_keys", cl.KEY_RE.findall(delivered))) if bad]
    with contextlib.redirect_stdout(io.StringIO()):
        warns = cl._check_evidence(draft, ledger, review / "evidence") if (review / "evidence").exists() else []
    active = ledger.active()
    for key in cl.collect_keys(draft):
        if key in active:
            warns.extend(cl._record_warnings(active[key].record))
    return hard, len(warns)


def audit(run_dir: Path, mods: Dict[str, ModuleType]) -> Dict[str, Any]:
    review = run_dir / "review"
    row: Dict[str, Any] = {"session": f"{run_dir.parent.name}/{run_dir.name}", **in_session(run_dir / "stream.jsonl")}
    delivered = (review / "literature.md").read_text(encoding="utf-8")
    draft = (review / "literature.draft.md").read_text(encoding="utf-8")
    checks = {name: recheck(cl, review, draft, delivered) for name, cl in mods.items()}
    passing = [n for n, (hard, _) in checks.items() if not hard]
    row["recheck_pass_versions"] = passing
    row["recheck_hard"] = {n: hard for n, (hard, _) in checks.items()}
    row["recheck_warnings"] = checks[passing[0]][1] if passing else None

    versions = [json.loads(ln)["record"] for ln in (review / "citations.jsonl").read_text(encoding="utf-8").splitlines()
                if ln.strip() and json.loads(ln).get("event") in ("add", "revise") and json.loads(ln).get("record")]
    style = mods["8fc3"].style_of(delivered)
    rendered = {cl.render_reference(0, r, style)[len("[0] "):] for cl in mods.values() for r in versions}
    titles = [norm(r.get("title") or "") for r in versions]
    entries = references(mods["8fc3"], delivered)
    classes = []
    for _, e in entries:
        if e in rendered:
            classes.append("a_identical")
            continue
        m = TITLE_RE.search(e)
        cand = norm(m.group(1)) if m else norm(e)
        hit = any(t and difflib.SequenceMatcher(None, cand, t).ratio() >= TITLE_MATCH for t in titles)
        classes.append("b_ledger_paper_edited" if hit else "c_outside_ledger")
    row["n_entries"] = len(entries)
    row["classes"] = {c: classes.count(c) for c in CLASSES}
    row["non_identical_entries"] = [e for (_, e), c in zip(entries, classes) if c != "a_identical"][:5]
    body = mods["8fc3"].REFS_HEADING_RE.split(delivered)[0]
    cited = {int(n) for grp in re.findall(r"\[(\d+(?:\s*[,–-]\s*\d+)*)\]", body) for n in re.findall(r"\d+", grp)}
    row["body_numbers_without_entry"] = sorted(cited - {n for n, _ in entries})
    return row


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    root, out = Path(sys.argv[1]), Path(sys.argv[2])
    mods = renderers()
    flagged = set()
    for name in ("full_r1", "full_r2", "full_r3", "abs_r1"):
        stats = json.loads((root / "final" / f"process_stats_{name}.json").read_text())
        flagged |= {r["run"] for r in stats["runs"] if not r["check_pass"]}
    rows = []
    for cond, method in RUNS.items():
        for d in sorted((root / "pulled" / method).glob("[0-9][0-9][0-9]")):
            row = audit(d, mods)
            row["condition"], row["flagged_in_paper"] = cond, row["session"] in flagged
            rows.append(row)

    def summ(sel: List[Dict[str, Any]]) -> Dict[str, Any]:
        return {"sessions": len(sel), "entries": sum(r["n_entries"] for r in sel),
                **{c: sum(r["classes"][c] for r in sel) for c in CLASSES},
                "no_check_call": [r["session"] for r in sel if r["check_calls"] == 0],
                "last_check_visible_pass": sum(r["last_check_hard"] == 0 for r in sel),
                "last_check_visible_fail": [r["session"] for r in sel if (r["last_check_hard"] or 0) > 0],
                "last_check_not_visible": [r["session"] for r in sel if r["check_calls"] and r["last_check_hard"] is None],
                "edited_after_last_check": [r["session"] for r in sel if r.get("edits_after_last_check")],
                "recheck_pass": sum(bool(r["recheck_pass_versions"]) for r in sel),
                "recheck_fail": [r["session"] for r in sel if not r["recheck_pass_versions"]],
                "body_numbers_without_entry": {r["session"]: r["body_numbers_without_entry"] for r in sel
                                               if r["body_numbers_without_entry"]}}
    summary = {"flagged_in_paper": summ([r for r in rows if r["flagged_in_paper"]]), "all": summ(rows),
               "by_condition": {c: {"recheck_pass": sum(bool(r["recheck_pass_versions"]) for r in rows if r["condition"] == c),
                                    "warnings_mean": round(sum(r["recheck_warnings"] or 0 for r in rows if r["condition"] == c)
                                                           / max(1, sum(r["recheck_warnings"] is not None for r in rows if r["condition"] == c)), 2),
                                    "n": sum(r["condition"] == c for r in rows)} for c in RUNS}}
    out.write_text(json.dumps({"summary": summary, "sessions": rows}, indent=1, ensure_ascii=False) + "\n")
    logger.info(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
