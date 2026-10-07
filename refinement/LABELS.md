# SkillRefiner on academic-literature: corpus, labels, feedback

Written 2026-10-04, before any trace was converted or summarized and before any proposal exists.
Changes after this point go to "Deviations" with a timestamp.

## Skill

`~/.claude/skills/academic-literature/SKILL.md`, md5 73287092aeabc3e2c07eac288f45bbd5, identical to the copy the evaluation
runs used (`/home/evalbot/.claude/skills/academic-literature/SKILL.md`). SkillRefiner edits this file only.
Scripts (`citation_ledger.py`, `verify_citations.py`, search clients) are out of its reach; changes there are listed
separately as code items.
The refined skill goes to `skillrefine/out/`; the installed skill is not touched.

## Held-out topics (`heldout.json`, seed 20261004, drawn before conversion)

- DAS-Bench: 4 of 21 CS topics and 2 of 9 non-CS topics: 002 006 010 013 025 026 (all four runs of each).
- SurveyLens: 2 per discipline: sl003 sl008 sl013 sl017 sl026 sl030 sl034 sl040 sl042 sl044 sl053 sl055 sl065 sl067 sl073 sl074 sl082 sl084 sl093 sl097.
- SurveyBench: sb02 sb08 sb12 sb14.

No trace of a held-out topic enters `traces.jsonl`. The refined skill is a candidate until it is run and scored on these topics.

## Corpus

deepseek-v4.1-flash Skill runs only (the two Opus runs are excluded: other model):
- DAS-Bench full r1, r2, r3 and abstract-only r1: 24 training topics x 4 = 96 traces.
- SurveyLens full: 80 traces. SurveyBench full: 16 traces.

## Binary labels (a failure is a topic where a same-model baseline beat the skill)

- DAS-Bench: failure if the run's Total under the main judge (qwen3.5-397b) is below NaiveRAG-Pool-Long's Total on that topic (the length-matched baseline, same pool and generator).
- SurveyLens: failure if the outline score under the benchmark's judge (qwen3-30b, mean of passes p1 and p2) is <= 3, or if the content score under the discipline rubric is below NaiveRAG-Pool's on that topic.
- SurveyBench: failure if the overall score (mean of content and outline, mean of passes, judge qwen3.5-397b) is below NaiveRAG-Pool's on that topic.

Counts on all topics before the split (computed while writing this file): DAS 34/120 failures, SurveyLens 52/100.

## Evaluator feedback

Only failing traces get feedback, as the last span: "EVALUATOR FEEDBACK (metadata from the benchmark's scorer, not agent output)", containing:
- the scores that made it a failure, next to the baseline's scores;
- DAS-Bench: the rationales of the four lowest-scoring submetrics (TSQ/HDQ/BSC/MAR JSON);
- SurveyLens: the outline judge's notes, and the discipline-rubric content notes when content lost;
- SurveyBench: scores only (its results carry no rationale);
- body length and heading counts (`##`, `###`) of the survey and of the baseline's survey.
`ground_truth_file` is not used: its wrapper text addresses a final `Answer:` line, which a survey has not.

## Trace conversion

Main-agent events only, in order: assistant text, tool calls (name plus arguments, each capped at 2000 characters),
tool results (capped at 1500 characters). Sub-agent transcripts appear only as the result returned to the main agent.
A first span states the benchmark, topic, reading mode and the label rule. Every converted trace must fit the
summarizer's budget (`context_window(model) - OUTPUT_RESERVE`, minus the fixed prompt); the converter asserts it.

## Refinement model

`openai/gpt-5.4-mini` through the PaperBypass gateway (the configuration of record's model). The config names it
`openai/openai/gpt-5.4-mini` because litellm strips one provider prefix and the gateway accepts only `openai/gpt-5.4-mini`;
the runner registers that name with litellm (272k input context, gateway prices) so the summarizer budget is the model's real one.
Embeddings: `openai/text-embedding-3-small` through OpenRouter (user's instruction, 2026-10-04), instead of the record's
`qwen3-embedding:4b`. All other `RefineConfig` fields stay at the configuration of record.

## Run record

- 2026-10-04 12:05, full run: 192 training traces (108 pass, 84 fail; 160 entered clusters), 31 positive and 22 negative
  clusters merged (23 negative proposals, 3 rejected by the evidence gate). Output `out/combined/proposed_skill.md`.

## Deviations

- 2026-10-04 12:10: the merge rewrote the 48,237-byte skill into 13,499 bytes and removed its operating instructions:
  no `citation_ledger.py` or `verify_citations.py` command, no `[wp:key]` citation syntax, no search/parse invocations,
  no "do not write a References section" rule in its original form. An agent cannot run the skill's scripts from it.
  `proposed_skill.md` is kept as SkillRefiner's raw output and is not deployed.
