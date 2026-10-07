# Two analyses for the paper: pre-registration

Written 2026-10-05, before either analysis was run. No new generation; existing outputs and judgments only.
Changes after this point go to "Deviations" with a timestamp.

## A. v3 against same-model baselines on the held-out topics

Held-out topics (`heldout.json`): 6 DAS-Bench, 20 SurveyLens, 4 SurveyBench. Those topics never entered the
SkillRefiner corpus; every other topic did, so v3 is compared on these only.

- DAS-Bench (n=6): Total and families, main and cross judge. v3 (one run) minus each of NaiveRAG-Own, NaiveRAG-Pool,
  NaiveRAG-Pool-Long; v1 (mean of three runs) minus the same baselines, for reference. Per-topic values and means;
  no interval at n=6.
- SurveyLens (n=20): outline, content, reference under the benchmark judge (p1+p2), the cross judge and the
  discipline rubric. v3 minus NaiveRAG-Own and minus NaiveRAG-Pool; v1 minus the same, for reference. Paired mean,
  bootstrap 95% CI (10,000 resamples, seed 0, `tools/analyze_paper.bootstrap_ci`), wins/ties/losses.
- SurveyBench (n=4): content and outline, v3 and v1 against NaiveRAG-Own and NaiveRAG-Pool; per topic only.

Caveat stated with the results: the NaiveRAG-Pool baselines were built from the v1 run's candidate pool, not from
v3's; v3 found its own pool. On these topics "Pool" is a same-model, same-search-service baseline, not a same-pool one.
No reading rule: the result is descriptive and is reported whatever it shows.

## B. Citation integrity of v3

Same verifier and settings as `citation_integrity/PROTOCOL.md` v3 (CrossRef and arXiv via DataCite; LLM field
extraction with the verbatim-identifier rule; up to 40 entries per survey, seeded by the topic number).
Surveys: v3 on the 6 DAS-Bench and 20 SurveyLens held-out topics; v1 on the same 26 topics (DAS-Bench run 1 results
already exist; the 20 SurveyLens v1 surveys are verified now).
Metrics per survey: defective rate (metadata_error + not_found over parseable), metadata_error rate, bad-identifier
rate. v3 minus v1 paired over 26 surveys, bootstrap 95% CI (seed 0), wins/ties/losses.
Expected direction, stated in advance: v3's `fill` adds venues and DOIs from CrossRef, which can lower metadata errors
and also add identifiers that the check then tests. No reading rule; reported whatever it shows.
Known limit carried over: `not_found` mostly measures source coverage (90% of audited `not_found` entries exist).

## Deviations

(none yet)

## Result A (2026-10-05; `paper_analysis_a.json`)

SurveyLens, n=20, versus NaiveRAG-Pool (v1 in brackets):
- outline: benchmark judge +0.03 [-0.08, 0.15] (v1 -1.45 [-1.78, -1.13]); cross judge -0.15 [-0.45, 0.15] (v1 -0.95);
  discipline rubric +0.81 [0.39, 1.24] (v1 -0.81 [-1.29, -0.30]).
- content: benchmark judge 0 (ceiling); cross -0.05 [-0.15, 0]; discipline +0.19 [0.13, 0.25] (v1 +0.21).
- reference: benchmark judge +0.03; cross +0.70 [0.30, 1.05] (v1 -0.20 [-0.55, 0.15]); discipline -0.18 [-0.43, 0.05] (v1 -0.43 [-0.67, -0.19]).
Versus NaiveRAG-Own: outline +0.10 / +0.15 / +0.71 [0.32, 1.11]; discipline content +0.47; discipline reference +0.45.
DAS-Bench, n=6, Total minus baseline (main / cross judge): v3 - Pool-Long +0.33 (5/6) / +0.10 (3/6); v1 +0.13 (3/6) / +0.05 (4/6);
v3 - Pool +0.56 / +0.60; v3 - Own +0.96 / +0.85.
SurveyBench, n=4, outline v3 vs Pool: 4.56/4.67, 4.44/4.89, 4.94/4.56, 4.83/4.78; content 4.8-5.0 for both.
Reading: on held-out topics v3 removes the outline deficit v1 had against same-model baselines (parity under two judges,
ahead under the discipline rubric) and keeps v1's content advantage under the discipline rubric.

## Result B (2026-10-05; `paper_analysis_b.json`; n = 26 surveys: 6 DAS-Bench + 20 SurveyLens held-out)

| per-survey rate | v3 | v1 | v3 - v1 [95% CI] | v3 lower / tie / higher |
|---|---|---|---|---|
| defective (metadata_error + not_found) | 9.5% | 9.6% | -0.0 pp [-2.6, +2.7] | 15 / 2 / 9 |
| metadata_error | 2.9% | 4.3% | -1.4 pp [-2.8, -0.04] | 17 / 4 / 5 |
| not_found | 6.6% | 5.2% | +1.4 pp [-0.6, +3.5] | 11 / 2 / 13 |
| bad identifier | 2.3% | 2.8% | -0.5 pp [-1.6, +0.6] | 8 / 11 / 7 |

Reading: `fill` lowers metadata errors; the overall defect rate is unchanged because not_found, which mostly measures
the verifier's source coverage, moves the other way within noise.
