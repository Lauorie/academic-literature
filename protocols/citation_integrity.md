# Citation integrity on DAS-Bench: pre-registration

Written 2026-10-02, before any output of the new conditions exists and before any reference of any condition has been verified.
Changes after this point go to "Deviations" with a timestamp.

## Question

The skill's design claim is that its references cannot be invented: the model cites ledger keys and a script renders the list from search records.
No experiment so far tests this against a generator that writes its own references, because every NaiveRAG baseline also renders its list from records.
This experiment measures how many references are wrong or unfindable when the same model writes them itself, and how many are wrong in the skill's output.

## Conditions (30 DAS-Bench topics each, generator `deepseek/deepseek-v4.1-flash`, temperature 0.7, max_tokens 32000, one call per topic, one retry on empty text)

- **Skill-Full**: existing run 1 (`pulled/deepseek-v4.1-flash`). No new generation.
- **NoRAG** (new): no papers given. The NaiveRAG prompt with the paper list removed and the citation rule replaced by: "Cite the literature with numbers in square brackets, e.g. [3] or [2, 7]. End with a section `## References` that lists every cited work as a numbered entry with its authors, title, venue, year, and DOI or arXiv identifier when you know it. Cite only works that exist."
- **Pool-Free** (new): the NaiveRAG-Pool prompt and candidate pool (all active records of Skill-Full run 1's ledger, abstracts cut at 1200 characters), with the citation rule replaced by: "Cite them with numbers in square brackets, e.g. [3] or [2, 7]. Do not cite anything else. End with a section `## References` that lists every cited work as a numbered entry with its authors, title, venue, year, and DOI or arXiv identifier when you know it." The list is the model's own text; nothing is rendered from records.

Prompts are in `gen_free.py`, written before generation.

## Unit and sampling

The unit is one entry of a survey's reference list, i.e. the text after the first `References` heading, split into numbered entries.
For each survey, all entries are verified when there are at most 40; otherwise 40 are drawn at random (Python `random.Random(seed=int(topic_id))`, without replacement).
The same rule applies to every condition.

## Field extraction

Each entry string goes to `qwen/qwen3-30b-a3b-instruct-2507` (temperature 0) with one instruction: return JSON `{title, authors (surnames, in order), year, doi, arxiv_id}` copied from the string, null when absent; do not correct or complete anything.
This is extraction only, applied identically to all conditions. An entry whose extracted title is null or shorter than 3 words is classed `unparseable`.

## Lookup (deterministic, no LLM)

Sources: CrossRef, OpenAlex, DBLP, arXiv API. Semantic Scholar is not used (unauthenticated requests are rate-limited, HTTP 429 on 2026-10-02).
Candidates for an entry: the record for its DOI (CrossRef), the record for its arXiv id (arXiv), and the top 5 title-search hits from each of CrossRef, OpenAlex, DBLP and arXiv.
Title match: normalized titles (lowercase, non-alphanumerics to spaces, collapsed) with `difflib.SequenceMatcher` ratio >= 0.90.
Author match: the entry's first surname, normalized and accent-stripped, equals the surname of any of the candidate's first three authors.
Year match: |entry year - candidate year| <= 1 (preprint against publication).

## Classes

- `verified`: some candidate matches title, author and year (a missing author list or year in the entry counts as a match: there is nothing to contradict).
- `metadata_error`: some candidate matches the title but none matches author and year; or the entry's DOI or arXiv id resolves to a work whose title does not match while the title is found elsewhere.
- `not_found`: no candidate from any source matches the title.
- `unparseable`: see above.

Venue and page numbers are not checked.

Search order: the DOI and arXiv-id lookups always run; title searches run in the order CrossRef, OpenAlex, DBLP, arXiv and stop once an entry is `verified`. Because `verified` is the best class and the identifier check has already run, stopping early gives the same class as querying every source; it only spares the arXiv API (one request per 3 seconds by its terms). Responses are cached on disk.

## Hand audit of the classifier

After classification, 40 `not_found` entries (pooled over conditions, `random.Random(0)`) and 20 `verified` entries are checked by hand with web search, blind to the condition (the condition label is stripped before the check).
The audit reports the share of `not_found` entries that turn out to exist (the classifier's miss rate). It does not change any class; the miss rate is reported next to the main numbers.

## Analysis (fixed now)

Primary metric per survey: defective rate = (`metadata_error` + `not_found`) / (entries checked, excluding `unparseable`). `unparseable` counts are reported separately.
Secondary: `not_found` rate alone, per survey; pooled class shares per condition.
Paired comparisons over the 30 topics: Skill-Full minus NoRAG and Skill-Full minus Pool-Free, mean difference of the per-survey defective rate, bootstrap 95% CI (10,000 resamples, seed 0, `bootstrap_ci` of `tools/analyze_paper.py`), wins/ties/losses.

Reading rule:
- Skill-Full defective rate lower than a baseline with the CI upper bound below 0: the paper states that the skill produces fewer defective references than that baseline, with the rates.
- CI contains 0: the paper states no measurable difference against that baseline.
- Skill-Full higher with the CI lower bound above 0: the paper reports it.
Skill-Full's defects, if any, are described by source (they come from search records, since the model cannot write metadata).

The result goes into the paper whatever it shows.

## Deviations

- 2026-10-02, before any condition was verified (during the verifier's synthetic test): DBLP answers scripted queries with an Anubis bot-challenge HTML page (status 200), so it is dropped. Sources are CrossRef, OpenAlex and arXiv. Non-JSON/HTML responses are treated as unavailable and not cached.
- 2026-10-02, same synthetic test: a DOI of the form 10.48550/arxiv.<id> is a DataCite DOI that CrossRef does not hold, so it is now looked up as arXiv id <id>. Synthetic test result: 26 cases (3 topics x {4 real, 1 wrong year, 1 wrong first author, 2 invented titles, 1 wrong DOI}) built from NaiveRAG-Pool search records; 26/26 classified as intended after one correction to the test itself: a 'real' case built from a search record whose author order is wrong (record: Nassi first; arXiv 2601.09625: Brodt, Feldman, Schneier, Nassi) was classed metadata_error, which is correct. Search records themselves can carry metadata errors.

- 2026-10-02, after generation, before any reference was verified: 12 of 30 NoRAG outputs (none of Pool-Free) ended with `finish_reason=length` at max_tokens 32000; reasoning used 21-30k tokens, and 2 of them (008, 019) have no reference list. Rule, applied by finish reason alone: every truncated output is regenerated once with the same prompt and max_tokens 64000; the 32k outputs are archived as `runs/norag/.<tid>_truncated32k` and not verified. An output still truncated at 64k is verified with the entries it has and flagged.
- Same time: the arXiv API returned HTTP 429 and stopped the first verification pass before any survey was finished. The client now waits up to 5 minutes on 429 and a survey whose source stays unavailable is redone in a later pass instead of being classified.
- 2026-10-02 18:10, before any survey was verified (0 results written): the arXiv API kept answering HTTP 429 ("Rate exceeded") even at one request per 3 seconds, so no survey could finish. arXiv lookups now go through DataCite, the registry of arXiv DOIs, whose records are arXiv's own metadata: id lookup `api.datacite.org/dois/10.48550/arXiv.<id>`, title search `client-id=arxiv.content`, top 5. The synthetic test is rerun with this source before verification restarts.
  Synthetic test with DataCite (about 18:08): 26/26.
- 2026-10-02 19:20: OpenAlex exhausted its anonymous daily budget (HTTP 429, retryAfter 45592 s; keys are now required) after 11 Skill-Full surveys had been verified with it; no NoRAG or Pool-Free survey had been verified. To keep one source set for every survey, OpenAlex is dropped: sources are CrossRef and arXiv (through DataCite). All surveys, including those 11, are verified again with this set. The 11 earlier results are kept in `results_with_openalex_partial/` and reported as a sensitivity check (how many entries OpenAlex alone would have found). The hand audit measures the classifier's miss rate with the reduced set.

## Result v1 (2026-10-02 20:30) - SUPERSEDED, verifier bug, see Deviations

| | Skill-Full | NoRAG | Pool-Free |
|---|---|---|---|
| entries in lists / checked | 1373 / 1140 | 2068 / 1157 | 4198 / 1200 |
| verified (pooled) | 88.4% | 84.4% | 88.3% |
| metadata_error | 6.8% | 8.5% | 2.3% |
| not_found | 4.5% | 6.1% | 9.2% |
| unparseable | 0.3% | 1.1% | 0.3% |
| mean per-survey defective rate | 11.4% | 15.0% | 11.5% |

Paired, defective rate: Skill-Full - NoRAG = -3.7 pp [-7.3, +0.2], 21/0/9; Skill-Full - Pool-Free = -0.2 pp [-2.6, +2.4], 14/2/14.
Secondary, not_found rate: vs NoRAG -2.0 pp [-5.0, +1.0]; vs Pool-Free -4.7 pp [-6.8, -2.8], 22/5/3.
Reading rule: both primary CIs contain 0, so the pre-registered reading is "no measurable difference" against both baselines.

## Deviations after the v1 result

- 2026-10-02 20:40, found after seeing the v1 result, while reading Skill-Full's metadata_error entries: the field extractor often split one person's name into several list elements (`"E Lumer"` -> `["E", "Lumer"]`, `"Shahul Es"` -> `["Shahul", "Es"]`), so the "first author" compared with the candidate was a given name or initial. 6 of the first 8 Skill-Full metadata_error entries inspected were this artifact. The bug can only turn a correct entry into metadata_error, in every condition. Fix: the extractor returns full names as written (one string per person, no "et al."), and the code takes the family name (part before a comma; else the last token; else the first token when the last is an initial, as in "Lin Q"). All 90 surveys are re-extracted and reclassified with the same sources and sample. v1 results are kept in `results_v1_authorbug/`; the v1 table above is superseded and not used. The hand audit, already started on v1 fields, is used for its existence judgments, which do not depend on authors.

  Synthetic test after the fix: 29/29 (the 26 cases plus three author formats that hit the bug: 'E Lumer, et al.', 'Shahul Es, et al.', 'Lin Q, Wen Y').

## Hand audit (2026-10-02 21:20, blind: three agents saw only extracted fields, no condition, no class)

Sample drawn from v1 classes. The not_found/verified classes depend on the title only, which the author bug did not touch, so the sample is valid for the existence question.

| set | n | exists | not found | unsure |
|---|---|---|---|---|
| not_found (pre-registered) | 40 | 36 | 3 | 1 |
| verified (pre-registered) | 20 | 20 | 0 | 0 |
| metadata_error (exploratory) | 20 | 20 | 0 | 0 |

- Classifier miss rate: 36 of 40 `not_found` entries exist (90%). With CrossRef and arXiv only, `not_found` mostly measures source coverage (OpenReview-only papers, theses, recent journal papers), not fabrication.
- By condition, not_found entries that exist: NoRAG 9/9, Skill-Full 11/11, Pool-Free 16/20. The 4 Pool-Free entries not found by hand (A12, A13, A16, A59) are copied verbatim from records in the topic's candidate pool (ResearchGate PDFs and ProQuest dissertations returned by the search service); the model did not invent them.
- No sampled entry in any condition was invented by the model.
- The auditors reported identifier errors on real works (DOI or arXiv id pointing to an unrelated paper) on 15 of 80 items (A03 A19 A21 A22 A26 A28 A29 A31 A43 A53 A58 A61 A65 A68 A76).

## Result v2 (2026-10-02 21:45, after the author fix; the reported result)

| | Skill-Full | NoRAG | Pool-Free |
|---|---|---|---|
| reference entries / survey (mean) | 46 | 69 | 140 |
| checked | 1140 | 1157 | 1200 |
| verified (pooled) | 90.7% | 85.2% | 89.2% |
| metadata_error | 4.5% | 7.6% | 1.4% |
| not_found | 4.6% | 6.1% | 9.2% |
| unparseable | 0.3% | 1.1% | 0.3% |
| mean per-survey defective rate (primary) | 9.1% | 14.3% | 10.6% |
| entries carrying a DOI or arXiv id | 75% | 98% | 5% |

Primary, pre-registered:
- Skill-Full - NoRAG: -5.2 pp [-9.0, -1.4], 21/1/8. CI upper bound below 0: the skill's lists contain fewer defective entries than memory-based generation.
- Skill-Full - Pool-Free: -1.5 pp [-4.1, +1.1], 17/2/11. No measurable difference.
Secondary: not_found rate vs NoRAG -1.9 pp [-4.9, +1.1]; vs Pool-Free -4.7 pp [-6.7, -2.7].

Read with the hand audit: 90% of not_found entries exist, and no sampled entry was invented in any condition, so the defective rate measures wrong metadata plus source coverage, not fabrication.

Exploratory (not pre-registered), metadata_error rate per survey: Skill-Full - NoRAG -3.3 pp [-5.4, -1.4]; Skill-Full - Pool-Free +3.1 pp [+1.4, +5.0]. Pool-Free writes an identifier on 5% of entries (its paper list shows no DOI), so it rarely has an identifier to get wrong. Of Skill-Full's 51 metadata errors, 19 are identifiers in the search record that resolve to another work; the rest are author or year mismatches in the records. The model cannot write metadata in the skill, so these are search-record errors passed through.

## Deviation after the v2 result

- 2026-10-02 22:00, found while counting identifiers that resolve to nothing (an exploratory check suggested by review): the field extractor invents identifiers. Skill-Full entries carry publisher URLs (e.g. `ieeexplore.ieee.org/abstract/document/10172517/`), and the extractor returned DOIs that appear nowhere in the entry (`10.1109/ICSE.2023.00087`). Counts of extracted identifiers absent from the entry text: Skill-Full 148 DOIs, NoRAG 2 DOIs, Pool-Free 5 arXiv ids. An invented DOI that resolves to another work made the entry `metadata_error`; one that resolves to nothing was ignored. The bug works against Skill-Full. Fix, deterministic: an extracted DOI or arXiv id counts only if it appears verbatim (case-insensitive) in the entry string. The stored v2 extractions are reclassified with this rule (`reclassify.py`, cached lookups; no new extraction). v2 is superseded by v3. The v2 table stays above for the record.

## Result v3 (2026-10-02 22:10, the reported result: author fix + verbatim-identifier rule)

| | Skill-Full | NoRAG | Pool-Free |
|---|---|---|---|
| verified (pooled) | 91.8% | 85.2% | 89.3% |
| metadata_error | 3.3% | 7.6% | 1.3% |
| not_found | 4.7% | 6.1% | 9.2% |
| mean per-survey defective rate (primary) | 8.0% | 14.3% | 10.5% |

Primary, pre-registered:
- Skill-Full - NoRAG: -6.3 pp [-10.3, -2.2], 22/2/6. Reading: fewer defective entries than memory-based generation.
- Skill-Full - Pool-Free: -2.5 pp [-4.9, -0.1], 17/5/8. The rule's condition (upper bound below 0) is met by 0.1 pp; the gap comes from not_found (secondary: -4.5 pp [-6.5, -2.5]), and the hand audit found 16 of 20 sampled Pool-Free not_found entries exist. Reported as met, with this caveat; it is not a robust difference.

Stability across verifier versions, Skill-Full - NoRAG: v1 -3.7 [-7.3, +0.2]; v2 -5.2 [-9.0, -1.4]; v3 -6.3 [-10.3, -2.2]. Skill-Full - Pool-Free: v1 -0.2 [-2.6, +2.4]; v2 -1.5 [-4.1, +1.1]; v3 -2.5 [-4.9, -0.1].
Both bugs were found by reading Skill-Full's error entries; the baselines' entries were not read with the same care before the fixes. Each fix is a deterministic rule applied to all conditions.

Exploratory (not pre-registered): bad-identifier rate per survey (an identifier written in the entry that resolves to nothing or to another work): Skill-Full 2.5%, NoRAG 10.4%, Pool-Free 2.2%; Skill-Full - NoRAG -7.8 pp [-10.7, -5.3]; vs Pool-Free +0.3 pp [-1.5, +2.3]. metadata_error alone: vs NoRAG -4.6 pp [-6.6, -2.7]; vs Pool-Free +2.0 pp [+0.5, +3.7] (Pool-Free writes identifiers on 5% of entries). Skill-Full's remaining errors are search-record errors passed through: the model writes no metadata.
