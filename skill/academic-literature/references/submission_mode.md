# Submission-grade mode (投稿级深度模式)

Read this when the user wants a review meant for a journal or a conference survey track: "投稿级", "能投稿的综述",
"写一篇可以发表的综述", "journal-length review", "submission-ready survey", or when they pick this mode explicitly.
It changes Steps 0–8 of SKILL.md in the places listed below and adds Step 9. Everything else — the ledger, citing by
key, evidence files, `fill`, `render`, `check` — works exactly as in SKILL.md, and matters more here, because a
reviewer will check a 150-entry bibliography harder than a 40-entry one.

## What this mode can and cannot deliver

It delivers a complete, checkable draft at the scale of a published review: 100–200 cited papers, a reproducible
methods section, a taxonomy figure and a timeline, and per-theme comparison tables. It does not deliver a paper
someone can submit unchanged, for three reasons no amount of searching removes:

- **Accountability.** Journals require named authors who answer for every claim, and most require a disclosure of
  AI assistance. The author has to read the core papers and sign off.
- **Paywalls.** In many fields most full texts cannot be fetched. Claims that rest on abstracts are marked; an author
  with library access must read the papers behind the claims that carry the argument.
- **Perspective.** A survey earns its place by an expert's judgment of the field: which framing is right, what is
  overrated, what comes next. The draft proposes one; the author must own it or replace it.

So the mode ends with `handoff.md` (Step 9), which lists exactly what the author still has to do. Say this to the
user in one or two sentences when the run starts and again when you deliver; don't oversell the draft.

This mode is long: hours of wall time, hundreds of tool calls, and a large context. If the run is interactive,
confirm once (folded into the Step 0 question) that the user wants it rather than a standard deep review.

## Targets

| | standard deep review | submission-grade |
|---|---|---|
| cited papers | 15–60 | 100–200 (a narrow topic may justify ~80; say why) |
| themes / subsections | 3–6 / 2–4 each | 5–8 / 2–4 each, each subsection backed by >= 4 papers |
| body length | 5–8k words | 12–20k words |
| full-text reading | as the mode allows | the 30–40 core papers first (see Step 5) |
| figures | none required | taxonomy (Figure 1), timeline (Figure 2), comparison tables per theme |
| front and back matter | Introduction ... Conclusion | Abstract, Introduction with contributions and prior surveys, Methods, ..., Conclusion, appendix table |

## Step 0 — Scope, written down

Besides the reading mode (default: full text when available), fix the scope in `<output_dir>/scope.md`: the
question the review answers, the audience/venue type, the time window, and inclusion and exclusion criteria (study
types, languages, what counts as off-topic). A reviewer's first methodological question is "how did you decide what
to include?"; the answer has to exist before the search, not be reconstructed after it. In a non-interactive run,
derive the scope from the request and say what you assumed.

## Steps 1–3 — Search in rounds, logged, until it saturates

Name **6–10 facets**, and phrase each **two ways** (different vocabulary or angle), because one phrasing samples one
corner of the ranker.

Keep `<output_dir>/search_log.tsv` with one row per search call: `round  facet  tool  query  topn  returned  file`.
The Methods section is written from this file, so log as you go.

- **Round 1** — `quick_search`, every facet x phrasing, `--topn 25`, concurrently. Ingest.
- **Round 2** — `deep_search` on **every** facet (not only thin ones), `--topn 30`, in the background with
  `wait`, Bash timeout >= 300 s. Ingest.
- **Round 3** — targeted: for each facet, one query for *prior surveys/reviews* of it (you must cite and position
  against them), one for *benchmarks or datasets*, one for *the last two years*. Ingest.
- After each round, count how many new **on-topic** papers it added, and write the counts into the log;
  "saturation" is a claim the Methods section makes, so it needs the numbers.
- **Three rounds is the plan.** Run a fourth only if Round 3 still added more than ~10% new on-topic papers, and
  never a fifth. Test runs that searched for five rounds collected 1,000+ candidates for a 200-paper review and then
  ran short of time for the reading, which is where a survey's depth actually comes from. Searching should take
  roughly a quarter of the run.

## Step 4 — Select against the written criteria

Apply `scope.md`. Use a fixed vocabulary for `drop --reason` — `off-topic`, `out-of-window`, `duplicate-version`,
`non-scholarly`, `metadata-garbled` — because `survey_figures.py stats` tallies the reasons into the Methods section.

Add a `tier` column to `manifest.tsv`: **core** for the 30–40 papers the argument rests on (they back claims in two or
more subsections, they are foundational, or they are the strongest evidence on a contested point), **supporting**
for the rest.

**Choose the core with its full text in view.** Before you freeze the core, shortlist about 60 candidates and ask
where their full text can come from:

```bash
FT=~/.claude/skills/academic-literature/scripts/fulltext.py
python3 "$FT" locate --ledger "$LEDGER" --manifest <output_dir>/manifest.tsv --tier core > <output_dir>/fulltext_routes.tsv
```

Each key gets a route: `arxiv` (PDF on arxiv.org), `europepmc` (open-access copy in Europe PMC), `pdf_url` (a
publisher PDF link, which often refuses scripted downloads), or `none`. When two candidates would carry the same
claim, make the one with an open route core. Keep a `none` paper core only when it is irreplaceable — foundational,
or the only evidence for a point — and it goes on the handoff list. In paywalled fields a core chosen without
looking at routes ended with 13 of 40 papers read in full; aim for **at least 25 core papers read in full**, and
say in the Methods section how many you reached.

## Step 5 — Read the core first

Fetch every core paper by its route, centrally, before any reader starts:

- `europepmc` — no parsing queue: `python3 "$FT" epmc --pmcid PMC1234567 --out <output_dir>/fulltext/<key>.md`
  prints the `markdown_path`, like WisDoc does.
- `arxiv`, `pdf_url` — WisDoc, exactly as in SKILL.md Step 5: foreground, `WISDOC_POLL_TIMEOUT=520`, and the Bash
  tool's own timeout raised to ~550000 ms. In testing, the first core parse of a run was killed by the default
  two-minute Bash timeout and the agent spent the next hour building its own downloader; the timeout is the whole
  fix. A `pdf_url` that 403s falls back to the abstract.

Supporting papers may be read from abstracts. A core paper whose full text cannot be fetched stays core and goes on
the handoff list: the author must read it. Readers write evidence files exactly as in Step 6.

## Step 6b — Outline at scale

5–8 themes, 2–4 subsections each, each subsection with >= 4 supporting keys. Add to the outline a short **relation
to prior surveys**: which earlier reviews exist (found in Round 3), what each covers, and what this one adds. If you
cannot state what it adds, the review has no reason to exist, and the handoff must say so.

## Step 7 — Structure and figures

```markdown
# [Title]
## Abstract                      150–250 words: scope, method, main findings, open problems
## 1 Introduction                motivation; contributions (3–4 bullets); relation to prior surveys
## 2 Survey Methodology          sources, search rounds and dates, queries (summary; full log in the appendix
                                 or supplementary file), counts from `stats`, inclusion criteria, read depth
## 3 Taxonomy Overview           Figure 1 and a paragraph per branch; Figure 2 (timeline)
## 4..N [Themes]                 ### subsections; a comparison table in each theme
## N+1 Open Problems and Future Directions
## N+2 Conclusion
## Appendix: Study characteristics
```

**Numbers in Methods come from the tools, not from memory**:

```bash
F=~/.claude/skills/academic-literature/scripts/survey_figures.py
python3 "$F" stats --ledger "$LEDGER" --draft <output_dir>/literature.draft.md --evidence <output_dir>/evidence
```

It reports papers identified, dropped (by reason), retained, cited, cited per year, and read depth of the cited set.
Re-run it after the last edit to the draft and update the Methods numbers to match.

**Figures are drawn from the outline and the ledger**, so they cannot show a paper the review doesn't cite:

```bash
mkdir -p <output_dir>/figures
python3 "$F" taxonomy --outline <output_dir>/outline.md --title "[short topic]" --out <output_dir>/figures/taxonomy.png
python3 "$F" timeline --ledger "$LEDGER" --draft <output_dir>/literature.draft.md \
  --outline <output_dir>/outline.md --out <output_dir>/figures/timeline.png
```

**Heading levels carry the structure.** Themes are `##`, their subsections `###`. Don't write a subsection as
`## 4.1 ...`: the number looks hierarchical to you, but the taxonomy figure, outline judges and a reader's table of
contents all read the heading level, and see a flat list of forty sections.

**Length: 12–20k words.** Past ~20k the draft is usually restating per-paper detail that belongs in the theme
tables or the appendix table; move it there rather than adding prose. A 34k-word draft from a test run read as
an annotated bibliography in its later themes.

Embed the figures in the draft with captions that say what is counted:
`![Figure 1. Taxonomy of [topic]; numbers are the papers this review cites under each branch.](figures/taxonomy.png)`.
Redraw both after the outline or the citations change. If matplotlib is missing, the script exits 4 with an install
hint; try `python3 -m pip install --user matplotlib` once, and if that fails, deliver without figures and put them
on the handoff list.

**Write theme by theme.** A 15k-word draft does not fit in one pass of attention. Draft each theme from its part of
`outline.md` and its evidence files, then read the whole draft once for transitions and repetition. Keep the
synthesis in your own hands, as in standard mode; reader subagents supply notes, not prose.

## Step 8 — Check, as in SKILL.md

`fill`, `render`, `check`, `verify_citations.py`. At this scale expect more warnings; each still needs a decision.

## Step 9 — `handoff.md` for the author

Write `<output_dir>/handoff.md`. Every item points at a key, a section or a file, so the author can act on it:

1. **Core papers not read in full** — the count (`n of N core read in full`), then each one: key, title (from
   `keys`), its route from `fulltext_routes.tsv`, and which subsections rely on it.
2. **Claims resting only on abstracts** — from `outline.md`: claims whose keys are all 摘要.
3. **Accepted `check` warnings** — each with the reason you accepted it.
4. **Bibliography gaps** — entries still `[venue unavailable]` or `[unverified]`.
5. **Prior surveys and novelty** — the closest existing reviews and what this draft claims to add; the author must
   confirm that claim holds.
6. **Where expert judgment is needed** — the taxonomy's framing, the open-problems section, any place the evidence
   was thin or contested.
7. **Before submission** — check the target venue's policy on AI-assisted writing and on review articles; a
   disclosure sentence the author can adapt, e.g. "A literature search and first draft were produced with an AI
   agent (academic-literature skill); the authors read the cited works, verified all claims, and take full
   responsibility for the content."

## Output directory, in addition to the standard files

```
scope.md            scope and inclusion criteria (Step 0)
search_log.tsv      every search call, with counts per round (Steps 1–3)
manifest.tsv        selection with a tier column (Step 4)
fulltext_routes.tsv where each core paper's full text came from, or `none` (Step 4)
fulltext/           full texts fetched from Europe PMC (Step 5)
outline.md          hierarchical outline with claim map and relation to prior surveys (Step 6b)
figures/            taxonomy.png, timeline.png (Step 7)
handoff.md          what the author still has to do (Step 9)
```
