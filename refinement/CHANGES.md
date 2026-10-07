# v2 SKILL.md: SkillRefiner lessons applied as targeted edits

SkillRefiner's merge rewrote the skill and dropped its operating instructions (LABELS.md, Deviations), so its
cluster proposals were applied by hand to the original file (user's choice, 2026-10-04). Every command, path,
citation syntax and check of the original is kept. `make_v2.py` applies the edits; `v2/SKILL.diff` is the diff.

| edit | where | source clusters (traces) |
|---|---|---|
| E1 probe search before the parallel round | Step 2 | positive: preflight probe (7, 5, 4) |
| E2 coverage audit written as a facet table | Step 3 | positive: coverage audit (12) |
| E3 `manifest.tsv` after selection | Step 4 | positive: manifest after ingest (8, 4, 4) |
| E4 truncated abstracts in abstract-only mode | Step 5 | negative: snippet-driven abstract-only reviews (5) |
| E5 Step 6b: hierarchical `outline.md` with a claim-to-evidence map before drafting | Step 6b (new) | negative: claim-evidence matrix (7); outline before drafting (4, 3, 3); flat H2-only (2, 2, 3) |
| E6 template: Introduction first with a bold bottom line; `###` subsections; comparison tables in themes; Conclusion; study table moved to an appendix | Step 7 | negative: TL;DR / At a glance front matter (10, 3, 3, 2); flat outline (3, 2, 2) |
| E7 quality bar: heading depth, synthesis aids, citation spread | Quality bar | negative: table-heavy recall-first (5); hub-paper reuse (2, 2) |

TL;DR and At a glance are demoted, not removed (user's choice): the bottom line opens the Introduction in bold,
the table moves to an appendix. Quick 3–5 paper scans keep their answer-first form.

Not applied: "draft the outline before any search" (the facets of Step 1 already plan the search; the outline is
locked after reading, Step 6b); "cap the corpus to the smallest set" outside abstract-only mode (it conflicts with
deep-survey breadth and had one cluster).

## v3 (code item)

`scripts/citation_ledger.py fill` and a `fill` call before `render` in Step 7b, to fill missing venues from CrossRef
(EVAL.md, v3 pre-registration). Tests: `tests/test_fill.py`.
