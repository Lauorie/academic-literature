# v2 vs v1 on held-out topics: pre-registration

Written 2026-10-04, before any v2 run. Changes after this point go to "Deviations" with a timestamp.

## What runs

v2 = `skillrefine/v2/SKILL.md` (CHANGES.md); scripts unchanged. Generator, gateway, harness (`gen.sh`), reading mode
(full text when available, else abstract), withheld-survey guards, and timeouts are the ones the v1 runs used.
One v2 run per held-out topic (`heldout.json`): 6 DAS-Bench, 20 SurveyLens, 4 SurveyBench = 30 surveys.
Run dirs: `runs/deepseek-v4.1-flash_full_v2/<tid>`, `..._full_v2_sl/<slid>`, `..._full_v2_sb/<sbid>`.
During the v2 runs the evalbot copy of SKILL.md is v2 (v1 is kept as `SKILL.md.v1` and restored afterwards).

## Scoring (unchanged pipelines and judges)

- DAS-Bench: released evaluator, main judge qwen3.5-397b and the cross judge; Total and the four families.
- SurveyLens: generic rubric with the benchmark's judge (qwen3-30b, passes p1 and p2), cross judge p1, discipline rubric p1;
  outline, content, reference separately.
- SurveyBench: qwen3.5-397b judge, passes p1 and p2; content and outline.

## Comparison

v2 minus v1 per topic. v1 = Skill-Full: on DAS-Bench the mean of its three runs, elsewhere its single run.
SurveyLens (n=20): paired mean with bootstrap 95% CI (10,000 resamples, seed 0), wins/ties/losses, per component and judge.
DAS-Bench (n=6) and SurveyBench (n=4): per-topic differences and means only; too few topics for an interval.

Primary question, fixed now: does v2 raise the SurveyLens outline score under the benchmark's judge?
Reading rule:
- v2 is called an improvement if that outline difference has a CI lower bound above 0 and no SurveyLens component under
  any judge has a CI upper bound below 0, and the DAS-Bench mean Total difference under the main judge is not below -0.1.
- If the outline CI contains 0: no measurable outline gain.
- Any component with a CI upper bound below 0 is reported as a regression.
Run-to-run noise caveat: v1 has one run per SurveyLens topic, so a per-topic difference mixes the skill change with
generation variance; the paired CI over 20 topics is the guard against reading noise as an effect.

Also reported: body length and heading counts (`##`, `###`) per condition; cost and wall time per survey; whether
each v2 run produced `outline.md` and `manifest.tsv` (did the agent follow the new steps).

## Deviations

(none yet)

## Result (2026-10-04 15:20; 30/30 v2 runs, exit 0; all judgments scored)

SurveyLens, v2 - v1, n=20 (bootstrap 95% CI, wins/ties/losses):

| judge config | outline | content | reference |
|---|---|---|---|
| benchmark judge (qwen3-30b, p1+p2) | **+1.45 [1.10, 1.80]**, 17/3/0 | 0.00 (all 5) | +0.08 [-0.05, 0.20] |
| cross judge (qwen3.5-397b) | **+0.75 [0.40, 1.10]**, 13/6/1 | 0.00 (all 5) | **-0.40 [-0.80, -0.05]**, 3/8/9 |
| discipline rubric | **+1.54 [1.29, 1.77]**, 20/0/0 | -0.01 [-0.03, +0.01] | -0.07 [-0.28, +0.12] |

DAS-Bench, n=6, mean v2 - v1 (v1 = mean of three runs): main judge Total +0.04 (TSQ +0.18, HDQ -0.06, BSC +0.01, MAR +0.01);
cross judge Total -0.01 (TSQ -0.13, HDQ -0.21, BSC +0.15, MAR +0.14).
SurveyBench, n=4, outline v1 -> v2: 3.39 -> 4.50, 3.28 -> 4.67, 4.89 -> 5.00, 3.67 -> 4.61; content 5.00 -> 4.80, 4.90, 5.00, 4.90.

Structure (30 held-out surveys each): `###` headings per survey 3.0 -> 18.5; top-level TL;DR heading 29 -> 0;
`outline.md` written in 29/30 v2 runs, `manifest.tsv` in 30/30; median body 7600 -> 6985 words.

Reading rule: the outline CI is above 0, and DAS-Bench Total is above -0.1, but the cross judge's reference score has a
CI upper bound below 0. By the pre-registered rule v2 is **not** called an improvement; it is an outline gain with a
reference regression under the cross judge.

Exploratory, on that regression: in all 9 topics where it dropped, the judge's note names the share of "[venue unavailable]"
entries; reference relevance is rated ~100% in each. The share is 0.59 (v1) and 0.64 (v2) on these 20 topics and moves by up
to +/-0.5 per topic with the papers a run selects. The placeholder comes from the renderer and the search records, which v2
did not change; reference counts are equal (median 39.5). So the drop tracks record metadata the prose cannot fix; a code
change (fill missing venues from CrossRef before rendering) is the item that addresses it.

## v3: pre-registration (2026-10-04, before any v3 run)

v3 = v2 SKILL.md plus a `fill` step before `render` (Step 7b), and `citation_ledger.py fill`: for each cited entry with no
venue (not arXiv), the venue comes from CrossRef, by DOI, or by title search accepted only on a title (ratio >= 0.95),
first-author and year (+/-1) match; empty fields only; each fill logged as a `revise` with CrossRef provenance.
Tests: 12 new (`tests/test_fill.py`, local fake CrossRef) and the 40 existing ledger tests pass.
Dry run on copies of the 20 v2 SurveyLens ledgers (no generation, originals untouched): `[venue unavailable]` share
0.64 -> 0.12; 209 title-match fills, 162 with a publisher-consistent DOI prefix, 6 inconsistent of which 5 are known
legacy prefixes (OUP journals, Palgrave) and 1 doubtful (IEEE URL matched to an Optica record), 41 unmapped hosts.

Same 30 held-out topics, same harness, judges and comparison as above; run dirs `..._full_v3`, `_v3_sl`, `_v3_sb`.
Caveat: these topics were scored for v2 before `fill` was written, and `fill` answers the regression seen there, so
this is a weaker test than fresh topics; the change is mechanical (bibliographic fields), not tuned on prose or judges.

Reading rule for v3 against v1: the rule above, unchanged. Secondary: v3 - v2 on the same topics (reported, no rule).
Also reported: `[venue unavailable]` share per condition and whether each v3 run called `fill`.

### v3 deviation (2026-10-04 15:28, before any v3 run finished)
- The first v3 `citation_ledger.py` was built on the copy in `~/.claude/skills` (md5 8fc3d113…), which is older than the
  copy the evalbot runs use (md5 142f8a1b…: bioRxiv/OUP DOI parsing, display clean-up of CrossRef markup). It was
  deployed for under five minutes and no run had reached `render`. Rebuilt as the evalbot copy plus the `fill` patch
  (md5 aca20553…); both test files pass on it. v3 runs use this file. The original is kept as `citation_ledger.py.v1`.

## v3 result (2026-10-04 19:00; 30/30 runs exit 0; all judgments scored; `fill` called in 30/30 runs)

SurveyLens, v3 - v1, n=20:

| judge config | outline | content | reference |
|---|---|---|---|
| benchmark judge (qwen3-30b, p1+p2) | **+1.48 [1.15, 1.80]**, 18/2/0 | 0.00 (all 5) | +0.08 [0.00, 0.20] |
| cross judge (qwen3.5-397b) | **+0.80 [0.45, 1.10]**, 16/2/2 | -0.05 [-0.15, 0.00], 0/19/1 | **+0.90 [0.55, 1.25]**, 13/7/0 |
| discipline rubric | **+1.62 [1.28, 1.92]**, 19/0/1 | -0.02 [-0.06, +0.01] | +0.25 [-0.03, +0.54] |

DAS-Bench, n=6, mean v3 - v1: main judge Total +0.21 (BSC -0.07, TSQ +0.10, HDQ +0.24, MAR +0.56); cross judge Total +0.05
(BSC +0.19, TSQ -0.04, HDQ -0.13, MAR +0.18).
SurveyBench, n=4, outline v1 -> v3: 3.39 -> 4.56, 3.28 -> 4.44, 4.89 -> 4.94, 3.67 -> 4.83; content 5.0 -> 4.8, 5.0, 5.0, 5.0.
Structure: `[venue unavailable]` share 0.58 (v1) -> 0.11 (v3); `###` per survey 3.0 -> 18.8; TL;DR heading 29 -> 0; median body 7600 -> 7158 words.

Reading rule: outline CI above 0; no SurveyLens component with a CI upper bound below 0 (closest: cross-judge content,
one topic lost one point, upper bound exactly 0.00); DAS-Bench main-judge Total +0.21 > -0.1. **v3 meets the
pre-registered rule against v1.**

Secondary, v3 - v2 (same topics): cross-judge reference +1.30 [1.00, 1.60]; discipline reference +0.32 [0.08, 0.56];
outline and content unchanged (all CIs contain 0). The reference gain comes from `fill`; the outline gain from v2's edits.
Caveat from the pre-registration stands: these topics were seen when `fill` was written.

Note (2026-10-07): an earlier paper draft showed +0.20 for the v3 - v1 DAS-Bench main-judge total because its macro
script rounded half to even; with half-up rounding it shows +0.21, matching the value above (0.205).
