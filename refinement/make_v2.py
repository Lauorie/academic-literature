#!/usr/bin/env python3
"""Apply SkillRefiner's lessons to seed_SKILL.md as targeted edits (skillrefine/CHANGES.md); writes v2/SKILL.md."""
from pathlib import Path

s = Path("seed_SKILL.md").read_text()


def rep(old: str, new: str) -> None:
    global s
    assert s.count(old) == 1, f"not unique/absent: {old[:70]!r}"
    s = s.replace(old, new)


# E1 (positive clusters, 7+5+4 traces): one probe search before the parallel round.
rep("""### Step 2 — Search the facets in parallel

The facet queries are independent, so launch them **concurrently**""",
"""### Step 2 — Search the facets in parallel

**Probe first.** Before the parallel round, run one small search on the topic itself (`--topn 3`) and read the result. It confirms the credentials work and that the backend understands the topic, for the price of five seconds. If it fails, the exit code tells you why (see below); if its three titles are off-topic, rephrase before you launch every facet with the same blind spot.

The facet queries are independent, so launch them **concurrently**""")

# E2 (positive cluster, 12 traces): the coverage audit as an explicit facet table.
rep("""Pool the results and ask the question that actually drives quality: **which facets came back thin, empty, or off-target?** Run **one** more round""",
"""Pool the results and ask the question that actually drives quality: **which facets came back thin, empty, or off-target?** Answer it in writing, as a short table in your notes — one row per facet: the facet, its two or three best hits by ledger key, and a verdict (*solid* / *thin* / *off-target*). Judge by reading titles, not by counting hits. Then run **one** more round""")

# E3 (positive clusters, 8+4+4 traces): a selection manifest after curation.
rep("""Keeping an un-cited paper in the ledger costs nothing — only cited keys reach the review — so drop for genuine irrelevance, not to tidy up.""",
"""Keeping an un-cited paper in the ledger costs nothing — only cited keys reach the review — so drop for genuine irrelevance, not to tidy up.

**Write the selection down.** Once curated, write `<output_dir>/manifest.tsv` with one row per selected paper: ledger key, the facet it serves, and its planned read depth (全文 / 摘要, per the Step 0 mode). Re-print the keys with `citation_ledger.py keys` to build it. The manifest is what Step 5 parses against, what reader subagents are dispatched from, and what you check against after a compaction, when your memory of the selection is gone but the file is not.""")

# E4 (negative cluster, 5 traces): truncated abstracts in abstract-only reading.
rep("""Go straight to Step 6 and read from abstracts. Note that a missing or `"N/A"` abstract then leaves that paper with no evidence — characterize it from title/venue only and say so; do not invent.""",
"""Go straight to Step 6 and read from abstracts. Note that a missing or `"N/A"` abstract then leaves that paper with no evidence — characterize it from title/venue only and say so; do not invent. **Check each selected abstract for truncation** — it ends in `…`, stops mid-sentence, or runs under ~60 words. Search snippets are often cut. Try once to get the full record (a `deep_search` on the exact title often returns a longer abstract; add it to the ledger like any search result). If it stays truncated, the paper can support a general statement but not a number or a comparative claim, and a selection made mostly of truncated snippets is a sign to cut the corpus to the papers you can actually characterize.""")

# E5 (negative clusters, 7+4+3+3 traces): lock a hierarchical outline and a claim map before drafting.
rep("""Refine them into the **3–6 themes** that will be your section headings. They must stay the topic's real sub-questions, not generic "foundational / recent / related" buckets. If after reading you still can't name them crisply, you haven't understood the literature yet — read more before writing.""",
"""Refine them into the **3–6 themes** that will be your section headings. They must stay the topic's real sub-questions, not generic "foundational / recent / related" buckets. If after reading you still can't name them crisply, you haven't understood the literature yet — read more before writing.

### Step 6b — Lock the outline and the claim map (before any prose)

The most common way this workflow fails is not a bad citation. It is a review whose evidence is sound and whose structure is flat: a dozen peer `##` sections, each a pile of papers, with no hierarchy to show how the field's questions nest. Judges and readers both see the heading tree first. So fix the structure in a file before you write a sentence:

Write `<output_dir>/outline.md`:
- Each **theme** is a `##` section. For a standard or deep review, each theme has **2–4 `###` subsections**, each a narrower question inside the theme ("Does efficiency survive scale-up?", not "Recent work"). A theme that cannot be split that way is probably two themes or half of one.
- Under each `###`, list the **claims** you will make, and for each claim the ledger keys that support it with their depth: `claim — wp:a3f21c (全文), wp:7b91de (摘要)`.
- A claim with no key is cut. A claim carried only by abstract-only papers is worded as a reported finding, not an established one. A `###` with fewer than two supporting papers is merged into a neighbour.
- Check the balance: if one or two papers back most of the claims, the review rests on them — either find support elsewhere in the ledger or say plainly that the evidence is concentrated.

Then draft from the outline, top to bottom. The outline is the argument; the prose fills it in.""")

# E6 (negative clusters, 10+3+3+2 traces): no top-level TL;DR / At a glance; Introduction first; hierarchy in the template.
rep("""```markdown
# Literature Review: [Topic]
*[Date] · [N] papers · [one-line note on scope and why this many]*

## TL;DR
2–4 sentences: the bottom line. What does the field actually know, what's the
biggest open tension, and where's the gap? A busy reader should get the thesis here.

## Introduction
Narrative prose: why the topic matters, how the field is organized, and the
sub-questions this review is built around. No per-paper content here.

## At a glance
A study-characteristics table — one row per paper, this is where the per-paper facts live.
Cite the paper in its own row; the study column is a short handle, not a citation. The
**Source** column records read-depth (全文 / 摘要) so the reader sees how thick each paper's evidence is:

| # | Study | Approach / model | Setting / data | Headline result | Source |
|---|-------|------------------|----------------|-----------------|--------|
| [wp:a3f21c] | AAV delivery | AAV vector | mouse, n=40 | 78% transduction | 全文 |
| [wp:7b91de] | LNP delivery | lipid nanoparticle | mouse, n=25 | 52% transduction | 摘要 |

## [Theme 1 — titled by a real sub-question of this topic]
Synthesis prose with inline [wp:key] citations. Make points; cite the papers that
back them; contrast where they conflict; weigh which evidence is strongest.
## [Theme 2 …]   ## [Theme 3 …]   (3–6 themes total)

## Critical assessment
How the field has evolved over time; what's well-established vs still contested;
methodological strengths and limits *across the body* (e.g. dominated by one group,
small samples, no clinical validation, no head-to-head comparisons); overall how
much to trust the evidence.

## Gaps & future directions
Concrete unexplored questions, grounded in what the papers did and didn't do —
not generic "more research is needed".

[no References section — `render` appends it from the ledger]
```""",
"""```markdown
# [Topic]: [a title that states the review's scope or thesis]
*[Date] · [N] papers · [one-line note on scope and why this many]*

## Introduction
Open with the bottom line in 2–4 sentences, set in bold: what the field actually
knows, its biggest open tension, and where the gap is. A busy reader gets the
thesis from this paragraph alone. Then narrative prose: why the topic matters, how
the field is organized, and the sub-questions this review is built around. No
per-paper content here.

## [Theme 1 — titled by a real sub-question of this topic]
One or two framing sentences, then the subsections.
### [1.1 — a narrower question inside the theme]
Synthesis prose with inline [wp:key] citations. Make points; cite the papers that
back them; contrast where they conflict; weigh which evidence is strongest.
### [1.2 …]
Where several papers measure the same thing, put the comparison in a small table
here — approach, setting, result, read depth — and argue from it in the prose.
## [Theme 2 …]   ### [2.1 …]   ### [2.2 …]   (3–6 themes, 2–4 subsections each)

## Critical assessment
How the field has evolved over time; what's well-established vs still contested;
methodological strengths and limits *across the body* (e.g. dominated by one group,
small samples, no clinical validation, no head-to-head comparisons); overall how
much to trust the evidence.

## Open problems and future directions
Concrete unexplored questions, grounded in what the papers did and didn't do —
not generic "more research is needed".

## Conclusion
A short paragraph: the thesis again, now earned by the sections above.

## Appendix: Study characteristics
A study-characteristics table — one row per paper, this is where the per-paper facts live.
Cite the paper in its own row; the study column is a short handle, not a citation. The
**Source** column records read-depth (全文 / 摘要) so the reader sees how thick each paper's evidence is:

| # | Study | Approach / model | Setting / data | Headline result | Source |
|---|-------|------------------|----------------|-----------------|--------|
| [wp:a3f21c] | AAV delivery | AAV vector | mouse, n=40 | 78% transduction | 全文 |
| [wp:7b91de] | LNP delivery | lipid nanoparticle | mouse, n=25 | 52% transduction | 摘要 |

[no References section — `render` appends it from the ledger]
```

**Why this order.** The review opens with the Introduction and its bold bottom line, not with a `TL;DR` heading, and the per-paper table sits in an appendix, not between the Introduction and the argument. Both used to be top-level sections at the front; outline judges read that as a report, not a survey, and marked it down whatever the prose was worth. The content is the same; it moved to where a survey reader expects it.""")

# E6b: the language paragraph mentions "the TL;DR".
rep("""So: prose, section headings, the TL;DR, and your analysis in the user's language;""",
"""So: prose, section headings, the opening summary, and your analysis in the user's language;""")

# E6c: deep-survey sentence after the template.
rep("""For a **deep survey**, give each theme room and add sub-themes as the structure demands.""",
"""For a **deep survey**, give each theme room: its `###` subsections from Step 6b, and a comparison table wherever several papers report on the same measure.""")

# E7 (negative clusters, 5+2+2 traces): quality bar on hierarchy, synthesis aids, citation spread.
rep("""- **Themes are the topic's real sub-questions**, not generic "foundational / recent / related" buckets.""",
"""- **Themes are the topic's real sub-questions**, not generic "foundational / recent / related" buckets.
- **The heading tree has depth.** A standard or deep review has 3–6 `##` themes, each split into `###` subsections; read the headings alone, top to bottom, and they should outline the field's argument. No `TL;DR` or `At a glance` heading at the front.
- **The argument has synthesis aids**: at least one comparison table inside a theme, beyond the appendix table.
- **Citations are spread**: no single paper carries a large share of the claims unless the review says why it must.""")

Path("v2/SKILL.md").write_text(s)
print(len(s), "bytes")
