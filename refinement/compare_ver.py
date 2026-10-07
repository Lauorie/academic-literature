#!/usr/bin/env python3
"""v2 vs v1 on held-out topics, as pre-registered in skillrefine/EVAL.md. Writes compare_v2.json and prints a summary."""
from __future__ import annotations

import json
import re
import statistics as st
import sys
from pathlib import Path

H = Path("/home/juli/citation/DAS/das_eval")
sys.path.insert(0, str(H / "tools"))
import analyze_paper as ap  # noqa: E402

HELD = json.loads((H / "skillrefine/heldout.json").read_text())
V1_DAS = ["skill_deepseek-v4.1-flash", "skill_deepseek-v4.1-flash_full_r2", "skill_deepseek-v4.1-flash_full_r3"]
VER = sys.argv[1] if len(sys.argv) > 1 else "v2"
V2_DAS = f"skill_deepseek-v4.1-flash_full_{VER}"
FAMS = ["BSC", "TSQ", "HDQ", "MAR"]


def fam_scores(bench: str, method: str, tid: str) -> dict | None:
    s = ap.load(H, bench, method, tid)
    if not s:
        return None
    out = {f: st.mean(s[c] for c in cs) for f, cs in ap.FAMILIES.items()}
    out["Total"] = ap.topic_total(s)
    return out


def das() -> dict:
    res = {}
    for bench in ("DAS-Bench", "DAS-Bench-xjudge"):
        rows = {}
        for t in HELD["das"]:
            v2 = fam_scores(bench, V2_DAS, t)
            v1s = [x for m in V1_DAS if (x := fam_scores(bench, m, t))]
            if v2 and v1s:
                rows[t] = {k: round(v2[k] - st.mean(x[k] for x in v1s), 3) for k in FAMS + ["Total"]}
        res[bench] = {"per_topic": rows, "mean": {k: round(st.mean(r[k] for r in rows.values()), 3) for k in FAMS + ["Total"]}
                      if rows else None, "n": len(rows)}
    return res


SL_T = {t["topic_id"]: t for t in json.loads((H / "surveylens/remote/topics_sl.json").read_text())}
SL_FN = {(r["discipline"], r["topic"]): r["topic_filename"] for r in json.loads((H / "surveylens/topics_map.json").read_text())}
SLR = H / "surveylens/results"
SL_CONF = {"primary": ("qwen_qwen3-30b-a3b-instruct-2507", ["p1", "p2"]), "cross": ("qwen_qwen3.5-397b-a17b", ["p1"]),
           "discipline": ("discipline/qwen_qwen3-30b-a3b-instruct-2507", ["p1"])}


def sl_score(sid: str, system: str, conf: str, asp: str) -> float | None:
    t = SL_T[sid]
    sub, passes = SL_CONF[conf]
    vals = []
    for p in passes:
        f = SLR / sub / p / system / t["discipline"] / (SL_FN[(t["discipline"], t["topic"])] + "_split.json")
        if not f.exists():
            return None
        d = json.loads(f.read_text())
        if d.get("failed"):
            return None
        vals.append(float(d["scores"][asp]["score"]))
    return st.mean(vals)


def sl() -> dict:
    res = {}
    for conf in SL_CONF:
        for asp in ("outline", "content", "reference"):
            d = []
            for sid in HELD["sl"]:
                a, b = sl_score(sid, f"Skill-{VER}", conf, asp), sl_score(sid, "Skill-Full", conf, asp)
                if a is not None and b is not None:
                    d.append(a - b)
            if len(d) >= 5:
                res[f"{conf}|{asp}"] = {"n": len(d), "mean": round(st.mean(d), 3),
                                        "ci95": [round(x, 3) for x in ap.bootstrap_ci(d)],
                                        "wins": sum(x > 0 for x in d), "ties": sum(x == 0 for x in d), "losses": sum(x < 0 for x in d)}
    return res


SB_T = {t["topic_id"]: t["topic"] for t in json.loads((H / "surveybench/remote/topics_sb.json").read_text())}


def sb() -> dict:
    out = {}
    for sid in HELD["sb"]:
        row = {}
        for m in (f"Skill-{VER}", "Skill-Full"):
            v = []
            for p in ("p1", "p2"):
                f = H / "surveybench/results/qwen_qwen3.5-397b-a17b" / p / m / f"{SB_T[sid]}.json"
                if f.exists() and not (d := json.loads(f.read_text())).get("failed"):
                    v.append((st.mean(d["content"].values()), st.mean(d["outline"].values())))
            if v:
                row[m] = {"content": round(st.mean(x[0] for x in v), 3), "outline": round(st.mean(x[1] for x in v), 3)}
        out[sid] = row
    return out


def structure(run_dir: Path) -> dict:
    md = run_dir / "review/literature.md"
    if not md.exists():
        return {}
    t = md.read_text(errors="replace")
    body = re.split(r"\n#+\s*References\b", t, flags=re.I)[0]
    cost = None
    s = run_dir / "stream.jsonl"
    if s.exists():
        for line in s.open(errors="replace"):
            if '"type":"result"' in line.replace(" ", ""):
                cost = json.loads(line).get("total_cost_usd")
    refs = re.findall(r"^\[\d+\].*$", re.split(r"\n#+\s*References\b", t, flags=re.I)[-1], re.M)
    fill_called = s.exists() and "citation_ledger.py fill" in s.read_text(errors="replace")
    return {"venue_na_share": round(sum("[venue unavailable]" in x for x in refs) / max(1, len(refs)), 3), "fill_called": fill_called,
            "words": len(body.split()), "h2": len(re.findall(r"^## ", t, re.M)), "h3": len(re.findall(r"^### ", t, re.M)),
            "tldr_heading": bool(re.search(r"^## TL;DR", t, re.M)), "outline_md": (run_dir / "review/outline.md").exists(),
            "manifest": (run_dir / "review/manifest.tsv").exists(), "cost_usd": cost}


def structures() -> dict:
    P = H / "pulled"
    pairs = [("das", t, P / f"deepseek-v4.1-flash_full_{VER}" / t, P / "deepseek-v4.1-flash" / t) for t in HELD["das"]] + \
            [("sl", t, P / f"deepseek-v4.1-flash_full_{VER}_sl" / t, P / "deepseek-v4.1-flash_full_sl" / t) for t in HELD["sl"]] + \
            [("sb", t, P / f"deepseek-v4.1-flash_full_{VER}_sb" / t, P / "deepseek-v4.1-flash_full_sb" / t) for t in HELD["sb"]]
    rows = [{"bench": b, "tid": t, "v2": structure(a), "v1": structure(c)} for b, t, a, c in pairs]
    summ = {}
    for ver in ("v2", "v1"):
        xs = [r[ver] for r in rows if r[ver]]
        summ[ver] = {"n": len(xs), "median_words": st.median(x["words"] for x in xs), "mean_h3": round(st.mean(x["h3"] for x in xs), 2),
                     "tldr_heading": sum(x["tldr_heading"] for x in xs), "outline_md": sum(x["outline_md"] for x in xs),
                     "manifest": sum(x["manifest"] for x in xs), "fill_called": sum(x["fill_called"] for x in xs),
                     "venue_na_share": round(st.mean(x["venue_na_share"] for x in xs), 3),
                     "mean_cost": round(st.mean(c for x in xs if (c := x["cost_usd"]) is not None), 3) if any(x["cost_usd"] for x in xs) else None}
    return {"rows": rows, "summary": summ}


def main() -> int:
    res = {"das": das(), "sl": sl(), "sb": sb(), "structure": structures()}
    (H / f"skillrefine/compare_{VER}.json").write_text(json.dumps(res, indent=1, default=str))
    for b, r in res["das"].items():
        print(b, "n", r["n"], "mean v2-v1", r["mean"])
    for k, r in res["sl"].items():
        print("SL", k, r)
    print("SB", json.dumps(res["sb"]))
    print("structure", json.dumps(res["structure"]["summary"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
