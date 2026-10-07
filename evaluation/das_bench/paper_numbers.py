#!/usr/bin/env python3
"""Write LaTeX macros and result tables from the analysis JSON, so no number is typed by hand.

Usage: paper_numbers.py <analysis.json> <variance.json> <process.json> <paper dir>
Writes <paper>/generated/numbers.tex, tab_main.tex, tab_paired.tex.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

FAMS = ["BSC", "TSQ", "HDQ", "MAR", "Total"]
BENCH = {"DAS-Bench": "M", "DAS-Bench-xjudge": "X"}
COND = {"Skill-Full": "SkillFull", "Skill-Abs": "SkillAbs", "NaiveRAG-Pool": "NaivePool", "NaiveRAG-Own": "NaiveOwn",
        "Skill-Full-Opus": "SkillOpus", "NaiveRAG-Pool-Long": "NaivePoolLong", "NoSkill-Agent": "NoSkill"}
COND_TEX = {"Skill-Full": r"\textsc{Skill-Full}", "Skill-Abs": r"\textsc{Skill-Abs}",
            "NaiveRAG-Pool": r"\textsc{NaiveRAG-Pool}", "NaiveRAG-Own": r"\textsc{NaiveRAG-Own}",
            "NoSkill-Agent": r"\textsc{NoSkill-Agent}"}
LEADER = [("DAS", [3.85, 4.22, 4.28, 5.00, 4.34]), ("Human", [3.84, 4.29, 4.24, 5.00, 4.34]),
          ("Naive RAG", [3.73, 4.06, 4.22, 4.09, 4.03])]  # DAS-Bench leaderboard, 30 topics (README)


def tm(txt: str) -> str:
    """Typeset a leading ASCII hyphen as a true minus sign."""
    return txt.replace("-", "\\ensuremath{-}", 1) if txt.startswith(("-", "+-")) or txt.startswith("-") else txt


def f2(x: float) -> str:
    x = 0.0 if abs(x) < 0.005 else x  # no "-0.00"
    return tm(f"{x:.2f}")


def s2(x: float) -> str:
    """Signed, two decimals, true minus."""
    x = 0.0 if abs(x) < 0.005 else x
    return tm(f"{x:+.2f}") if x < 0 else f"{x:+.2f}"


def macro(name: str, value: str) -> str:
    return f"\\newcommand{{\\{name}}}{{{value}}}\n"


def main() -> int:
    res = json.loads(Path(sys.argv[1]).read_text())
    var = json.loads(Path(sys.argv[2]).read_text())
    proc = json.loads(Path(sys.argv[3]).read_text())["summary"]
    out = Path(sys.argv[4]) / "generated"
    out.mkdir(parents=True, exist_ok=True)

    m = ""
    for b, bj in BENCH.items():
        for c, cm in COND.items():
            e = res["condition"][b].get(c)
            if not e:
                continue
            m += macro(f"n{cm}{bj}", str(e["n_topics"]))
            for f in FAMS:
                m += macro(f"{cm}{f}{bj}", f2(e[f]))
                if e.get(f"{f}_sd_runs") is not None:
                    m += macro(f"{cm}{f}Sd{bj}", f"{e[f'{f}_sd_runs']:.3f}")
            for sub in ("cs", "noncs"):
                if sub in e:
                    m += macro(f"{cm}Total{sub.capitalize()}{bj}", f2(e[sub]["Total"]))
        for key, p in res["paired"][b].items():
            other = COND[key.split("_vs_")[1]]
            m += macro(f"d{other}{bj}", f2(p["mean_diff_total"]))
            m += macro(f"d{other}Lo{bj}", f2(p["ci95"][0]))
            m += macro(f"d{other}Hi{bj}", f2(p["ci95"][1]))
            m += macro(f"d{other}Wins{bj}", str(p["wins"]))
            m += macro(f"d{other}Ties{bj}", str(p["ties"]))
            m += macro(f"d{other}N{bj}", str(p["n"]))
            m += macro(f"d{other}RunWins{bj}", str(p["per_run_wins"])) + macro(f"d{other}RunPairs{bj}", str(p["per_run_pairs"]))
            for f, v in p["family_diffs"].items():
                m += macro(f"d{other}{f}{bj}", s2(v))
    for jk, jm in (("main", "M"), ("xjudge", "X")):
        v = var[jk]
        m += macro(f"rejudgeR{jm}", f2(v["rejudge_pearson"]))
        m += macro(f"rejudgeAbs{jm}", f2(v["rejudge_mean_abs_diff"]))
        m += macro(f"rejudgeMean{jm}", f2(abs(v["rejudge_mean_diff_old_minus_new"])))
        m += macro(f"judgeSd{jm}", f2(v["per_topic_judge_sd"]))
        m += macro(f"genSd{jm}", f2(v["per_topic_generation_sd_3runs"]))
        pure = max(v["per_topic_generation_sd_3runs"] ** 2 - v["per_topic_judge_sd"] ** 2, 0) ** 0.5
        m += macro(f"genPureSd{jm}", f2(pure))
    ag = res["judge_agreement"]
    rs = [a["pearson_topic_total"] for a in ag.values()]
    m += macro("crossRMin", f2(min(rs))) + macro("crossRMax", f2(max(rs)))
    for meth, cm in (("skill_deepseek-v4.1-flash", "SkillFull"), ("skill_deepseek-v4.1-flash_abs_r1", "SkillAbs"),
                     ("naiverag-deepseek-v4.1-flash_pool_r1", "NaivePool"), ("naiverag-deepseek-v4.1-flash_own_r1", "NaiveOwn")):
        c = res["coverage"][meth]
        m += macro(f"refs{cm}", f"{c['refs_mean']:.0f}") + macro(f"words{cm}", f"{c['words_mean']:,}".replace(",", "{,}"))
        m += macro(f"covCs{cm}", f"{100 * c['cov_cs']:.0f}") + macro(f"covNoncs{cm}", f"{100 * c['cov_noncs']:.0f}")
    if len(sys.argv) > 5:
        sup = json.loads(Path(sys.argv[5]).read_text())
        crit = {"Claim-Level Citation Support": "Support", "Reference Faithfulness and Attribution Accuracy": "Faith",
                "Multi-Reference Synthesis Coverage and Quality": "Synth", "Citation Distribution Balance and Non-Redundancy": "Balance"}
        for b, bj in BENCH.items():
            for c, short in crit.items():
                m += macro(f"abs{short}{bj}", s2(sup["bsc_criteria_full_minus_abs"][b][c]["mean"]))
            for cond, cm in COND.items():
                e = sup["cards_ge20"][b].get(cond)
                if e:
                    m += macro(f"ge{cm}N{bj}", str(e["n_topics"])) + macro(f"ge{cm}Total{bj}", f2(e["Total"]))
                    m += macro(f"ge{cm}BSC{bj}", f2(e["BSC"]))
        m += macro("nLowCards", str(sup["n_bsc_results_lt20_cards"]))
        m += macro("nRubricViol", str(len(sup["rubric_violations_lt20_cards_score5"])))
        att = sup["attempts"]
        m += macro("nRetried", str(att["items_retried"]))
        dist = {int(k): v for k, v in att["distribution_of_attempts_used"].items()}
        m += macro("nRetriedTwo", str(dist.get(2, 0))) + macro("nRetriedMore", str(sum(v for k, v in dist.items() if k > 2)))
        m += macro("maxAttemptsUsed", str(max(dist)))
    for meth, cm in (("skill_deepseek-v4.1-flash_full_r2", "SkillFullRtwo"), ("skill_deepseek-v4.1-flash_full_r3", "SkillFullRthree")):
        if meth in res["coverage"]:
            m += macro(f"refs{cm}", f"{res['coverage'][meth]['refs_mean']:.0f}")
    # Process statistics across all skill runs (files next to the r1 file)
    pdir = Path(sys.argv[3]).parent
    runs = [("full_r1", pdir / "process_stats_full_r1.json"), ("full_r2", pdir / "process_stats_full_r2.json"),
            ("full_r3", pdir / "process_stats_full_r3.json"), ("abs_r1", pdir / "process_stats_abs_r1.json")]
    ps = {k: json.loads(f.read_text())["summary"] for k, f in runs if f.exists()}
    if len(ps) == 4:
        full = [ps[k] for k in ("full_r1", "full_r2", "full_r3")]
        mean3 = lambda key: sum(x[key]["mean"] for x in full) / 3  # noqa: E731
        m += macro("costFull", f"{mean3('cost_usd'):.2f}") + macro("wallFull", f"{mean3('wall_min'):.0f}")
        shares = [x["evidence_full"]["mean"] / (x["evidence_full"]["mean"] + x["evidence_abstract"]["mean"]) for x in full]
        m += macro("fullShareMin", f"{100 * min(shares):.0f}") + macro("fullShareMax", f"{100 * max(shares):.0f}")
        m += macro("costAbs", f"{ps['abs_r1']['cost_usd']['mean']:.2f}") + macro("wallAbs", f"{ps['abs_r1']['wall_min']['mean']:.0f}")
        # Check outcomes come from review_followup/c7_check.py: the first parser here missed `check` calls made
        # through a shell variable and outputs the agent filtered, and counted those sessions as failures.
        c7 = json.loads((pdir.parent / "review_followup" / "c7_result.json").read_text())
        c7_cond = {"full_r1": "Skill-Full r1", "full_r2": "Skill-Full r2", "full_r3": "Skill-Full r3", "abs_r1": "Skill-Abs"}
        for k, cond in c7_cond.items():
            sel = [r for r in c7["sessions"] if r["condition"] == cond]
            ps[k]["c7_logged_pass"] = sum(r["last_check_hard"] == 0 for r in sel)
            ps[k]["c7_recheck_pass"] = sum(bool(r["recheck_pass_versions"]) for r in sel)
            ps[k]["c7_warnings"] = c7["summary"]["by_condition"][cond]["warnings_mean"]
        for k, name in (("full_r1", "RunOne"), ("full_r2", "RunTwo"), ("full_r3", "RunThree"), ("abs_r1", "RunAbs")):
            m += macro(f"checkLogged{name}", str(ps[k]["c7_logged_pass"]))
        allc7 = c7["summary"]["all"]
        m += macro("cSevenSessions", str(allc7["sessions"])) + macro("cSevenEntries", f"{allc7['entries']:,}".replace(",", "{,}"))
        m += macro("cSevenLoggedPass", str(allc7["last_check_visible_pass"]))
        m += macro("cSevenHidden", str(len(allc7["last_check_not_visible"])))
        m += macro("cSevenRecheckPass", str(allc7["recheck_pass"])) + macro("cSevenOutside", str(allc7["c_outside_ledger"]))
        m += macro("cSevenFlagged", str(c7["summary"]["flagged_in_paper"]["sessions"]))
        m += macro("cSevenWarnMin", f"{min(ps[k]['c7_warnings'] for k in c7_cond):.1f}")
        m += macro("cSevenWarnMax", f"{max(ps[k]['c7_warnings'] for k in c7_cond):.1f}")
        rows = [("Search calls, \\texttt{deep\\_search} in parentheses", lambda x: f"{x['search_calls']['mean']:.1f} ({x['deep_search_calls']['mean']:.1f})"),
                ("Result files ingested into the ledger", lambda x: f"{x['ingested_result_files']['mean']:.1f}"),
                ("Papers added to the ledger", lambda x: f"{x['ledger_adds']['mean']:.0f}"),
                ("Papers dropped with a recorded reason", lambda x: f"{x['ledger_drops']['mean']:.1f}"),
                ("Papers cited in the survey", lambda x: f"{x['cited']['mean']:.1f}"),
                ("Reader sub-agents", lambda x: f"{x['subagents']['mean']:.1f}"),
                ("Evidence files: full text / abstract", lambda x: f"{x['evidence_full']['mean']:.1f} / {x['evidence_abstract']['mean']:.1f}"),
                ("Warnings \\texttt{check} reports on the delivered files", lambda x: f"{x['c7_warnings']:.1f}"),
                ("Agent turns", lambda x: f"{x['turns']['mean']:.0f}"),
                ("Wall time (min)", lambda x: f"{x['wall_min']['mean']:.1f}"),
                ("Generation cost (USD)", lambda x: f"{x['cost_usd']['mean']:.2f}"),
                ("Final \\texttt{check} shows zero hard failures in the log", lambda x: f"{x['c7_logged_pass']}/{x['n_runs']}"),
                ("Delivered file passes \\texttt{check} when re-run", lambda x: f"{x['c7_recheck_pass']}/{x['n_runs']}")]
        body = "\n".join("    " + name + " & " + " & ".join(fn(ps[k]) for k, _ in runs) + r" \\" for name, fn in rows)
        (out / "tab_process.tex").write_text(r"""\begin{table}[t]
  \centering
  \caption{\textbf{Process statistics of \skill{}}: means per session over 30 sessions per run (\dsflash{}). Search calls are counted from the executed shell commands and may undercount calls issued inside loops; ingested result files are counted from the ledger. The last two rows read the session log, where the agent sometimes filtered the output of its final \texttt{check}, and re-run \texttt{check} on the delivered files with the ledger code deployed during the runs.}
  \label{tab:process}
  \small
  \begin{tabular}{@{}lcccc@{}}
    \toprule
    & \multicolumn{3}{c}{\textsc{Skill-Full}} & \textsc{Skill-Abs} \\
    \cmidrule(lr){2-4}\cmidrule(l){5-5}
    Quantity per session & $r_1$ & $r_2$ & $r_3$ & $r_1$ \\
    \midrule
""" + body + r"""
    \bottomrule
  \end{tabular}
\end{table}
""")
    (out / "numbers.tex").write_text("% generated by tools/paper_numbers.py; do not edit\n" + m)

    # Main table
    rows = []
    conds = [c for c in ("Skill-Full", "Skill-Abs", "NoSkill-Agent", "NaiveRAG-Pool", "NaiveRAG-Own")
             if all(c in res["condition"][b] for b in BENCH)]
    best = {b: max(res["condition"][b][c]["Total"] for c in conds) for b in BENCH}  # bold marks the top total
    for c in conds:
        cells = []
        for b in BENCH:
            e = res["condition"][b][c]
            for f in FAMS:
                sd = e.get(f"{f}_sd_runs")
                val = f2(e[f]) + (f"$_{{\\pm{sd:.2f}}}$" if sd is not None and f == "Total" else "")
                cells.append(f"\\textbf{{{val}}}" if f == "Total" and e[f] == best[b] else val)
        rows.append(COND_TEX[c] + " & " + " & ".join(cells) + r" \\")
    lead = [f"{name} & " + " & ".join(f2(v) for v in vals) + r" & \multicolumn{5}{c}{---} \\" for name, vals in LEADER]
    tab = (r"""\begin{table}[t]
  \centering
  \caption{\textbf{Main results on DAS-Bench (30 topics).} Family scores on a 1--5 scale under the main judge (\mainjudge{}) and the cross judge (\xjudge{}). \textsc{Skill-Full} is the mean over runs $r_1$--$r_3$ on the topics scored in every run, with the standard deviation of the three run means on the total as subscript (family-level standard deviations are at most """ + f2(max(res['condition'][b]['Skill-Full'][f + '_sd_runs'] for b in BENCH for f in FAMS[:4])) + r"""). \textsc{NoSkill-Agent} is the same agent session without the skill (\cref{sec:noskill}). Leaderboard rows use the original judge deployment and the frozen candidate pools; they are shown for scale only and are not comparable (\cref{sec:bench}). The leaderboard's Naive RAG is the original authors' system, not our \textsc{NaiveRAG} baselines.}
  \label{tab:main}
  \footnotesize
  \setlength{\tabcolsep}{2.4pt}
  \begin{tabular}{@{}l ccccc ccccc@{}}
    \toprule
    & \multicolumn{5}{c}{Main judge} & \multicolumn{5}{c}{Cross judge} \\
    \cmidrule(lr){2-6}\cmidrule(l){7-11}
    Condition & \BSC{} & \TSQ{} & \HDQ{} & \MAR{} & Total & \BSC{} & \TSQ{} & \HDQ{} & \MAR{} & Total \\
    \midrule
""" + "\n".join("    " + r for r in rows) + r"""
    \midrule
    \multicolumn{11}{@{}l}{\emph{DAS-Bench leaderboard (reference scale only)}} \\
""" + "\n".join("    " + r for r in lead) + r"""
    \bottomrule
  \end{tabular}
\end{table}
""")
    (out / "tab_main.tex").write_text(tab)

    # Paired table: one row per comparison and judge, no scaling
    prow = []
    for other in ("NaiveRAG-Own", "NaiveRAG-Pool", "Skill-Abs", "NoSkill-Agent"):
        if f"Skill-Full_vs_{other}" not in res["paired"]["DAS-Bench"]:
            continue
        for k, (b, jname) in enumerate((("DAS-Bench", "main"), ("DAS-Bench-xjudge", "cross"))):
            p = res["paired"][b][f"Skill-Full_vs_{other}"]
            head = (r"\multirow{2}{*}{$-$ " + COND_TEX[other] + "}") if k == 0 else ""
            cells = [jname, s2(p["mean_diff_total"]), f"[{s2(p['ci95'][0])}, {s2(p['ci95'][1])}]",
                     f"{p['wins']}/{p['n']}"] + [s2(p["family_diffs"][f]) for f in FAMS[:4]]
            prow.append(head + " & " + " & ".join(cells) + r" \\" + (r" \addlinespace" if k == 1 else ""))
    ptab = (r"""\begin{table}[t]
  \centering
  \caption{\textbf{Paired differences over topics.} $\Delta$ is the mean difference in total score between \textsc{Skill-Full} (averaged over its runs) and the other condition on the same topic, with a 95\% bootstrap confidence interval (10{,}000 resamples of topics) and the number of topics on which \textsc{Skill-Full} scores higher. Family columns give the mean difference per family.}
  \label{tab:paired}
  \small
  \setlength{\tabcolsep}{3.5pt}
  \begin{tabular}{@{}l l c c c cccc@{}}
    \toprule
    \textsc{Skill-Full} & Judge & $\Delta$ Total & 95\% CI & Wins & \BSC{} & \TSQ{} & \HDQ{} & \MAR{} \\
    \midrule
""" + "\n".join("    " + r for r in prow) + r"""
    \bottomrule
  \end{tabular}
\end{table}
""")
    (out / "tab_paired.tex").write_text(ptab)
    sys.stdout.write(f"wrote {out}/numbers.tex ({m.count(chr(10))} macros), tab_main.tex, tab_paired.tex\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
