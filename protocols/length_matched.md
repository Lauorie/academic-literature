# Length-matched baseline on DAS-Bench: pre-registration

Written 2026-10-02, before any length-matched output exists. No result of this baseline has been generated or scored.
Changes after this point go to the "Deviations" section at the end, with a timestamp.

## Why

On DAS-Bench, Skill-Full beats NaiveRAG-Pool by 0.46 (main judge) and 0.41 (cross judge) in Total.
Skill-Full surveys are about twice as long (median body 7678 words against 3707 for Pool).
Within the baselines, body length correlates with TSQ and HDQ at r = +0.5 to +0.6 under the cross judge.
The two length distributions barely overlap (longest baseline 5929 words, shortest Skill-Full 5184).
The current data cannot separate "the skill writes better" from "the skill writes more".
This baseline asks: given the same candidate papers and told to write as much as the skill wrote, does a single generation call close the gap?

## Condition: NaiveRAG-Pool-Long

Identical to NaiveRAG-Pool (`tools/naive_rag.py --pool-from pulled/deepseek-v4.1-flash`) in every respect but two:

1. One sentence is added to the prompt, after "Synthesize across papers rather than summarizing them one by one.":
   "The survey body, not counting the reference list, should be about {W} words long."
   W is the topic's target length, defined below.
2. `max_tokens` rises from 32000 to 64000, because the expected output is twice as long and the Pool runs already spent about 6k tokens on reasoning. The cap does not touch an output that stops earlier.

Unchanged: generator `deepseek/deepseek-v4.1-flash`, temperature 0.7, candidate pool = all active records of Skill-Full run 1's citation ledger for the topic (the same pool NaiveRAG-Pool used), abstracts cut at 1200 characters, citation by list number, reference list rendered from the records, one retry when the call returns no text, one generation per topic.

**Target length W.** For each topic, the mean body word count of the three Skill-Full runs (runs 1, r2, r3).
Body = `review/literature.md` up to the first heading matching `\n#+\s*References\b` (case-insensitive), split on whitespace.
W is rounded to the nearest 100 and written to `<run>/target_words`.

## Pilot and the generation variant

Pilot: topics 001, 002, 003 with the single-call variant above (variant A).
A passes if all three outputs finish with `finish_reason=stop` and reach at least 85% of W.
The pilot looks at length and finish reason only. Pilot outputs are not converted or scored before the decision.

- A passes: run the remaining 27 topics with A. The pilot outputs stay in the condition.
- A fails: archive the pilot outputs (their lengths are reported) and run all 30 topics with variant B.

Variant B (fixed now, implemented only if A fails): one call returns an outline as JSON, with sections and a word budget per section summing to W; then one call per section writes that section, given the same paper list, the full outline and the section's budget; the sections are concatenated in order and the reference list is rendered as in A. Same model, temperature, pool and citation rule.

Length check on the full run: report the distribution of body/W. The condition counts as length-matched if the median ratio lies in [0.85, 1.15]. If it does not, the comparison is still reported, labeled as not length-matched.

## Evaluation

Same as every other DAS-Bench condition: `tools/make_submission.py` conversion, the released evaluator, main judge `qwen/qwen3.5-397b-a17b` and the cross judge, up to three judge attempts for a failed judgment, a failed judgment never counted as a score.
The remote watchdog launches the evaluation; nothing about scoring changes.

## Analysis (fixed now)

Primary: Total difference Skill-Full (mean of three runs per topic) minus NaiveRAG-Pool-Long, per judge, paired over the 30 topics; bootstrap 95% CI (10,000 resamples, seed 0, as in `tools/analyze_paper.py`); wins/ties/losses. Same code path as the existing Skill-Full vs NaiveRAG-Pool comparison.

Secondary:
- the same difference for each family (BSC, TSQ, HDQ, MAR);
- gap closure on Total: (Pool-Long − Pool) / (Skill-Full − Pool), per judge;
- body length and heading counts (`##`, `###`) per condition.

Reading rule, fixed before any score exists:
- CI lower bound above 0 under both judges: at matched length the skill still scores higher; the paper keeps the claim that the gain over the same pool comes from the reading and writing procedure, and cites this baseline as the control for length.
- CI contains 0 under either judge: the gain over Pool cannot be separated from length; the paper says so and rewrites the claim (the skill writes longer surveys from the same pool; at matched length no difference is measurable under that judge).
- CI upper bound below 0 under either judge: the paper reports that a length-matched single call scores higher under that judge.

The result goes into the paper whatever it shows.

## Pilot result (2026-10-02 11:39)

Variant A, single call, `finish_reason=stop` on all three:

| topic | W | body words | ratio |
|---|---|---|---|
| 001 | 7100 | 6894 | 0.97 |
| 002 | 9500 | 6006 | 0.63 |
| 003 | 7100 | 6023 | 0.848 |

Two of three fall below 0.85, so A fails. Following the rule above, all 30 topics run with variant B.
The A outputs stay in `length_matched/pilot/` and are never converted or scored.

Implementation details of B, fixed before any B output exists:
- Outline call: the NaiveRAG-Pool prompt (topic, structure instructions, paper list) plus a request to return only JSON `{"title": str, "sections": [{"heading": str, "words": int, "plan": str}]}`, the abstract as the first section, budgets summing to about W.
  If the reply does not parse as that JSON, the call is repeated once; a second failure fails the topic, which is reported as missing.
- Section calls: the same paper list and citation rule, the full outline with budgets, and the instruction to write only the named section, about its budget, starting with the line `## <heading>`. The calls run independently; no call sees another section's text.
- The survey is `# <title>`, then the sections in outline order, then the reference list rendered from the records as in A (citation numbers refer to one shared list, so the global renumbering is unchanged).
- Every call: same model, temperature 0.7, `max_tokens` 64000, one retry when it returns no text. Token usage is summed over the calls.
- A section that writes its own `References` heading is cut at that heading before concatenation, so the global renderer cannot drop the sections after it.
- Smoke test on topic 001 (11:42): 16 sections, body 6558 of 7100 words (0.92), all calls `stop`; no section wrote a References heading, so its output is identical under the cut rule and is kept as topic 001.
- Output: `pulled/naiverag-deepseek-v4.1-flash_poollong_r1/<tid>`. The local watchdog converts it and the remote watchdog scores it.

## Generation result (2026-10-02 11:59)

Variant B, 30/30 topics, exit 0, every call `finish_reason=stop`. Body/W: median 0.925, range 0.87-0.98, inside [0.85, 1.15], so the condition counts as length-matched. Median body 6882 words.

## Result (2026-10-02, both judges complete, 30/30 topics, no failed judgment)

| | main judge | cross judge |
|---|---|---|
| Skill-Full Total | 4.385 | 4.322 |
| NaiveRAG-Pool-Long Total | 4.250 | 4.160 |
| NaiveRAG-Pool Total | 3.923 | 3.917 |
| Skill-Full - Pool-Long | +0.135 [0.036, 0.237], 19/0/11 | +0.162 [0.102, 0.222], 26/1/3 |
| family diffs vs Pool-Long (BSC/TSQ/HDQ/MAR) | +0.06 / +0.03 / +0.15 / +0.31 | -0.01 / +0.16 / +0.27 / +0.23 |
| gap closure (Pool-Long - Pool)/(Skill-Full - Pool) | 0.71 | 0.60 |

Reading rule: the CI lower bound is above 0 under both judges, so the pre-registered reading applies: at matched length the skill still scores higher.
Size, reported with it: length accounts for 60-71% of the Skill-Full vs Pool gap; the remaining 0.14-0.16 is a third of the original. Under the main judge 58% of the remainder is MAR (artifact: tables, reference presentation, layout); TSQ is level (+0.03). MAR submetrics (main judge): Figure/Table 3.63 for Skill-Full against 1.00 for both Pool conditions (Skill-Full has a Markdown table in 30/30 surveys, Pool-Long in 0/30); reference presentation 3.77 against 5.00. Analysis: `length_matched/analysis_lm.json` (tools/analyze_paper.py).

## Deviations

- 2026-10-02 11:50, before any score: the analysis section said seed 42; the existing code path it names (`tools/analyze_paper.py`, `bootstrap_ci`) uses seed 0. Corrected to seed 0 so the new comparison uses the same code as the old ones.

## Note (2026-10-07, paper version 2)

The "Why" section's "r = +0.5 to +0.6" was read off an exploratory run before this protocol. The paper reports the
recomputed values (tools/paper_numbers_v2.py): cross judge, both baselines, TSQ and HDQ, r = 0.37-0.52; main judge,
NaiveRAG-Own 0.58-0.60, NaiveRAG-Pool -0.02 to 0.19.
