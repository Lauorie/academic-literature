# Follow-up analyses C3 and C4 (internal review of 2026-10-07)

Written 2026-10-07, before any sample was drawn or audited. Both analyses are exploratory; the paper reports them
whatever they show. Auditors are LLM agents with web and bibliographic search (as in the earlier audit of the
reference-integrity study, which the paper must describe as such); they see no condition and no verifier label.

## C3: how accurate are the verifier's labels, per condition?

Data: citation_integrity/results_v3 (the reported verifier version), conditions skill_full, norag, poolfree; classes
verified, metadata_error, not_found (unparseable excluded, as in the primary metric).

Sample: per condition x class, 25 entries drawn at random (seed 20261007) from all checked entries of that cell, or
every entry when the cell holds fewer (poolfree metadata_error: 16). Items are shuffled across cells and split into
batches. Each item shows the entry text with its leading number, markdown emphasis and the skill's placeholder marks
("[venue unavailable]", "[authors unavailable]", "[no locator]", "[unverified]") removed; nothing else changes.

Auditor answers per item: does the work exist; the authoritative record found (title, first author, year, DOI or
arXiv id, URL); title_ok, first_author_ok, year_ok (within one year of some version), identifier (correct /
another_work / does_not_resolve / none). A field the entry does not give is not an error (the verifier's rule).

Truth: an entry is defective if the work does not exist, or its title, first author, year (more than one year off)
or DOI/arXiv id is wrong. "unsure" items are reported and dropped from the estimates.

Outputs:
1. per cell, the share of entries whose audit agrees with the label (verified -> not defective; metadata_error ->
   exists and defective; not_found -> does not exist) and the share defective, with Wilson 95% intervals;
2. corrected per-survey defect rate per condition: each checked entry counts as the audited defective share of its
   cell; mean over surveys; Skill-Full minus each baseline, paired over topics, with a nested bootstrap (audited items
   resampled within cells, then topics; 10,000 resamples, seed 0).

Reading: if the corrected Skill-Full minus NoRAG interval lies below 0, the paper keeps "fewer defective entries than
the same model writing from memory" and gives the corrected rates next to the verifier's; if it contains 0, the paper
says the difference does not survive the correction. The same for Pool-Free. The paper reports the label accuracy per
cell either way.

## C4: are the numbers in the surveys attributed to the right papers?

Part A, deterministic, all 120 skill sessions (Skill-Full r1-r3, Skill-Abs), v1 check code at run time (ledger_das/):
- warnings from `check` on the delivered files, by type: cited paper without evidence file; figure not in the cited
  paper's evidence; record warnings (no identifier, venue/DOI mismatch, other);
- claim numbers (check's own `_claim_numbers`) in sentences and table rows that cite papers: share found in the cited
  papers' evidence files, share whose cited papers have no evidence file, share found only in another paper's
  evidence file, share in no evidence file.

Part B, claim audit, Skill-Full run 1 against NaiveRAG-Pool (the same 30 topics, the same candidate papers):
- unit: a prose sentence (not a table row, not a heading) in the survey body that cites exactly one reference and
  holds at least one claim number under check's rule; two per topic per condition, drawn at random (seed 20261007),
  120 claims in all;
- the auditor sees the sentence with its citation marker replaced by "[cited]", the cited reference entry, and the
  numbers to check; no condition;
- the auditor reads the cited paper (full text where reachable: arXiv, PMC, open publisher pages; else the abstract)
  and judges each number: supported (reported by that paper for what the sentence says), misattributed (in the paper
  but for something else, or not this paper's figure), absent (full text read, number not there), unverifiable (only
  the abstract reachable and the number not in it). A claim is an error if any of its numbers is misattributed or
  absent; unverifiable claims are reported and left out of the error share.

Outputs: per condition, the shares supported / error / unverifiable, with Wilson intervals; Skill-Full minus
NaiveRAG-Pool in error share, bootstrap over topics (10,000 resamples, seed 0).

Reading: descriptive. The comparison is not an ablation of evidence files: the two conditions also differ in reading
depth (full text against 1,200-character abstracts) and in generation procedure. If the skill's error share is lower
with an interval below 0, the paper says the skill's numbers are more often right and names the confounds; if not,
it says no difference is measurable in this sample. Either way the paper reports the skill's error share, replaces
"The evidence files narrow that gap" with what Part A and Part B show, and reports Part A's breakdown.

## Additions before any audit ran (2026-10-07, after drawing the samples)

- C4 sample: NaiveRAG-Pool has only 22 eligible sentences over the 30 topics (22 topics hold fewer than two; most hold
  none), against 60 drawn for Skill-Full. The sample stays as drawn; the paper reports the counts and, as a
  descriptive addition, the number of eligible sentences per survey in each condition.
- C4 auditor instruction: a token the sentence does not present as a figure of the cited paper (a product or model
  name such as "RTX 4090", a number about another work) is marked not_a_claim and ignored; a claim whose numbers are
  all not_a_claim drops out of the shares.
