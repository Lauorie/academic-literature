#!/usr/bin/env python3
"""Build SkillRefiner inputs from the skill's evaluation runs (skillrefine/LABELS.md).

Writes traces.jsonl, binary_rewards.json, labels_detail.json into the output dir.
SkillRefiner serializes only each span's output_text, so every span carries its own description
(tool name, arguments, result) in output_text.
Usage: convert.py <out dir>
"""
from __future__ import annotations

import json
import re
import statistics as st
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

H = Path("/home/juli/citation/DAS/das_eval")
P = H / "pulled"
ARG_CAP, RESULT_CAP, TEXT_CAP, NOTE_CAP = 2000, 1500, 6000, 700
HELD = json.loads((H / "skillrefine" / "heldout.json").read_text())


def cap(s: str, n: int) -> str:
    s = s if isinstance(s, str) else json.dumps(s, ensure_ascii=False)
    return s if len(s) <= n else s[:n] + f" …[{len(s) - n} chars cut]"


def survey_stats(md_path: Path) -> Dict[str, int]:
    t = md_path.read_text(errors="replace")
    body = re.split(r"\n#+\s*References\b", t, flags=re.I)[0]
    return {"body_words": len(body.split()), "h2": len(re.findall(r"^## ", t, re.M)),
            "h3": len(re.findall(r"^### ", t, re.M)), "h4": len(re.findall(r"^#### ", t, re.M))}


def main_agent_spans(stream: Path) -> List[str]:
    """Main-agent assistant text and tool calls paired with their results, in order."""
    outs: List[str] = []
    pending: Dict[str, int] = {}
    for line in stream.open(errors="replace"):
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        if e.get("parent_tool_use_id") or e.get("type") not in ("assistant", "user"):
            continue
        content = (e.get("message") or {}).get("content")
        if isinstance(content, str):
            content = [{"type": "text", "text": content}]
        for c in content or []:
            ct = c.get("type")
            if e["type"] == "assistant" and ct == "text" and c.get("text", "").strip():
                outs.append("ASSISTANT: " + cap(c["text"].strip(), TEXT_CAP))
            elif e["type"] == "assistant" and ct == "tool_use":
                pending[c.get("id", "")] = len(outs)
                outs.append(f"TOOL CALL {c.get('name')}: {cap(c.get('input'), ARG_CAP)}")
            elif e["type"] == "user" and ct == "tool_result":
                res = c.get("content")
                if isinstance(res, list):
                    res = "\n".join(x.get("text", "") for x in res if isinstance(x, dict) and x.get("type") == "text")
                i = pending.pop(c.get("tool_use_id", ""), None)
                txt = "\n  → RESULT" + (" (error)" if c.get("is_error") else "") + ": " + cap(str(res or "(empty)"), RESULT_CAP)
                if i is None:
                    outs.append("TOOL RESULT (unmatched):" + txt)
                else:
                    outs[i] += txt
    return outs


# ---------- scores ----------

def das_total(method: str, tid: str, bench: str = "DAS-Bench") -> Optional[float]:
    sys.path.insert(0, str(H / "tools"))
    import analyze_paper as ap  # noqa: E402
    s = ap.load(H, bench, method, tid)
    return ap.topic_total(s) if s else None


def das_rationales(method: str, tid: str, k: int = 4) -> List[str]:
    base = H / "remote_results" / "DAS-Bench" / method
    items = []
    for fam in ("tsq_hdq", "bsc", "mar"):
        d = json.loads((base / fam / "api_off" / f"{tid}.json").read_text())
        sc = d.get("scores", {})
        groups = sc.values() if all(isinstance(v, dict) and "score" not in v for v in sc.values()) else [sc]
        for g in groups:
            for name, v in g.items():
                if isinstance(v, dict) and "score" in v:
                    items.append((float(v["score"]), name, v.get("rationale", "")))
    items.sort(key=lambda x: x[0])
    return [f"- {n} = {s:g}: {cap(r, NOTE_CAP)}" for s, n, r in items[:k]]


SLR = H / "surveylens" / "results"
SL_TOPICS = {t["topic_id"]: t for t in json.loads((H / "surveylens/remote/topics_sl.json").read_text())}
SL_FN = {(r["discipline"], r["topic"]): r["topic_filename"] for r in json.loads((H / "surveylens/topics_map.json").read_text())}


def sl_file(sid: str, sub: str, system: str) -> Path:
    t = SL_TOPICS[sid]
    return SLR / sub / system / t["discipline"] / (SL_FN[(t["discipline"], t["topic"])] + "_split.json")


def sl_score(sid: str, sub: str, system: str, asp: str) -> Optional[Dict[str, Any]]:
    f = sl_file(sid, sub, system)
    if not f.exists():
        return None
    d = json.loads(f.read_text())
    return None if d.get("failed") else d["scores"][asp]


SB_TOPICS = {t["topic_id"]: t["topic"] for t in json.loads((H / "surveybench/remote/topics_sb.json").read_text())}
SBR = H / "surveybench" / "results" / "qwen_qwen3.5-397b-a17b"


def sb_scores(sid: str, method: str) -> Optional[Dict[str, float]]:
    vals = []
    for p in ("p1", "p2"):
        f = SBR / p / method / f"{SB_TOPICS[sid]}.json"
        if not f.exists():
            return None
        d = json.loads(f.read_text())
        if d.get("failed"):
            return None
        c, o = st.mean(d["content"].values()), st.mean(d["outline"].values())
        vals.append({"content": c, "outline": o, "overall": (c + o) / 2, "outline_detail": d["outline"]})
    return {k: st.mean(v[k] for v in vals) for k in ("content", "outline", "overall")} | {"outline_detail": vals[0]["outline_detail"]}


# ---------- corpus ----------

DAS_RUNS = [("r1", "deepseek-v4.1-flash", "skill_deepseek-v4.1-flash", "full text"),
            ("r2", "deepseek-v4.1-flash_full_r2", "skill_deepseek-v4.1-flash_full_r2", "full text"),
            ("r3", "deepseek-v4.1-flash_full_r3", "skill_deepseek-v4.1-flash_full_r3", "full text"),
            ("abs", "deepseek-v4.1-flash_abs_r1", "skill_deepseek-v4.1-flash_abs_r1", "abstracts only")]
POOL_LONG = "naiverag-deepseek-v4.1-flash_poollong_r1"


def stats_line(name: str, s: Dict[str, int]) -> str:
    return f"{name}: body {s['body_words']} words, headings ## {s['h2']}, ### {s['h3']}, #### {s['h4']}"


def build() -> List[Dict[str, Any]]:
    items = []
    for run, d, method, mode in DAS_RUNS:
        for tid in [f"{i:03d}" for i in range(1, 31)]:
            if tid in HELD["das"]:
                continue
            s, b = das_total(method, tid), das_total(POOL_LONG, tid)
            fail = s < b
            fb = None
            if fail:
                fb = [f"DAS-Bench main judge: this run's Total {s:.3f} < length-matched single-call baseline {b:.3f}.",
                      "Lowest-scoring submetrics of this survey (score, judge rationale):", *das_rationales(method, tid),
                      stats_line("This survey", survey_stats(P / d / tid / "review/literature.md")),
                      stats_line("Baseline survey", survey_stats(P / POOL_LONG / tid / "review/literature.md"))]
            items.append({"trace_id": f"das_{run}_{tid}", "bench": "DAS-Bench", "topic_id": tid, "mode": mode,
                          "run_dir": P / d / tid, "fail": fail, "feedback": fb,
                          "detail": {"total": s, "baseline_total": b}})
    for sid in sorted(SL_TOPICS):
        if sid in HELD["sl"]:
            continue
        outl = [sl_score(sid, f"qwen_qwen3-30b-a3b-instruct-2507/{p}", "Skill-Full", "outline") for p in ("p1", "p2")]
        o = st.mean(float(x["score"]) for x in outl if x)
        cs = sl_score(sid, "discipline/qwen_qwen3-30b-a3b-instruct-2507/p1", "Skill-Full", "content")
        cp = sl_score(sid, "discipline/qwen_qwen3-30b-a3b-instruct-2507/p1", "NaiveRAG-Pool", "content")
        o_fail, c_fail = o <= 3, float(cs["score"]) < float(cp["score"])
        fb = None
        if o_fail or c_fail:
            fb = []
            if o_fail:
                fb += [f"SurveyLens outline score {o:g} (<= 3) from the benchmark's judge, which sees only the list of section headings.",
                       f"Judge notes: {cap(outl[0]['notes'], 1200)}"]
            if c_fail:
                fb += [f"SurveyLens discipline-rubric content {cs['score']} < single-call baseline {cp['score']} (same candidate papers).",
                       f"Judge notes: {cap(str(cs.get('notes', '')), 1200)}"]
            fb += [stats_line("This survey", survey_stats(P / "deepseek-v4.1-flash_full_sl" / sid / "review/literature.md")),
                   stats_line("Baseline survey", survey_stats(P / "naiverag-deepseek-v4.1-flash_pool_sl" / sid / "review/literature.md"))]
        items.append({"trace_id": f"sl_{sid}", "bench": "SurveyLens", "topic_id": sid, "mode": "full text",
                      "run_dir": P / "deepseek-v4.1-flash_full_sl" / sid, "fail": o_fail or c_fail, "feedback": fb,
                      "detail": {"outline": o, "content": cs["score"], "baseline_content": cp["score"]}})
    for sid in sorted(SB_TOPICS):
        if sid in HELD["sb"]:
            continue
        s, b = sb_scores(sid, "Skill-Full"), sb_scores(sid, "NaiveRAG-Pool")
        fail = s["overall"] < b["overall"]
        fb = None
        if fail:
            fb = [f"SurveyBench overall {s['overall']:.2f} < single-call baseline {b['overall']:.2f} "
                  f"(content {s['content']:.2f} vs {b['content']:.2f}; outline {s['outline']:.2f} vs {b['outline']:.2f}).",
                  f"Outline sub-scores of this survey (coverage/relevance/structure): {s['outline_detail']}",
                  stats_line("This survey", survey_stats(P / "deepseek-v4.1-flash_full_sb" / sid / "review/literature.md")),
                  stats_line("Baseline survey", survey_stats(P / "naiverag-deepseek-v4.1-flash_pool_sb" / sid / "review/literature.md"))]
        items.append({"trace_id": f"sb_{sid}", "bench": "SurveyBench", "topic_id": sid, "mode": "full text",
                      "run_dir": P / "deepseek-v4.1-flash_full_sb" / sid, "fail": fail, "feedback": fb,
                      "detail": {k: s[k] for k in ("overall", "content", "outline")} | {"baseline_overall": b["overall"]}})
    return items


RULES = {"DAS-Bench": "a run fails if its Total is below a length-matched single-call baseline that used the same candidate papers",
         "SurveyLens": "a run fails if its outline score is <= 3 or its content score is below a single-call baseline with the same papers",
         "SurveyBench": "a run fails if its overall score is below a single-call baseline with the same papers"}


def main() -> int:
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, "/home/juli/citation/SkillRefiner")
    from skill_refiner.propose import budget  # noqa: E402
    limit = budget.context_window("openai/gpt-5.4-mini") - budget.OUTPUT_RESERVE - 30000  # 30k: fixed prompt incl. the skill
    items = build()
    rewards, detail, sizes = {}, {}, []
    with (out / "traces.jsonl").open("w") as fo:
        for it in items:
            head = (f"RUN CONTEXT (metadata): benchmark {it['bench']}, topic id {it['topic_id']}, reading mode: {it['mode']}. "
                    f"The agent ran the academic-literature skill headlessly to write one survey. Outcome label rule: {RULES[it['bench']]}.")
            texts = [head] + main_agent_spans(it["run_dir"] / "stream.jsonl")
            if it["feedback"]:
                texts.append("EVALUATOR FEEDBACK (metadata from the benchmark's scorer, not agent output):\n" + "\n".join(it["feedback"]))
            ntok = budget.count_tokens("\n---\n".join(texts), "openai/gpt-5.4-mini")
            assert ntok < limit, f"{it['trace_id']}: {ntok} tokens >= {limit}"
            sizes.append(ntok)
            spans = [{"span_id": f"s{i}", "name": "step", "input_text": "", "output_text": t,
                      "start_time": "", "end_time": ""} for i, t in enumerate(texts)]
            fo.write(json.dumps({"trace_id": it["trace_id"], "spans": spans}, ensure_ascii=False) + "\n")
            rewards[it["trace_id"]] = not it["fail"]
            detail[it["trace_id"]] = {"bench": it["bench"], "fail": it["fail"], **it["detail"]}
    (out / "binary_rewards.json").write_text(json.dumps(rewards, indent=1))
    (out / "labels_detail.json").write_text(json.dumps(detail, indent=1, default=float))
    by = {}
    for v in detail.values():
        by.setdefault(v["bench"], [0, 0])[v["fail"]] += 1
    print("traces", len(items), "pass/fail by bench", by, "tokens median", st.median(sizes), "max", max(sizes),
          "sum", sum(sizes), "limit", limit)
    return 0


if __name__ == "__main__":
    sys.exit(main())
