# academic-literature: skill, evaluation and refinement scripts

Companion release for *Verifiable Literature Surveys with an Agent Skill: Evaluation on Three Benchmarks and
Refinement from Its Own Traces*.

## Layout

```
skill/academic-literature/   the agent skill as evaluated last (v4: v3 plus the opt-in submission-grade mode)
  SKILL.md                    the procedure
  references/                 citation styles; submission_mode.md (loaded only for submission-grade requests)
  scripts/                    citation_ledger.py (ledger, render, check, revise, fill), verify_citations.py,
                              wis_mcp_search.py / wispaper_search_standalone.py (search), wisdoc_mcp_standalone.py
                              (PDF parsing), fulltext.py (open full-text routes), survey_figures.py (methods
                              numbers, taxonomy and timeline figures)
  tests/                      offline tests for the scripts
evaluation/
  harness/                    headless generation (gen.sh, queue_cap.sh) and the withheld-survey guard
                              (sb_guard.py hook, patch_search.py filter)
  das_bench/                  DAS-Bench conversion, analysis and the NaiveRAG baselines (naive_rag.py)
  length_matched/             the length-matched baseline (outline call + one call per section)
  citation_integrity/         NoRAG / Pool-Free generation and the reference verifier
  surveylens/                 SurveyLens processing, judging and analysis
  surveybench/                SurveyBench conversion, judging and analysis
  review_followup/            two analyses added after an internal review: the plan written before computing them
                              (PLAN.md), the per-criterion split of the length-matched comparison (c1_criteria.py),
                              the re-check of every delivered DAS-Bench survey against its ledger (c7_check.py, with
                              the two ledger-script versions it needs), and their results
refinement/                   SkillRefiner corpus conversion and runner, label rules (LABELS.md), the edits
                              applied (CHANGES.md, make_v2.py), held-out tests (EVAL.md, compare_ver.py)
protocols/                    the pre-registered protocols with every logged deviation
```

## Credentials

Nothing here holds a credential. The scripts read them from the environment:

| variable | used by |
|---|---|
| `WIS_MCP_URL`, `WIS_MCP_TOKEN` | the skill's search script |
| `WISDOCRS_BASE_URL` | PDF parsing |
| `PAPERBYPASS_AUTH_TOKEN` (or your own OpenAI/Anthropic-compatible gateway) | generation, judging, field extraction |
| `LLM_API_KEY`, `EMBEDDING_API_KEY` | SkillRefiner runs |

Gateway URLs, model names and server paths (`/root/...`, `/home/evalbot/...`) are the ones we used; change them for
your setup. Keep any `.env` file out of version control (`.gitignore` covers it).

## What is not here

Generated surveys, judge outputs, traces and the benchmarks' own data. DAS-Bench, SurveyLens, SurveyBench and
SkillRefiner are obtained from their authors.
