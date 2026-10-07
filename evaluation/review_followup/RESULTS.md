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

# C3 and C4 (2026-10-07; plan in PLAN_C3_C4.md)

## C3 (prepare_c3.py, c3/, c3_analyze.py -> c3_result.json)

216 entries audited by 7 search agents blind to condition and label; 2 unsure (dropped).

| cell | label right | entries truly defective |
|---|---|---|
| verified (all three conditions) | 75/75 | 0/75 |
| not_found: skill / NoRAG / Pool-Free | 0/24, 1/25, 2/24 do not exist | 1/24, 6/25, 2/24 |
| metadata_error: skill / NoRAG / Pool-Free | 9/25, 20/25, 8/16 | same |

Corrected defect rate per survey: skill 1.4%, NoRAG 7.8%, Pool-Free 1.4% (verifier: 8.0 / 14.3 / 10.5).
Skill - NoRAG -6.4 pp [-9.2, -4.1] (holds); Skill - Pool-Free -0.1 [-1.6, 1.4] (does not survive).
Work does not exist: skill 0.0%, NoRAG 0.3% (one sampled entry, R179, arXiv id points to another work), Pool-Free
0.8% (both unfound entries are records in its candidate pool, copied verbatim).
Field errors on real works (added decomposition): skill 1.4%, NoRAG 7.6%, Pool-Free 0.7%; skill - Pool-Free +0.7
[-0.2, 1.8].

## C4 part A (c4_partA.py -> c4_partA_result.json)

Per skill session (120): 229 claim numbers in citing sentences/table rows; 97.7% in the cited papers' evidence files,
0.7% only in another paper's file, 0.3% in none, 1.4% in sentences whose cited papers have no file. Warnings 23.9 per
session: 19.8 records without identifier, 2.1 figures not in the cited evidence, 1.9 venue vs arXiv DOI.

## C4 part B (prepare_c4.py, c4/, c4_analyze.py -> c4_result.json; c4_density.py -> c4_density.json)

Eligible sentences per survey: skill 37.2 (1,115 in all), NaiveRAG-Pool 0.8 (25 in all; none in 16 surveys).
Skill: 7 of 60 sentences have a wrong figure (12%, Wilson [6, 22]); of 207 figures, 10 misattributed (in the paper,
other meaning) and 1 absent; 57 of 60 read in full text. All 11 wrong figures are in the cited paper's evidence
file, so check passes them. NaiveRAG-Pool: 0 of 18 checkable sentences wrong ([0, 18]); 2 unverifiable, 2 no claim.
Skill - Pool error share +12 pp [3, 22] (topics bootstrap); the samples differ in size and in figures per sentence
(3.5 against 1). Three further skill sentences with correct figures misdescribe the method (auditor notes, batch 5).

## Checks added after the results (2026-10-07)

- C3: the 16 skill metadata_error labels the audit overturned were read against the verifier's reasons. Most trace to
  the verifier: name normalization (diacritics such as Varıcı/Kıcıman, candidate records without authors, records
  that store given names as surnames, a compound surname), ACM DOIs whose record title did not match, and one match to
  a different paper. Two auditor calls are borderline (R100: year 2022 for a 2020 paper with a 2022 arXiv revision;
  R135: 2018 for HNSW, TPAMI online 2018). Counting both as errors raises the skill's corrected rate from 1.4% to
  about 1.7%; no conclusion changes.
- C3: the verified cell had 0 errors in 75; the 95% Wilson upper bound is 4.9%. The corrected rates treat the
  verified labels as right.
- C4 density over all prose, whatever the citation style: claim numbers per 1,000 words, skill 35.8, NaiveRAG-Pool 0.8
  (c4_density.py).

# C6 (2026-10-07; plan in PLAN_C6_C8.md; c6_prepare.py, c6_analyze.py -> c6_result.json)

Outline score, paired over the 20 held-out SurveyLens topics, bootstrap 95% CI:

| configuration | v1-split - v1 | v3 - v1 | v3-flat - v3 |
|---|---|---|---|
| benchmark judge (generic) | +0.33 [-0.03, 0.70] | +1.48 [1.15, 1.80] | +0.03 [0.00, 0.08] |
| cross judge (generic) | -0.50 [-0.90, -0.10] | +0.80 [0.45, 1.10] | -0.15 [-0.45, 0.15] |
| discipline rubric | +0.40 [0.15, 0.64] | +1.62 [1.28, 1.92] | -1.26 [-1.55, -0.99] |

Third-level headings per survey: v1 1.9, v1-split 44.1, v3 18.0, v3-flat 0. Reading per plan: the benchmark-judge CI
of v1-split - v1 contains 0, so mechanical heading depth does not earn the gain under that judge; under the
discipline rubric it reaches 25% of v3's gain. v3's gain survives flattening under both generic configurations.

# C8 (2026-10-07; plan in PLAN_C6_C8.md; gen_noskill.sh, queue_noskill.sh, c8_sync.sh, c8_analyze.py -> c8_result.json)

NoSkill-Agent: the Skill-Full harness without the skill, WisPaper as MCP tools, 30 DAS-Bench topics (014 rerun once
after a gateway 502). Skill-Full (mean of 3 runs) minus NoSkill-Agent, 30 topics:

| judge | total | without figure/table | TSQ | HDQ |
|---|---|---|---|---|
| main | +0.01 [-0.07, 0.10] | -0.15 [-0.23, -0.05] | -0.19 [-0.32, -0.05] | -0.03 [-0.21, 0.18] |
| cross | +0.07 [0.01, 0.15] | -0.04 [-0.11, 0.04] | +0.05 [-0.08, 0.18] | +0.20 [0.07, 0.35] |

Reading per plan: the main-judge CI contains 0, so no measurable difference under that judge; the skill's lead over
the single-call baselines does not separate from what the agent does by itself. Median body words: NoSkill 6,384,
Skill-Full 7,678.

Reference integrity (verifier v3 rules on all 30 NoSkill surveys; audit of 75 NoSkill labels as in C3):
verifier 8.0% (skill) vs 12.3% (NoSkill), -4.3 [-9.9, 0.9]; corrected 1.4% vs 5.4%, -4.1 [-7.2, -1.5].
2 of 25 audited NoSkill not-found entries do not exist and are absent from the WisPaper results the agent received
(S003, topic 020; S013, topic 023): invented references, about 0.6% of NoSkill entries.
