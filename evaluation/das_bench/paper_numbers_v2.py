#!/usr/bin/env python3
"""Macros and tables for the paper's version-2 sections, from the pre-registered analysis outputs.

Writes <paper>/generated/numbers_v2.tex and tab_lm.tex, tab_sl.tex, tab_ci.tex, tab_refine.tex, tab_submode.tex.
Sources (all under das_eval/): length_matched/analysis_lm.json, surveylens/analysis_sl.json, surveybench/results,
citation_integrity/{analysis_ci_v3.json, audit_key.json, audit_result_*.json}, skillrefine/{compare_v2.json,
compare_v3.json, paper_analysis_a.json, paper_analysis_b.json, run_stats_v3.json, corpus/labels_detail.json,
out/combined/manifest.json, out/negative/*.json}, surveylens/run_stats_sl.json,
skillrefine/v4/academic-literature-workspace/iteration-{1,2}/*/*/run-1/grading.json.
Usage: paper_numbers_v2.py <paper dir>
"""
from __future__ import annotations

import glob
import json
import re
import statistics as st
import sys
from pathlib import Path

H = Path(__file__).resolve().parent.parent
PAPER = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(H / "tools"))
import analyze_paper as ap  # noqa: E402

M: list[str] = []


def mac(name: str, value) -> None:
    assert re.fullmatch(r"[A-Za-z]+", name), name
    M.append(f"\\newcommand{{\\{name}}}{{{value}}}")


def _r(x: float, nd: int) -> str:
    """Round half up (as in the protocol notes), not half to even."""
    from decimal import ROUND_HALF_UP, Decimal
    return str(Decimal(repr(x)).quantize(Decimal(1).scaleb(-nd), rounding=ROUND_HALF_UP))


def sg(x: float, nd: int = 2) -> str:
    """Signed number, with a true minus sign."""
    v = _r(x, nd)
    s = v if v.startswith("-") else "+" + v
    return s.replace("-", "$-$") if s.startswith("-") else s


def f2(x: float, nd: int = 2) -> str:
    s = _r(x, nd)
    return s.replace("-", "$-$") if s.startswith("-") else s


def pc(x: float, nd: int = 1) -> str:
    return _r(100 * x, nd)


def pp(x: float, nd: int = 1) -> str:
    return sg(100 * x, nd)


def load(p: str):
    return json.loads((H / p).read_text())


# ---------------------------------------------------------------- length-matched baseline (DAS-Bench)
lm = load("length_matched/analysis_lm.json")
for b, tag in (("DAS-Bench", "M"), ("DAS-Bench-xjudge", "X")):
    c, p = lm["condition"][b], lm["paired"][b]
    q = p["Skill-Full_vs_NaiveRAG-Pool-Long"]
    mac(f"lmTotal{tag}", f2(c["NaiveRAG-Pool-Long"]["Total"]))
    mac(f"lmDiff{tag}", sg(q["mean_diff_total"]))
    mac(f"lmLo{tag}", f2(q["ci95"][0]))
    mac(f"lmHi{tag}", f2(q["ci95"][1]))
    mac(f"lmWins{tag}", q["wins"])
    mac(f"lmN{tag}", q["n"])
    for fam in ("BSC", "TSQ", "HDQ", "MAR"):
        mac(f"lm{fam.capitalize()}{tag}", sg(q["family_diffs"][fam]))
    s, pl, pll = (c[k]["Total"] for k in ("Skill-Full", "NaiveRAG-Pool", "NaiveRAG-Pool-Long"))
    mac(f"lmClose{tag}", f"{100 * (pll - pl) / (s - pl):.0f}")


def words(md: Path) -> int:
    return len(re.split(r"\n#+\s*References\b", md.read_text(errors="replace"), flags=re.I)[0].split())


P = H / "pulled"
wl = {"Skill": [words(P / "deepseek-v4.1-flash" / f"{i:03d}/review/literature.md") for i in range(1, 31)],
      "Pool": [words(P / "naiverag-deepseek-v4.1-flash_pool_r1" / f"{i:03d}/review/literature.md") for i in range(1, 31)],
      "PoolLong": [words(P / "naiverag-deepseek-v4.1-flash_poollong_r1" / f"{i:03d}/review/literature.md") for i in range(1, 31)]}
for k, v in wl.items():
    mac(f"lmWords{k}", f"{st.median(v):,.0f}".replace(",", "{,}"))
targets = [int((P / "naiverag-deepseek-v4.1-flash_poollong_r1" / f"{i:03d}/target_words").read_text()) for i in range(1, 31)]
ratios = [w / t for w, t in zip(wl["PoolLong"], targets)]
mac("lmRatioMed", f2(st.median(ratios)))
mac("lmRatioMin", f2(min(ratios)))
mac("lmRatioMax", f2(max(ratios)))


def mar_sub(method: str, crit: str) -> float:
    vals = [ap.load(H, "DAS-Bench", method, f"{i:03d}")[crit] for i in range(1, 31)]
    return st.mean(vals)


FT = "Figure/Table Quality and Textual Integration"
mac("lmFigTabSkill", f2(mar_sub("skill_deepseek-v4.1-flash", FT)))
mac("lmFigTabPoolLong", f2(mar_sub("naiverag-deepseek-v4.1-flash_poollong_r1", FT)))
mac("lmRefPresSkill", f2(mar_sub("skill_deepseek-v4.1-flash", "Citation and Reference Presentation Integrity")))
mac("lmRefPresPoolLong", f2(mar_sub("naiverag-deepseek-v4.1-flash_poollong_r1", "Citation and Reference Presentation Integrity")))


def pearson(x, y):
    mx, my = st.mean(x), st.mean(y)
    den = (sum((a - mx) ** 2 for a in x) * sum((b - my) ** 2 for b in y)) ** 0.5
    return sum((a - mx) * (b - my) for a, b in zip(x, y)) / den


rs = []
for meth, key in (("naiverag-deepseek-v4.1-flash_own_r1", "naiverag-deepseek-v4.1-flash_own_r1"),
                  ("naiverag-deepseek-v4.1-flash_pool_r1", "naiverag-deepseek-v4.1-flash_pool_r1")):
    w = [words(P / key / f"{i:03d}/review/literature.md") for i in range(1, 31)]
    for fam in ("TSQ", "HDQ"):
        sc = [st.mean(ap.load(H, "DAS-Bench-xjudge", meth, f"{i:03d}")[c] for c in ap.FAMILIES[fam]) for i in range(1, 31)]
        rs.append(pearson(w, sc))
mac("lenRMin", f2(min(rs)))
mac("lenRMax", f2(max(rs)))
# the same correlations under the main judge, per baseline
for meth, tag in (("naiverag-deepseek-v4.1-flash_own_r1", "Own"), ("naiverag-deepseek-v4.1-flash_pool_r1", "Pool")):
    w = [words(P / meth / f"{i:03d}/review/literature.md") for i in range(1, 31)]
    rr = [pearson(w, [st.mean(ap.load(H, "DAS-Bench", meth, f"{i:03d}")[c] for c in ap.FAMILIES[fam]) for i in range(1, 31)])
          for fam in ("TSQ", "HDQ")]
    mac(f"lenRMain{tag}Min", f2(min(rr)))
    mac(f"lenRMain{tag}Max", f2(max(rr)))

lt = r"""\begin{table}[t]
  \centering
  \caption{\textbf{Length-matched baseline on DAS-Bench} (30 topics). \textsc{NaiveRAG-Pool-Long} receives the same
  candidate papers as \textsc{NaiveRAG-Pool} and is asked to write as many words as \textsc{Skill-Full} wrote on that
  topic. Differences are \textsc{Skill-Full} (mean of three runs) minus the baseline, with paired 95\% bootstrap CIs.}
  \label{tab:lm}
  \small
  \begin{tabular}{@{}lcc@{}}
    \toprule
    & main judge & cross judge \\
    \midrule
    \textsc{NaiveRAG-Pool-Long} total & \lmTotalM{} & \lmTotalX{} \\
    \textsc{Skill-Full} $-$ \textsc{Pool-Long} & \lmDiffM{} [\lmLoM, \lmHiM] & \lmDiffX{} [\lmLoX, \lmHiX] \\
    \quad topics won & \lmWinsM{}/\lmNM{} & \lmWinsX{}/\lmNX{} \\
    \quad \BSC{} / \TSQ{} / \HDQ{} / \MAR{} & \lmBscM{} / \lmTsqM{} / \lmHdqM{} / \lmMarM{} & \lmBscX{} / \lmTsqX{} / \lmHdqX{} / \lmMarX{} \\
    Share of the \textsc{Pool} gap closed by length & \lmCloseM\% & \lmCloseX\% \\
    \bottomrule
  \end{tabular}
\end{table}
"""

# ---------------------------------------------------------------- SurveyLens, v1, 100 topics
sl = load("surveylens/analysis_sl.json")
SLK = {"Bj": "generic|qwen_qwen3-30b-a3b-instruct-2507", "Cj": "generic|qwen_qwen3.5-397b-a17b",
       "Dr": "discipline|qwen_qwen3-30b-a3b-instruct-2507"}
ASP = {"Outline": "outline", "Content": "content", "Reference": "reference"}
for jt, key in SLK.items():
    blk = sl[key]
    for sysname, st_ in (("Skill", "Skill-Full"), ("Own", "NaiveRAG-Own"), ("Pool", "NaiveRAG-Pool")):
        for an, a in ASP.items():
            mac(f"sl{jt}{an}{sysname}", f2(blk["systems"][st_][a]))
    for base, bt in (("NaiveRAG-Own", "Own"), ("NaiveRAG-Pool", "Pool")):
        q = blk["paired"][f"Skill-Full - {base}"]
        for an, a in ASP.items():
            r = q[a]
            mac(f"sl{jt}{an}D{bt}", sg(r["mean"]))
            mac(f"sl{jt}{an}D{bt}Abs", f2(abs(r["mean"])))
            mac(f"sl{jt}{an}D{bt}Lo", f2(r["ci95"][0]))
            mac(f"sl{jt}{an}D{bt}Hi", f2(r["ci95"][1]))
            mac(f"sl{jt}{an}D{bt}W", r["wins"])
            mac(f"sl{jt}{an}D{bt}L", r["losses"])
bj = sl[SLK["Bj"]]["systems"]
for sysname, st_ in (("SurveyForge", "SurveyForge"), ("SurveyX", "SurveyX"), ("Autosurvey", "Autosurvey"),
                     ("Human", "Human"), ("Gemini", "Gemini")):
    for an, a in ASP.items():
        mac(f"slBj{an}{sysname}", f2(bj[st_][a]))
# The SurveyLens authors' manual leakage audit: generated surveys that cite the withheld human survey.
import csv  # noqa: E402

leak = {"Gemini": 0, "Qwen": 0}
for r in csv.DictReader(open("/home/juli/citation/SurveyLens/Data_Statistics_and_Analysis/flagged_cases_minimal.csv")):
    s_ = "Gemini" if r["system"].lower().startswith("gemini") else r["system"]
    if s_ in leak and r["manual_same_paper"].strip() == "1":
        leak[s_] += 1
mac("slLeakGemini", leak["Gemini"])
mac("slLeakQwen", leak["Qwen"])
# Cross-judge reference notes that name the placeholder (skill) or a missing venue (any system)
MISSING = re.compile(r"missing (venue|journal|publication)|lack(s|ing)? (venue|journal)|no (venue|journal)|"
                     r"venue (information )?(is )?missing|without (a )?(venue|journal)|venue unavailable")
for sysname, tag in (("Skill-Full", "Skill"), ("NaiveRAG-Pool", "Pool"), ("NaiveRAG-Own", "Own")):
    hits = 0
    for f in glob.glob(str(H / "surveylens/results/qwen_qwen3.5-397b-a17b/p1" / sysname / "*/*_split.json")):
        d = json.loads(Path(f).read_text())
        if not d.get("failed") and MISSING.search(d["scores"]["reference"]["notes"].lower()):
            hits += 1
    mac(f"slNoteVenue{tag}", hits)
aud = load("surveylens/audit_final.json")
mac("slAuditRuns", len(aud))
mac("slAuditCited", sum(r["in_ledger"] + r["in_reference_list"] for r in aud))
mac("slAuditFiltered", sum(r["search_filtered"] for r in aud))
mac("slAuditBlocked", sum(r["blocked_calls"] for r in aud))
# share of cited records without a venue: skill (ledger records it cites) vs NaiveRAG-Pool (records it cites), SurveyLens v1
sys.path.insert(0, str(H / "skillrefine/v4/academic-literature/scripts"))
import citation_ledger as cl  # noqa: E402

shs = []
for d in sorted(glob.glob(str(P / "deepseek-v4.1-flash_full_sl/sl*/review"))):
    led = cl.Ledger.load(Path(d) / "citations.jsonl").active()
    recs = [led[k].record for k in cl.collect_keys((Path(d) / "literature.draft.md").read_text()) if k in led]
    if recs:
        shs.append(sum(cl._needs_venue(r) for r in recs) / len(recs))
mac("slVenueMissSkill", pc(st.mean(shs), 0))
shp = []
for f in sorted(glob.glob(str(P / "naiverag-deepseek-v4.1-flash_pool_sl/sl*/review/records.json"))):
    recs = json.loads(Path(f).read_text())
    if recs:
        shp.append(sum(cl._needs_venue(r) for r in recs) / len(recs))
mac("slVenueMissPool", pc(st.mean(shp), 0))
runs_sl = load("surveylens/run_stats_sl.json")
mac("slCost", f2(st.mean(r["cost_usd"] for r in runs_sl)))
mac("slWall", f"{st.mean(r['wall_min'] for r in runs_sl):.0f}")

slt = r"""\begin{table}[t]
  \centering
  \caption{\textbf{SurveyLens, 100 topics in ten disciplines.} Each component is scored 1--5. Paired differences are
  \textsc{Skill-Full} minus the baseline with 95\% bootstrap CIs. Benchmark judge: Qwen3-30B-A3B, the benchmark's
  configured model (two passes); cross judge: Qwen3.5-397B-A17B; discipline rubric: the benchmark's
  discipline-specific criteria, benchmark judge.}
  \label{tab:sl}
  \small
  \setlength{\tabcolsep}{4pt}
  \resizebox{\linewidth}{!}{\begin{tabular}{@{}llccc@{}}
    \toprule
    Judge & Comparison & Outline & Content & Reference \\
    \midrule
    \multirow{3}{*}{benchmark} & \textsc{Skill-Full} & \slBjOutlineSkill & \slBjContentSkill & \slBjReferenceSkill \\
     & $-$ \textsc{Own} & \slBjOutlineDOwn{} [\slBjOutlineDOwnLo, \slBjOutlineDOwnHi] & \slBjContentDOwn{} & \slBjReferenceDOwn{} [\slBjReferenceDOwnLo, \slBjReferenceDOwnHi] \\
     & $-$ \textsc{Pool} & \slBjOutlineDPool{} [\slBjOutlineDPoolLo, \slBjOutlineDPoolHi] & \slBjContentDPool{} & \slBjReferenceDPool{} [\slBjReferenceDPoolLo, \slBjReferenceDPoolHi] \\
    \midrule
    \multirow{3}{*}{cross} & \textsc{Skill-Full} & \slCjOutlineSkill & \slCjContentSkill & \slCjReferenceSkill \\
     & $-$ \textsc{Own} & \slCjOutlineDOwn{} [\slCjOutlineDOwnLo, \slCjOutlineDOwnHi] & \slCjContentDOwn{} [\slCjContentDOwnLo, \slCjContentDOwnHi] & \slCjReferenceDOwn{} [\slCjReferenceDOwnLo, \slCjReferenceDOwnHi] \\
     & $-$ \textsc{Pool} & \slCjOutlineDPool{} [\slCjOutlineDPoolLo, \slCjOutlineDPoolHi] & \slCjContentDPool{} [\slCjContentDPoolLo, \slCjContentDPoolHi] & \slCjReferenceDPool{} [\slCjReferenceDPoolLo, \slCjReferenceDPoolHi] \\
    \midrule
    \multirow{3}{*}{discipline} & \textsc{Skill-Full} & \slDrOutlineSkill & \slDrContentSkill & \slDrReferenceSkill \\
     & $-$ \textsc{Own} & \slDrOutlineDOwn{} [\slDrOutlineDOwnLo, \slDrOutlineDOwnHi] & \slDrContentDOwn{} [\slDrContentDOwnLo, \slDrContentDOwnHi] & \slDrReferenceDOwn{} [\slDrReferenceDOwnLo, \slDrReferenceDOwnHi] \\
     & $-$ \textsc{Pool} & \slDrOutlineDPool{} [\slDrOutlineDPoolLo, \slDrOutlineDPoolHi] & \slDrContentDPool{} [\slDrContentDPoolLo, \slDrContentDPoolHi] & \slDrReferenceDPool{} [\slDrReferenceDPoolLo, \slDrReferenceDPoolHi] \\
    \bottomrule
  \end{tabular}}
\end{table}
"""

# ---------------------------------------------------------------- SurveyBench, v1, 20 topics (appendix)
sbt = {t["topic_id"]: t["topic"] for t in load("surveybench/remote/topics_sb.json")}
SBJ = {"Q": ("qwen_qwen3.5-397b-a17b", ("p1", "p2")), "G": ("openai_gpt-4o-mini", ("p1", "p2", "p3"))}


def sb(judge: str, method: str, tid: str):
    root, passes = SBJ[judge]
    v = []
    for p in passes:
        f = H / "surveybench/results" / root / p / method / f"{sbt[tid]}.json"
        if f.exists() and not (d := json.loads(f.read_text())).get("failed"):
            v.append((st.mean(d["content"].values()), st.mean(d["outline"].values())))
    return (st.mean(x[0] for x in v), st.mean(x[1] for x in v)) if v else None


for j in SBJ:
    for base, bt in (("NaiveRAG-Own", "Own"), ("NaiveRAG-Pool", "Pool")):
        for i, an in ((0, "Content"), (1, "Outline")):
            d = [a[i] - b[i] for t in sbt if (a := sb(j, "Skill-Full", t)) and (b := sb(j, base, t))]
            ci_ = ap.bootstrap_ci(d)
            mac(f"sb{j}{an}D{bt}", sg(st.mean(d)))
            mac(f"sb{j}{an}D{bt}Lo", f2(ci_[0]))
            mac(f"sb{j}{an}D{bt}Hi", f2(ci_[1]))
            mac(f"sb{j}{an}D{bt}N", len(d))

# ---------------------------------------------------------------- citation integrity (v1 Skill-Full run 1, DAS-Bench)
ci = load("citation_integrity/analysis_ci_v3.json")
for c, tag in (("skill_full", "Skill"), ("norag", "NoRag"), ("poolfree", "PoolFree")):
    cond = ci["condition"][c]
    mac(f"ci{tag}Def", pc(cond["mean_defective"]))
    mac(f"ci{tag}Ver", pc(cond["pooled_share"]["verified"]))
    mac(f"ci{tag}Meta", pc(cond["pooled_share"]["metadata_error"]))
    mac(f"ci{tag}NF", pc(cond["pooled_share"]["not_found"]))
    mac(f"ci{tag}Entries", cond["entries_total"])
    mac(f"ci{tag}Checked", cond["checked"])
for base, tag in (("norag", "NoRag"), ("poolfree", "PoolFree")):
    q = ci["paired"][f"skill_full - {base} | defective"]
    mac(f"ciD{tag}", pp(q["mean"]))
    mac(f"ciD{tag}Lo", pp(q["ci95"][0]))
    mac(f"ciD{tag}Hi", pp(q["ci95"][1]))
    mac(f"ciD{tag}W", q["wins(lower for skill)"])
    mac(f"ciD{tag}L", q["losses"])
for v, vt in (("v1", "One"), ("v2", "Two"), ("v3", "Three")):
    for base, tag in (("norag", "NoRag"), ("poolfree", "PoolFree")):
        q = load(f"citation_integrity/analysis_ci_{v}.json")["paired"][f"skill_full - {base} | defective"]
        mac(f"ciVer{vt}{tag}", pp(q["mean"]))
        mac(f"ciVer{vt}{tag}Lo", pp(q["ci95"][0]))
        mac(f"ciVer{vt}{tag}Hi", pp(q["ci95"][1]))
key = {x["aid"]: x for x in load("citation_integrity/audit_key.json")}
res = {r["aid"]: r for n in (1, 2, 3) for r in load(f"citation_integrity/audit_result_{n}.json")}
nf = [a for a, x in key.items() if x["class"] == "not_found" and x["set"] == "preregistered"]
mac("auditNF", len(nf))
mac("auditNFExist", sum(res[a]["exists"] == "yes" for a in nf))
mac("auditTotal", len(key))
mac("auditInvented", 0)
mac("auditNFNoRag", sum(key[a]["cond"] == "norag" for a in nf))
mac("auditVer", sum(x["class"] == "verified" for x in key.values()))
mac("auditMeta", sum(x["class"] == "metadata_error" for x in key.values()))
nr_cond = ci["condition"]["norag"]
mac("ciNoRagNFCount", round(nr_cond["pooled_share"]["not_found"] * nr_cond["checked"]))  # no audited entry was judged invented by the model; see PROTOCOL.md "Hand audit"

cit = r"""\begin{table}[t]
  \centering
  \caption{\textbf{Reference integrity on DAS-Bench} (30 topics, up to 40 entries checked per survey against CrossRef
  and arXiv). \textsc{NoRAG} writes from memory; \textsc{Pool-Free} receives the skill's candidate papers but writes its
  own reference list. Rows 2--4 are shares of all checked entries; the defective row is the mean of the per-survey
  rates (metadata error + not found), the pre-registered primary metric, so it need not equal the sum of rows 3 and 4.}
  \label{tab:ci}
  \small
  \begin{tabular}{@{}lccc@{}}
    \toprule
    & \textsc{Skill-Full} & \textsc{NoRAG} & \textsc{Pool-Free} \\
    \midrule
    entries checked & \ciSkillChecked & \ciNoRagChecked & \ciPoolFreeChecked \\
    verified (\%) & \ciSkillVer & \ciNoRagVer & \ciPoolFreeVer \\
    metadata error (\%) & \ciSkillMeta & \ciNoRagMeta & \ciPoolFreeMeta \\
    not found (\%) & \ciSkillNF & \ciNoRagNF & \ciPoolFreeNF \\
    defective, mean per survey (\%) & \ciSkillDef & \ciNoRagDef & \ciPoolFreeDef \\
    \textsc{Skill-Full} $-$ baseline (pp) & --- & \ciDNoRag{} [\ciDNoRagLo, \ciDNoRagHi] & \ciDPoolFree{} [\ciDPoolFreeLo, \ciDPoolFreeHi] \\
    \bottomrule
  \end{tabular}
\end{table}
"""

# ---------------------------------------------------------------- refinement (SkillRefiner, v2, v3, held-out)
lab = load("skillrefine/corpus/labels_detail.json")
mac("srTraces", len(lab))
mac("srFail", sum(v["fail"] for v in lab.values()))
mac("srPass", sum(not v["fail"] for v in lab.values()))
man = load("skillrefine/out/combined/manifest.json")
mac("srPosClusters", man["n_positive_clusters"])
mac("srNegClusters", man["n_negative_clusters"])
kept = len(load("skillrefine/out/negative/cluster_proposals.json"))
rejected = len(load("skillrefine/out/negative/rejected_cluster_proposals.json"))
mac("srNegKept", kept)
mac("srNegRejected", rejected)
mac("srNegProps", kept + rejected)
mac("srSeedBytes", f"{len((H / 'skillrefine/seed_SKILL.md').read_bytes()):,}".replace(",", "{,}"))
mac("srMergedBytes", f"{len((H / 'skillrefine/out/combined/proposed_skill.md').read_bytes()):,}".replace(",", "{,}"))
held = load("skillrefine/heldout.json")
mac("hoDas", len(held["das"]))
mac("hoSl", len(held["sl"]))
mac("hoSb", len(held["sb"]))
for ver in ("v2", "v3"):
    cv = load(f"skillrefine/compare_{ver}.json")
    V = {"v2": "VTwo", "v3": "VThree"}[ver]  # LaTeX macro names take letters only
    for k, r in cv["sl"].items():
        conf, asp = k.split("|")
        t = {"primary": "Bj", "cross": "Cj", "discipline": "Dr"}[conf] + asp.capitalize()
        mac(f"ho{V}{t}", sg(r["mean"]))
        mac(f"ho{V}{t}Lo", f2(r["ci95"][0]))
        mac(f"ho{V}{t}Hi", f2(r["ci95"][1]))
        mac(f"ho{V}{t}W", r["wins"])
        mac(f"ho{V}{t}L", r["losses"])
    for b, tag in (("DAS-Bench", "M"), ("DAS-Bench-xjudge", "X")):
        mac(f"ho{V}DasTotal{tag}", sg(cv["das"][b]["mean"]["Total"]))
    s2 = dict(cv["structure"]["summary"])
    s2[ver] = s2["v2"]  # compare_ver.py stores the new version under "v2" whatever its tag; "v1" is the baseline
    mac(f"ho{V}Hthree", f"{s2[ver]['mean_h3']:.1f}")
    mac(f"ho{V}Tldr", s2[ver]["tldr_heading"])
    mac(f"ho{V}OutlineMd", s2[ver]["outline_md"])
    if "venue_na_share" in s2[ver]:
        mac(f"ho{V}VenueNA", pc(s2[ver]["venue_na_share"], 0))
    if ver == "v3":
        mac("hoVOneHthree", f"{s2['v1']['mean_h3']:.1f}")
        mac("hoVOneTldr", s2["v1"]["tldr_heading"])
        mac("hoVOneVenueNA", pc(s2["v1"]["venue_na_share"], 0))
        mac("hoN", s2["v3"]["n"])
        mac("hoVThreeFill", s2["v3"]["fill_called"])
# v3 - v2 on SurveyLens (secondary)
sys.argv = [sys.argv[0], "v3"]
sys.path.insert(0, str(H / "skillrefine"))
import compare_ver as cvmod  # noqa: E402

for conf, jt in (("cross", "Cj"), ("discipline", "Dr")):
    d = [cvmod.sl_score(s, "Skill-v3", conf, "reference") - cvmod.sl_score(s, "Skill-v2", conf, "reference")
         for s in held["sl"]]
    c95 = ap.bootstrap_ci(d)
    mac(f"hoVTwoThree{jt}Ref", sg(st.mean(d)))
    mac(f"hoVTwoThree{jt}RefLo", f2(c95[0]))
    mac(f"hoVTwoThree{jt}RefHi", f2(c95[1]))
pa = load("skillrefine/paper_analysis_a.json")
for k, r in pa["sl"].items():
    conf, asp, comp = k.split("|")
    ver, base = comp.split("-", 1)
    t = {"primary": "Bj", "cross": "Cj", "discipline": "Dr"}[conf] + asp.capitalize() + {"v1": "VOne", "v3": "VThree"}[ver] + \
        {"NaiveRAG-Own": "Own", "NaiveRAG-Pool": "Pool"}[base]
    mac(f"ha{t}", sg(r["mean"]))
    mac(f"ha{t}Lo", f2(r["ci95"][0]))
    mac(f"ha{t}Hi", f2(r["ci95"][1]))
for k, r in pa["das"].items():
    bench, comp = k.split("|")
    ver, base = comp.split("-", 1)
    t = ("M" if bench == "DAS-Bench" else "X") + {"v1": "VOne", "v3": "VThree"}[ver] + base.replace("-", "")
    mac(f"haDas{t}", sg(r["mean"]))
    mac(f"haDas{t}W", r["wins"])
pb = load("skillrefine/paper_analysis_b.json")
mac("hbN", pb["n"])
for k, tag in (("defective", "Def"), ("metadata_error", "Meta"), ("not_found", "NF"), ("bad_id", "BadId")):
    r = pb[k]
    mac(f"hb{tag}VThree", pc(r["v3_mean"]))
    mac(f"hb{tag}VOne", pc(r["v1_mean"]))
    mac(f"hb{tag}D", pp(r["diff"], 2))
    mac(f"hb{tag}Lo", pp(r["ci95"][0], 2))
    mac(f"hb{tag}Hi", pp(r["ci95"][1], 2))
import run_stats  # noqa: E402

v1runs = [P / "deepseek-v4.1-flash" / t for t in held["das"]] + \
         [P / "deepseek-v4.1-flash_full_sl" / t for t in held["sl"]] + \
         [P / "deepseek-v4.1-flash_full_sb" / t for t in held["sb"]]
v1s = [run_stats.run_summary(r) for r in v1runs]
mac("vOneHoCost", f2(st.mean(r["cost_usd"] for r in v1s)))
mac("vOneHoWall", f"{st.mean(r['wall_min'] for r in v1s):.0f}")


def venue_na(md: Path) -> float:
    refs = re.findall(r"^\[\d+\].*$", re.split(r"\n#+\s*References\b", md.read_text(errors="replace"), flags=re.I)[-1], re.M)
    return sum("[venue unavailable]" in x for x in refs) / max(1, len(refs))


for tag, d in (("VOne", "deepseek-v4.1-flash_full_sl"), ("VTwo", "deepseek-v4.1-flash_full_v2_sl"),
               ("VThree", "deepseek-v4.1-flash_full_v3_sl")):
    mac(f"ho{tag}VenueNASl", pc(st.mean(venue_na(P / d / s_ / "review/literature.md") for s_ in held["sl"]), 0))
for b, tag in (("DAS-Bench", "M"), ("DAS-Bench-xjudge", "X")):
    for base in ("PoolLong",):
        r_ = pa["das"][f"{b}|v3-Pool-Long"]
        mac(f"haDas{tag}VThreePoolLongN", r_["n"])
# SurveyBench held-out, outline v3 vs NaiveRAG-Pool (pre-registered, n=4): per topic
mac("haSbOutline", ", ".join(f"{pa['sb'][t]['Skill-v3']['outline']:.2f} vs {pa['sb'][t]['NaiveRAG-Pool']['outline']:.2f}"
                              for t in held["sb"]))
mac("haSbBelow", sum(pa["sb"][t]["Skill-v3"]["outline"] < pa["sb"][t]["NaiveRAG-Pool"]["outline"] for t in held["sb"]))
# fill dry run on copies of the 20 v2 SurveyLens ledgers (recorded in skillrefine/EVAL.md, v3 pre-registration)
mac("fillDryBefore", 64)
mac("fillDryAfter", 12)
mac("fillDryTitleMatches", 209)
mac("fillDryDoubtful", 1)
mac("fillDryConsistent", 162)   # DOI prefix matches the publisher of the record's URL
mac("fillDryInconsistent", 6)   # of which 5 are known legacy prefixes (OUP journals, Palgrave) and 1 doubtful
mac("fillDryUnmapped", 41)      # URL host not in the prefix table, unchecked
# Pool-Long judgments that needed a second attempt (watchdog event log)
ev = (H / "watchdog_events.log").read_text(errors="replace")
mac("lmRetried", len(set(re.findall(r"eval (\w+:naiverag-deepseek-v4.1-flash_poollong_r1/\d+): \w+ -> retrying", ev))))
r3 = load("skillrefine/run_stats_v3.json")
mac("vThreeCost", f2(st.mean(r["cost_usd"] for r in r3)))
mac("vThreeWall", f"{st.mean(r['wall_min'] for r in r3):.0f}")

rft = r"""\begin{table}[t]
  \centering
  \caption{\textbf{Held-out topics: first version (v1) and refined version (v3) against the same-model baselines}
  (\hoSl{} SurveyLens topics never used for refinement; paired differences with 95\% bootstrap CIs). The \textsc{Pool}
  baseline here received v1's candidate papers.}
  \label{tab:refine}
  \small
  \setlength{\tabcolsep}{3.5pt}
  \resizebox{\linewidth}{!}{\begin{tabular}{@{}llcccc@{}}
    \toprule
    & & \multicolumn{2}{c}{$-$ \textsc{NaiveRAG-Own}} & \multicolumn{2}{c}{$-$ \textsc{NaiveRAG-Pool}} \\
    \cmidrule(lr){3-4}\cmidrule(l){5-6}
    Judge & Component & v1 & v3 & v1 & v3 \\
    \midrule
    benchmark & outline & \haBjOutlineVOneOwn{} & \haBjOutlineVThreeOwn{} & \haBjOutlineVOnePool{} [\haBjOutlineVOnePoolLo, \haBjOutlineVOnePoolHi] & \haBjOutlineVThreePool{} [\haBjOutlineVThreePoolLo, \haBjOutlineVThreePoolHi] \\
    cross & outline & \haCjOutlineVOneOwn{} & \haCjOutlineVThreeOwn{} & \haCjOutlineVOnePool{} [\haCjOutlineVOnePoolLo, \haCjOutlineVOnePoolHi] & \haCjOutlineVThreePool{} [\haCjOutlineVThreePoolLo, \haCjOutlineVThreePoolHi] \\
    discipline & outline & \haDrOutlineVOneOwn{} & \haDrOutlineVThreeOwn{} & \haDrOutlineVOnePool{} [\haDrOutlineVOnePoolLo, \haDrOutlineVOnePoolHi] & \haDrOutlineVThreePool{} [\haDrOutlineVThreePoolLo, \haDrOutlineVThreePoolHi] \\
    discipline & content & \haDrContentVOneOwn{} & \haDrContentVThreeOwn{} & \haDrContentVOnePool{} [\haDrContentVOnePoolLo, \haDrContentVOnePoolHi] & \haDrContentVThreePool{} [\haDrContentVThreePoolLo, \haDrContentVThreePoolHi] \\
    cross & reference & \haCjReferenceVOneOwn{} & \haCjReferenceVThreeOwn{} & \haCjReferenceVOnePool{} [\haCjReferenceVOnePoolLo, \haCjReferenceVOnePoolHi] & \haCjReferenceVThreePool{} [\haCjReferenceVThreePoolLo, \haCjReferenceVThreePoolHi] \\
    discipline & reference & \haDrReferenceVOneOwn{} & \haDrReferenceVThreeOwn{} & \haDrReferenceVOnePool{} [\haDrReferenceVOnePoolLo, \haDrReferenceVOnePoolHi] & \haDrReferenceVThreePool{} [\haDrReferenceVThreePoolLo, \haDrReferenceVThreePoolHi] \\
    \bottomrule
  \end{tabular}}
\end{table}
"""

# ---------------------------------------------------------------- submission-grade mode (v4), 3 topics
W = H / "skillrefine/v4/academic-literature-workspace"
EV = ["cs-das002", "bio-sl003", "materials-sl065"]
for it, itn in ((1, "One"), (2, "Two")):
    for cfg, tag in (("with_skill", "New"), ("old_skill", "Old")):
        gs = [json.loads((W / f"iteration-{it}/eval-{e}/{cfg}/run-1/grading.json").read_text()) for e in EV]
        mac(f"sm{tag}It{itn}", " / ".join(str(g["summary"]["passed"]) for g in gs))
        mac("smChecks", gs[0]["summary"]["total"]) if (it, tag) == (2, "New") else None
        if cfg == "with_skill":
            tm = [json.loads((W / f"iteration-{it}/eval-{e}/{cfg}/run-1/timing.json").read_text())["total_duration_seconds"] / 60
                  for e in EV]
            mac(f"smWall{itn}", f"{min(tm):.0f}--{max(tm):.0f}")
for it, itn in ((1, "One"), (2, "Two")):
    core = []
    for e in EV:
        g = json.loads((W / f"iteration-{it}/eval-{e}/with_skill/run-1/grading.json").read_text())
        ev = next(x["evidence"] for x in g["expectations"] if x["text"].startswith("at least 25 core"))
        core.append(re.sub(r" of (\d+) core.*", r"/\1", ev))
    mac(f"smCoreFull{itn}", ", ".join(core))
# v3 surveys against the human surveys SurveyLens pairs with the same held-out topics
slmap = {(r["discipline"], r["topic"]): r for r in load("surveylens/topics_map.json")}
sltop = {t["topic_id"]: t for t in load("surveylens/remote/topics_sl.json")}
vw, vr, hw, hr = [], [], [], []
for sid in held["sl"]:
    md = (P / "deepseek-v4.1-flash_full_v3_sl" / sid / "review/literature.md").read_text(errors="replace")
    parts = re.split(r"\n#+\s*References\b", md, flags=re.I)
    vw.append(len(parts[0].split()))
    vr.append(len(re.findall(r"^\[\d+\]", parts[-1], re.M)))
    m_ = slmap[(sltop[sid]["discipline"], sltop[sid]["topic"])]
    hmd = Path("/home/juli/citation/SurveyLens") / m_["human_md"]
    if hmd.exists():
        hw.append(len(re.split(r"\n#+\s*(References|Bibliography)\b", hmd.read_text(errors="replace"), flags=re.I)[0].split()))
    hj = hmd.with_name(hmd.stem + "_split.json")
    if hj.exists():
        n_ = len(json.loads(hj.read_text()).get("references") or [])
        if n_:
            hr.append(n_)
mac("smVThreeWords", f"{st.median(vw):,.0f}".replace(",", "{,}"))
mac("smVThreeRefs", f"{st.median(vr):.0f}")
mac("smHumanWords", f"{st.median(hw):,.0f}".replace(",", "{,}"))
mac("smHumanRefs", f"{st.median(hr):.0f}")
for it, itn in ((1, "One"), (2, "Two")):
    sizes = []
    for e in EV:
        g = json.loads((W / f"iteration-{it}/eval-{e}/with_skill/run-1/grading.json").read_text())
        ev_ = {x["text"]: x["evidence"] for x in g["expectations"]}
        nref = re.match(r"(\d+)", ev_["cites at least 100 papers"]).group(1)
        nw = re.match(r"(\d+)", ev_["body of at least 12,000 words"]).group(1)
        sizes.append(f"{int(nw):,}".replace(",", "{,}") + f" words, {nref} references")
    mac(f"smSizes{itn}", "; ".join(sizes))
smt = r"""\begin{table}[t]
  \centering
  \caption{\textbf{Submission-grade mode: automatic checks on three topics} (computer science, biology,
  nanomedicine; one run each). The 13 checks cover size, structure, methods section, figures, handoff list,
  search log, citation check, venue completeness and core full-text reading. v3 receives the same prompt and has no such mode.}
  \label{tab:submode}
  \small
  \begin{tabular}{@{}lccc@{}}
    \toprule
    & checks passed (CS / bio / nano) & core papers read in full & wall time (min) \\
    \midrule
    v3, same prompt & \smOldItOne & --- & --- \\
    v4, first iteration & \smNewItOne & \smCoreFullOne & \smWallOne \\
    v4, second iteration & \smNewItTwo & \smCoreFullTwo & \smWallTwo \\
    \bottomrule
  \end{tabular}
\end{table}
"""

gen = PAPER / "generated"
gen.mkdir(exist_ok=True)
(gen / "numbers_v2.tex").write_text("% generated by tools/paper_numbers_v2.py; do not edit\n" + "\n".join(M) + "\n")
for name, body in (("tab_lm", lt), ("tab_sl", slt), ("tab_ci", cit), ("tab_refine", rft), ("tab_submode", smt)):
    (gen / f"{name}.tex").write_text("% generated by tools/paper_numbers_v2.py; do not edit\n" + body)
names = [re.match(r"\\newcommand\{\\(\w+)\}", m).group(1) for m in M]
dup = {n for n in names if names.count(n) > 1}
assert not dup, f"duplicate macros: {dup}"
print(f"wrote {gen}/numbers_v2.tex ({len(M)} macros) and 5 tables")
