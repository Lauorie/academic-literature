# Results of the follow-up analyses (2026-10-07; plan in PLAN.md)

## C1 (c1_criteria.py -> c1_result.json)

Skill-Full (mean of three runs) minus baseline, DAS-Bench total, 30 topics, bootstrap 95% CI:

| baseline | judge | total | without figure/table | without figure/table and reference presentation |
|---|---|---|---|---|
| Pool-Long | main | +0.13 [0.04, 0.24] | -0.03 [-0.13, 0.07] | +0.05 [-0.05, 0.16] |
| Pool-Long | cross | +0.16 [0.10, 0.22] | +0.04 [-0.02, 0.11] | +0.10 [0.04, 0.16] |
| Pool | main | +0.46 [0.36, 0.56] | +0.31 [0.21, 0.42] | +0.43 [0.32, 0.53] |
| Pool | cross | +0.41 [0.30, 0.51] | +0.30 [0.20, 0.41] | +0.37 [0.27, 0.48] |

Figure/table quality: Skill-Full 3.67, Pool-Long 1.00 (main judge). Reading per plan: the CI without the
figure/table criterion contains 0 under both judges, so at matched length the lead rests on that criterion; the paper
says so in the abstract, introduction, Sec. 5.2, discussion and conclusion. The paper's 3.63/3.77 were run-1 values;
now three-run means (3.67/3.73).

## C7 (c7_check.py -> c7_result.json)

- Every one of the 120 sessions called `check`. The parser behind the first Table 7 matched only the literal
  `citation_ledger.py check` and needed "hard failures: 0" in the captured output; it missed `python3 "$L" check` and
  outputs the agent piped through grep/sed/tail. The 12 sessions it flagged are this artifact.
- Log: final check shows "hard failures: 0" in 113/120; hidden by the agent's own filter in 7; visible failure in 0.
- Re-run of check's hard-failure tests on the delivered files: 120/120 pass under a renderer version deployed during
  the runs (8fc3 on 2026-09-29; DOI view-suffix fix by 2026-09-30 afternoon; title clean-up in 142f, 2026-10-01).
  One session (full_r2/023) passes only under the reconstructed middle version.
- Entry audit: 6,380 delivered reference entries, all identical to the rendering of a ledger record; 0 edited,
  0 from outside the ledger. Three body numbers without an entry are not citations ("lambda in [0,1]" twice; prose
  quoting another paper's "ref [56]").
- Warnings check reports on the delivered files (mean per session): r1 20.0, r2 26.1, r3 25.1, Abs 24.3.
