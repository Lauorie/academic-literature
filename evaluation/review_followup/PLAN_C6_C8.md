# C6 and C8: pre-registration (internal review of 2026-10-07)

Written 2026-10-07, before any run, edit or judgment named here exists. Both analyses answer the internal review and
are reported whatever they show. Changes after this point go to "Deviations" with a timestamp.

## C8: the same agent without the skill (DAS-Bench)

Question: what does the skill add to the agent that runs it, with search held fixed?

Condition NoSkill-Agent: the harness of every Skill-Full run (gen.sh: headless Claude Code, generator
deepseek/deepseek-v4.1-flash through the same gateway, the same 3-hour limit, unprivileged user, per-session TMPDIR,
the same reading-mode sentence), with three differences:
1. a separate Claude Code config directory that holds no skill;
2. the WisPaper search service, which the skill reaches through its own script, is registered as an MCP server in
   that config, so the agent can call quick_search and deep_search directly (same endpoint and token as the skill);
3. the prompt drops "Use the academic-literature skill to" and states the output contract instead: Markdown at
   review/literature.md, citations as numbers in square brackets, and a "## References" section with one numbered
   entry per cited work in the form "[n] Authors. *Title.* Venue, Year. DOI or arXiv URL". The format line exists so
   that the DAS-Bench conversion can read titles and identifiers as it does for the skill; it says nothing about how
   to find, read or select papers.
Everything else (document parsing, web access) is whatever the agent finds without the skill.
Topics: the 30 DAS-Bench topics, one run each (run tag noskill_r1). A session that ends without a survey follows the
AUTO_RERUN rule of the Skill-Full runs (one rerun). Conversion: tools/make_submission.py (reference-section path, as
for a run without a ledger). Judging: the released evaluator, main judge qwen/qwen3.5-397b-a17b and the cross judge,
the six-attempt rule.

Primary: Skill-Full (mean of its three runs per topic) minus NoSkill-Agent on the DAS-Bench total, per judge, paired
over the topics scored in both, bootstrap 95% CI (10,000 resamples, seed 0, tools/analyze_paper.bootstrap_ci).
Secondary: family differences; body length; the same criterion split as C1 (without figure/table quality).
Reading rule:
- CI lower bound above 0 under both judges: the skill adds to the same agent with the same search; the paper says so.
- CI contains 0 under either judge: no measurable difference under that judge; the paper says the skill's lead over
  simple baselines does not separate from what the agent does by itself.
- CI upper bound below 0 under either judge: the agent without the skill scores higher under that judge; reported.

Reference integrity, secondary: the v3 reference verifier (citation_integrity/verify_refs.py, sources and rules
unchanged) on every NoSkill-Agent survey; per-survey defective rate against Skill-Full run 1, paired, bootstrap CI.
Because C3 found the verifier's labels condition-dependent, the NoSkill-Agent labels get the C3 audit procedure:
up to 25 entries per class (verified, metadata_error, not_found), search agents blind to condition and label, and
corrected rates computed the same way. Reading: as the C3 rule (lower with CI below 0 / no measurable difference /
higher).

## C6: is the outline gain heading depth? (SurveyLens, held-out topics)

Data: the 20 held-out SurveyLens topics; v1 surveys (pulled/deepseek-v4.1-flash_full_sl) and v3 surveys
(pulled/deepseek-v4.1-flash_full_v3_sl). Two mechanical edits, no model involved, body text unchanged:
- v1-split: in every top-level section of a v1 survey (except References) that has no third-level heading and at
  least two paragraphs, each paragraph gets a third-level heading made of its first sentence, citation markers and
  markdown removed, cut to its first ten words.
- v3-flat: every third-level heading of a v3 survey becomes a bold lead-in at the start of the paragraph it opened.
Both are staged and judged exactly as the held-out surveys were (process_sl.py, eval_sl_all.sh: benchmark judge two
passes and cross judge one pass; eval_sl_disc.sh: discipline rubric one pass).

Primary: outline score, v1-split minus v1, paired over the 20 topics, per judge configuration, bootstrap 95% CI; next
to it, v3 minus v1 (the reported gain). Secondary: v3-flat minus v3; content and reference components (should not
move); third-level heading counts.
Reading rule:
- v1-split minus v1 has a CI lower bound above 0 under the benchmark judge: mechanical heading depth alone raises the
  outline score; the paper reports the share of v3's gain it reaches (ratio of the means) under each configuration
  and says v3's outline gain cannot be read as better structure beyond the rest.
- That CI contains 0: mechanical heading depth does not earn the gain under that judge; the paper says the outline
  judge responds to more than heading count.
- v3-flat minus v3 is reported as how much of v3's score rides on the third level.

## Deviations

(none yet)
- 2026-10-07 20:05, before any C6 judgment: the C6 edit script's own text check compared v1-split with
  third-level headings removed against v1 with them kept; three v1 surveys that already had some third-level
  headings failed it. The check now removes them on both sides; the edits were correct. v3-flat first missed
  headings that sat on the line right after another heading or right above their paragraph; every heading line is
  now separated before the edit, as the rule requires (third-level headings left: 0).
- 2026-10-07 21:40 (C8, before any C8 score was read): topic 014 ended with a gateway error (HTTP 502, no survey);
  it was rerun once under the AUTO_RERUN rule and the failed session archived as .014_failed_api. The local sync
  loop left from the earlier experiments also converted the C8 runs under a skill_ method name and pushed them,
  and the remote watchdog judged that copy; those inputs and results were moved aside unread
  (dup_noskill_backup/ on the GPU host), and the sync loop now skips *_noskill_* runs. The reported C8 scores come
  only from noskill_deepseek-v4.1-flash_r1.
