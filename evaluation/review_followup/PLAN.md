# Follow-up analyses after the internal review of 2026-10-07 (C1, C7)

Written 2026-10-07, before either analysis was computed. Both are exploratory: the internal review
(peer_review/main/20261007-1645/report.md) prompted them; no protocol named them. The paper reports them
whatever they show and marks them exploratory.

## C1: per-criterion decomposition of the length-matched comparison

Data: remote_results/{DAS-Bench, DAS-Bench-xjudge}/<method>/{bsc,mar,tsq_hdq}/api_off/<tid>.json, read with the
loader of tools/analyze_paper.py. Skill-Full = mean of its three runs per topic; topics scored in every run and in the
baseline (the set behind Table 4).

Per judge, for Skill-Full minus NaiveRAG-Pool-Long and, for the contribution's +0.46, Skill-Full minus NaiveRAG-Pool:
1. paired difference per criterion (16), bootstrap 95% CI (10,000 resamples, seed 0, `bootstrap_ci`);
2. the total without "Figure/Table Quality and Textual Integration" (mean of 15 criteria), with CI;
3. the total without that criterion and "Citation and Reference Presentation Integrity" (mean of 14), with CI.

Reading: descriptive, no decision rule. The paper reports (2) and (3) next to the totals and rewrites the contribution
and abstract to say what remains once the table criterion is set aside. If the CI of (2) contains 0 under a judge, the
paper says that under that judge the length-matched lead rests on the table criterion.

## C7: sessions delivered without a passing final check

Data: pulled/<run>/<tid>/review/{literature.md, literature.draft.md, citations.jsonl} for Skill-Full runs 1-3 and
Skill-Abs (120 sessions). Ledger code: the v1 citation_ledger.py the runs used (md5 142f8a1b..., copied from the
remote host to review_followup/ledger_v1/).

Per session:
1. Re-run v1 `check` without an evidence directory; record the hard-failure types (draft keys absent from the
   ledger; delivered file differs from what the ledger renders; unrendered keys left in the delivered file).
2. Audit the delivered References section entry by entry:
   (a) identical to the v1 rendering of some ledger record (active or dropped);
   (b) not identical, but its title matches a ledger record (normalized titles, similarity >= 0.95): a ledger
       paper whose entry text was edited;
   (c) no ledger record matches: a reference from outside the ledger.
3. Numbering: does render(draft, ledger) give the same reference list, in the same order, as the delivered file?
   If not, the DAS-Eval citation mapping (derived from draft + ledger) can disagree with the delivered survey.

Primary count: class (c) entries in the 12 sessions whose final check did not pass; the same count over all 120
sessions for context.

Reading: if class (c) is 0, the paper says no delivered reference came from outside the ledger, including in the
sessions that skipped or failed `check`, and names that audit next to "by construction". If it is above 0, the paper
reports the count and the sessions and limits the guarantee to sessions whose final check passed.
