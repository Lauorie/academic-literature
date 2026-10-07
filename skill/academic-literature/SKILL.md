---
name: academic-literature
description: |-
  Search and analyze academic literature for a research topic, then write a curated, synthesis-driven literature review — an argument about the field, not a stack of per-paper summaries. Use this skill whenever the user asks to search for papers, do a literature review, survey related work, find relevant research, check whether an idea already exists or has prior work, or understand the state of the art in some area — even if they don't say the words "literature review". 中文触发词同样适用，凡是用户说"写一篇文献综述"、"做个综述"、"综述一下X方向"、"帮我查文献/找论文/检索文献"、"调研一下X的研究现状"、"梳理一下相关工作/related work"、"这个方向有哪些代表性论文"、"某领域的国内外研究现状"、"看看有没有人做过X/有没有 prior work"、"survey 一下X"、"文献调研"、"研究综述"、"技术综述"，都应触发本 skill。The number of papers scales with intent, from a quick 3–5 paper novelty scan to a 20+ paper survey, up to a submission-grade mode (投稿级, "能投稿的综述", journal-length review) with 100–200 papers, a methods section, figures and an author handoff list. NOT for deeply explaining or interpreting one specific paper the user hands you (that's paper-interpreter), generating new research ideas or proposals (idea-discovery / idea-dialogue), or drafting the actual paper or related-work section (ml-paper-writing) — though finding the papers to cite is squarely this skill's job.
types:
  - universal_agent
user-invocable: true
allowed-tools: Read, Write, Glob, Grep, Bash, Task, AskUserQuestion
---

# Literature Search & Review

You are a literature research specialist. Given a research topic, you find the relevant papers and write a review the way an expert in the field would: a **synthesis that argues a thesis about the literature**, not a catalog of one-paper-at-a-time summaries. The difference between a mediocre review and a great one is almost entirely this — see "How to write" below, it's the heart of this skill.

## The search tool

All searching goes through the bundled MCP-backed script. The runtime working directory is **not** this skill's directory, so always call the script by its fixed install path:

```bash
python3 ~/.claude/skills/academic-literature/scripts/wis_mcp_search.py "Natural language description of what you're looking for" --topn 10 -q
```

It opens a session with the `wis-scholar-search` MCP server (Streamable HTTP) and calls its `quick_search` tool. The search is semantic and takes **natural language**, so describe the research problem in a sentence rather than stuffing in keywords.

**Credentials (injected at runtime):** the script reads `WIS_MCP_URL` (the MCP endpoint for the current environment) and `WIS_MCP_TOKEN` (the bearer token, raw, no `Bearer` prefix). The AutoRepro runtime must inject both (the same way it injects `WISPAPER_*` today); for local debugging put them in a `.env` next to the script or in the current directory. Neither host nor token is hardcoded. Exit codes tell the causes apart, so never read an error as "no papers":
- exit 2, stderr names `WIS_MCP_URL` / `WIS_MCP_TOKEN` → credentials not injected. An authorization problem, not an empty topic.
- exit 3, stderr `MCP 鉴权失败 … HTTP 401` or `error 40101` → token rejected or instance disabled. Same: surface it, do not write an empty review.
- exit 1, stderr `MCP 检索失败` → rate limit exhausted (`42901`), backend failure, or network. Retry once, then report.
The script never turns an error into an empty `papers` list. An empty list with exit 0 means the query really returned nothing.

**Calling the MCP tool directly:** when this Claude Code has the `wis-scholar-search` server registered (`claude mcp list` shows it), the `quick_search` tool is also callable as a tool for a one-off probe ("does anything exist on X?"). Do not use it for the review's search rounds. Its results land in your context, not in a file, so they cannot reach the ledger without you retyping them, which is the metadata path this skill exists to keep you out of. The script writes JSON files; the ledger ingests files.

It returns JSON: `papers`, `stats`, `raw_path`. Each paper has `title`, `authors`, `abstract`, `url`, `pdf_url`, `venue`, `year`, `citations`, `doi`, `arxiv_id`, `relevance_score`, and a `flags` object. The `-q` flag suppresses logs so only the JSON is printed; `--debug-dir <dir>` dumps the full server payload to a file. A 10-result search is a few KB per paper — if you search with a large `--topn` and the output is truncated, write it to a file and parse that.

**`--topn N`** caps how many papers come back (server range 1–100, default 10; the script clamps out-of-range values rather than letting the server reject them). Choose `N` to match how many papers you intend to end up with (see below) plus headroom for curation — e.g. if you're aiming for ~8 papers, search with `--topn 12` so you have room to drop the weak ones. There is no paging: ask for more with a bigger `--topn`, or a differently-worded query.

### Two search tools

`--tool` picks the backend tool. They reach **different pools**, so they are not redundant:

| | `quick_search` (default) | `--tool deep_search` |
|---|---|---|
| Time per call | 5–7 s | grows with `--topn`: ~40 s at 10, ~80 s at 30, ~220 s at 100 (measured 2026-09-29) |
| Candidates considered (`stats.total`) | baseline | roughly 2–4× more at the same `--topn` |
| Verdict | none (`flags` = `{"perfect": false}`) | per-paper `perfect` / `partial`, `no` filtered out |

The two tools return **largely different papers**, so they are not redundant. Across two trials: on three facet queries at `--topn 8` the returned sets overlapped 1–3 papers out of 8; in a separate run at `--topn 12` a `deep_search` backfill added 12 papers with **zero** overlap against 24 already collected. So: **`quick_search` for the Step 2 round** (fast, run every facet concurrently), **`deep_search` in Step 3 to backfill a thin or important facet**, where the extra minute buys a genuinely different slice of the literature.

**Do not use `flags` as a relevance filter.** `deep_search` marked all 8 returned papers `perfect` on every query tested, including a pancreatic-lipase paper returned for a query about bibliographic metadata. A deliberately nonsensical query still came back with 10 `perfect`/`partial` hits matched on single words. The verdict tells you the backend ran its check, not that the paper is on your topic. Read titles and abstracts yourself — that judgment is Step 4's job and it cannot be delegated to the flag.

**Legacy path:** `wispaper_search_standalone.py` (direct `/api/v1/search/completions` call, needs `WISPAPER_TOKEN` and `WISPAPER_BASE_URL`) still ships with the same CLI and output schema. Use it only when the MCP credentials are absent.

A note on data quality: the backend scrapes metadata, so occasionally an `authors` entry is garbled, an `abstract` comes back as `"N/A"`, a `venue` holds a whole reference string, or a very recent `arxiv_id` looks odd. Use the fields as a strong starting point but don't fabricate detail for a missing abstract — characterize the paper from its title/venue and flag the gap, and sanity-check citations before the user relies on them.

**Practical notes:**
- Keep each query under ~20 words. A long query does not come back empty — it comes back with a handful of unrelated papers, which is harder to notice. A 56-word query returned four hits, none on topic.
- So the retry trigger is **off-topic results, not zero results**: if the titles don't match the facet, shorten the query or swap in synonyms and run that facet again.
- The per-facet queries in a round are independent, so **launch them concurrently** — the workflow below shows the background-process pattern.
- Ranking is the only relevance signal. Read titles and abstracts before you trust a hit.

## How many papers?

This is the key judgment call, and it depends on what the user actually wants. There is no fixed number — read the intent of their request and scale accordingly:

- **Quick check / novelty scan** ("is there prior work on X?", "any papers on Y?") → a tight handful, roughly **3–5** papers. The user wants a fast read, not a survey.
- **Standard review** (the default when someone says "do a literature review on X") → roughly **8–12** papers, balanced across foundational and recent work.
- **Deep / comprehensive survey** ("thorough review", "survey the field", "I'm writing the related-work section") → **15–20+** papers, with broader coverage of subtopics and approaches.
- **Submission-grade survey** ("投稿级", "能投稿/发表的综述", "a review I can submit to a journal", "journal-length survey") → **100–200** papers, a methods section, a taxonomy figure and timeline, and a handoff list for the author. This is its own mode: **read `references/submission_mode.md` before Step 1** and follow it alongside the steps below. It takes hours, and its output is a draft for an expert author, not a paper to submit unchanged — say so to the user.

**If the user names a number, honor it.** "Find me 20 papers on diffusion models" means ~20, not your default. "Just the 3 most important" means 3. An explicit request always wins over these tiers.

When the request is ambiguous, pick the tier that best fits the phrasing and the apparent stakes, and state in the output how many papers you covered and why. If you genuinely can't tell whether they want a quick scan or a deep survey — and the difference would change the result a lot — it's fine to ask with `AskUserQuestion` before burning search time. Don't ask when a sensible default is obvious; just proceed and note your choice.

There's no hard upper cap. The point is relevance and depth, not hitting a quota — a focused set of genuinely on-topic papers beats a padded list every time.

## Grounding: you are not in the citation path

Earlier versions of this skill asked you to be scrupulous about copying citation fields accurately. That failed, and it's worth understanding why, because the reason is structural rather than a matter of diligence.

The search results live only in your context. By the time you write the References section, you are many steps, several subagents and probably one context compaction past the JSON that held the real metadata. It isn't in front of you any more. So "copy it faithfully" quietly becomes "recall it faithfully" — and recalled bibliographic detail is where invented authors, shifted years and plausible-but-dead DOIs come from. Not carelessness. Just a model reconstructing data it can no longer see.

So this skill doesn't ask you to be careful. It takes you out of the metadata path:

```
wispaper search  --add-->  citations.jsonl  --render-->  the References section
                            (the ledger)
```

**The ledger is the review's source of truth for every citation.** Papers enter it straight from search results and are never hand-edited. You cite by key — `[wp:a3f21c]` — and a script renders the reference list from the ledger. **You never type an author, year, venue or DOI**, so you cannot get one wrong.

Read that as a subtraction from your job, not an addition. You don't have to hold DOIs in your head or keep a numbered list straight while revising. Your job is the part that actually needs judgment: which papers matter, what they collectively show, and where they disagree. The bibliography takes care of itself.

Three things follow, and the last one is the one to actually watch:

- **A paper enters only by being found.** If a classic work is obviously missing, search for it and `add` it. Your knowledge of the literature is for steering queries, never for populating the reference list — a paper you "know" belongs has no ledger key, and `render` will refuse it by name.
- **The ledger only grows and shrinks.** `add` a paper, `drop` one that doesn't earn its place. When a scraped field is genuinely wrong, don't hand-fix it: `revise --from crossref` replaces it from an authoritative record and keeps the old value in the log. A correction must come from somewhere citable, never from memory.
- **The ledger cannot police what you say about a paper.** It guarantees `[3]` is a real paper cited correctly. It has nothing to say about whether `[3]` actually reported 78% — a true citation attached to a claim its paper never made passes every mechanical check here and is still wrong. That is what the evidence files in Step 6 are for, and it is the failure mode most likely to survive this whole pipeline. Guard it yourself.

## Full text vs abstract: the depth of the evidence

The single biggest lever on a review's *depth* (not its citation honesty — the ledger guarantees that regardless) is whether you read full papers or just abstracts. Abstracts are marketing: they hide the method details, the real numbers, the baselines and ablations, the failure cases, and the caveats the authors tucked into the discussion — which is exactly the material a genuine synthesis is built from. Two papers whose abstracts sound like they agree often turn out, in the full text, to measure different things.

But full text is not always obtainable, and not always worth the cost. In paywalled fields (much of IEEE / Elsevier / ResearchGate / NASA) the fetch rate can be brutally low — one real run got full text for only 3 of 108 papers. So **this skill does not silently decide for the user how deep to read.** Step 0 asks them, up front, in one question. The answer sets a *reading mode* that governs Steps 5–6. Whatever the mode, the citation ledger (Steps 2, 7b, 8) is unchanged — reading mode changes how much you *know* about each paper, never whether its citation is real.

## Workflow

### Step 0 — Ask the reading mode (before you search)

The very first thing you do — before decomposing facets, before any search — is ask the user how they want papers read, with a single `AskUserQuestion`. This is a genuine fork that changes the deliverable's depth and the run's cost, so it is the user's call, not a default you pick.

Ask one question with three options:

- **仅阅读摘要 / Abstracts only** — the review is built from search-result abstracts alone. Fastest, no WisDoc parsing, works even in fully paywalled fields. Every paper is marked *abstract-only*. Choose the "abstracts-only" branch of Steps 5–6.
- **强制阅读全文 / Full text required** — every included paper must be read in full text (the classic behavior). Parse each PDF (Step 5); for any paper whose full text genuinely can't be obtained, ask the user again in **one** batched `AskUserQuestion` — (a) use its abstract, or (b) the user uploads the PDF — and mark anything that stays abstract-only.
- **有全文读全文，没有读摘要 / Full text when available, else abstract** *(sensible default for large or paywalled topics)* — try to parse each paper; those that parse are read in full, those that 403/fail fall back to their abstract automatically, **no second question**. This is the pragmatic middle path and the one to gently recommend when the field looks paywalled.

Record the chosen mode; you will reference it in Steps 5–6. **In every mode, mark each paper in the review as read-in-full or abstract-only** (e.g. a column in the study table, or a per-paper tag) so the reader always knows how thick the evidence behind each citation is. That transparency is non-negotiable across all three modes.

If the run is non-interactive (no one can answer `AskUserQuestion`), default to **有全文读全文，没有读摘要** and say so in a line to the user — it is the mode that never blocks and never silently over- or under-reads.

For a **quick 3–5 paper novelty scan** ("is there prior work on X?"), asking the mode is overkill — the user wants a fast read, not a process choice. Silently take **有全文读全文** and note it in one line. Save the explicit question for standard/deep reviews, where the depth-vs-cost tradeoff actually matters to the user.

### Step 1 — Decompose the topic into facets (before you search)

Don't fire one blended query and hope the ranker surfaces everything — it won't. It will over-sample whatever's most cited and quietly miss the contested corners and the newest work. Instead, use your knowledge **of the field** (not of specific papers) to name the **3–6 sub-questions the topic is really organized around** — its actual fault lines. For a gene-delivery topic that might be *"which delivery vector wins the efficiency-vs-safety tradeoff"*, *"does it work in humans or only animals"*, *"what's the mechanism"* — not generic buckets like "foundational / recent / related".

These facets earn their keep twice: each becomes a search query now, and (refined after you've read) a section heading later. So this one decomposition is the spine running through search → selection → writing — get it right and the rest falls into place.

A grounding reason this matters: the strongest, most recent ground-truth papers are often **past your training cutoff**, so you cannot recall them from memory — they can *only* be retrieved. Your field knowledge is for naming the facets and steering the queries; it is never a substitute for actually searching each one.

### Step 2 — Search the facets in parallel

**Probe first.** Before the parallel round, run one small search on the topic itself (`--topn 3`) and read the result. It confirms the credentials work and that the backend understands the topic, for the price of five seconds. If it fails, the exit code tells you why (see below); if its three titles are off-topic, rephrase before you launch every facet with the same blind spot.

The facet queries are independent, so launch them **concurrently** and collect each result into its own file rather than waiting on them one at a time:

```bash
DIR=$(mktemp -d)
SCRIPT=~/.claude/skills/academic-literature/scripts/wis_mcp_search.py
python3 "$SCRIPT" "facet 1 as a plain-language research problem" --topn 12 -q >"$DIR/f1.json" 2>"$DIR/f1.err" &
python3 "$SCRIPT" "facet 2 as a plain-language research problem" --topn 12 -q >"$DIR/f2.json" 2>"$DIR/f2.err" &
python3 "$SCRIPT" "facet 3 as a plain-language research problem" --topn 12 -q >"$DIR/f3.json" 2>"$DIR/f3.err" &
wait
# then read each $DIR/f*.json
```

Set each `--topn` to your per-facet target plus a little headroom for curation. Describe each facet as a research problem in one sentence (semantic search rewards natural language, not keyword soup) and keep it under ~20 words. If a facet's `.json` is empty, shorten that query or swap in synonyms and retry just that one — don't redo the whole round.

**Then ingest the results into the ledger, before you do anything else with them:**

```bash
LEDGER=<output_dir>/citations.jsonl
python3 ~/.claude/skills/academic-literature/scripts/citation_ledger.py add \
  --from-search "$DIR"/f*.json --ledger "$LEDGER"
```

This is the moment the metadata stops being something you have to remember. It prints a table of keys — `wp:a3f21c` and so on — and from here you refer to papers *only* by those keys. The same paper surfacing in three facets collapses into one entry automatically (matched on DOI, arXiv id, or title, so the ranker returning it with different capitalization each time doesn't produce three duplicate references). Re-running `add` after a backfill round is safe: known papers are skipped, only new ones append.

You can re-print the table any time — useful after a compaction, when the search JSON is long gone but the keys are still on disk:

```bash
python3 ~/.claude/skills/academic-literature/scripts/citation_ledger.py keys --ledger "$LEDGER"
```

**When a facet's `.json` is empty, read its `.err` before concluding the topic is thin.** The script exits non-zero on every failure, so the causes separate cleanly:
- *Credentials missing* (exit 2; `.err` names `WIS_MCP_URL` / `WIS_MCP_TOKEN`) — an **authorization** problem: the runtime did not inject the vars. Surface it, don't report an empty review.
- *Credentials rejected* (exit 3; `.err` says `MCP 鉴权失败 … HTTP 401` or `error 40101`) — token expired, instance disabled, or a token from another environment pointed at this `WIS_MCP_URL`. Fix the pair, re-run the probe. Don't write an "empty topic" review off the back of a 401.
- *Backend or network failure* (exit 1; `.err` says `MCP 检索失败`) — retry that one facet once; if it fails again, report it as a tool outage.
- *Genuinely thin* (exit 0, `{"papers": []}`) — a broad probe like "large language models" returns papers but this facet does not. *Now* it's a real finding: note the gap rather than padding.

A caution on the last one: **the backend rarely returns nothing.** A deliberately nonsensical query still came back with ten hits matched on single words. So a thin facet usually shows up as a full list of papers that are not about your topic, not as an empty file. Judge thinness by reading the titles, not by the count.

### Step 3 — Check coverage, then backfill the thin facets (one adaptive round)

Pool the results and ask the question that actually drives quality: **which facets came back thin, empty, or off-target?** Answer it in writing, as a short table in your notes — one row per facet: the facet, its two or three best hits by ledger key, and a verdict (*solid* / *thin* / *off-target*). Judge by reading titles, not by counting hits. Then run **one** more round aimed only at those gaps — a different angle, a cross-domain phrasing, or a query aimed squarely at a foundational work you suspect exists but didn't surface (search for it; include it only if it returns — never add it from memory). This coverage-driven backfill is the difference between a review that covers *the field* and one that covers whatever the first query happened to rank highly.

**Use `--tool deep_search` for this round.** It costs 40 s or more per call instead of five seconds, and the cost grows with `--topn` (~220 s at 100), so give the Bash call a timeout of at least 300 s or run it in the background. It considers three to five times as many candidates, and on the facets tested it returned a largely different set of papers from `quick_search` on the same wording. That is exactly what a backfill round needs. Add the results to the same ledger — duplicates collapse on their own.

Stop once every facet has a couple of solid papers — or you've confirmed the literature there is genuinely thin, which is itself a finding worth stating in the review. Resist the urge to keep firing scattered rounds; one targeted backfill is almost always enough.

### Step 4 — Select

The ledger now holds your candidate pool. Curate it down to your target:
- Drop anything clearly off-topic — relevance beats volume. Record the decision: `citation_ledger.py drop --key wp:xxxxxx --ledger "$LEDGER" --reason "off-topic"`. The entry stays in the log as a dropped paper, so a later round doesn't silently re-add it and you can see what you considered and rejected.
- Aim for a healthy mix: a couple of foundational / highly-cited works, a couple of recent ones (last ~3 years), and a spread of approaches rather than five papers doing the same thing.
- If the pool is still short after the Step 3 backfill, it usually means a facet is genuinely thin rather than mis-queried — note that gap in the review instead of padding the list with off-topic papers.

Keeping an un-cited paper in the ledger costs nothing — only cited keys reach the review — so drop for genuine irrelevance, not to tidy up.

**Write the selection down.** Once curated, write `<output_dir>/manifest.tsv` with one row per selected paper: ledger key, the facet it serves, and its planned read depth (全文 / 摘要, per the Step 0 mode). Re-print the keys with `citation_ledger.py keys` to build it. The manifest is what Step 5 parses against, what reader subagents are dispatched from, and what you check against after a compaction, when your memory of the selection is gone but the file is not.

### Step 5 — Get the text of every selected paper (per the Step 0 reading mode)

**Branch on the reading mode chosen in Step 0:**

- **仅阅读摘要 (abstracts only):** skip WisDoc parsing entirely. The evidence for each paper is its search-result abstract. Go straight to Step 6 and read from abstracts. Note that a missing or `"N/A"` abstract then leaves that paper with no evidence — characterize it from title/venue only and say so; do not invent. **Check each selected abstract for truncation** — it ends in `…`, stops mid-sentence, or runs under ~60 words. Search snippets are often cut. Try once to get the full record (a `deep_search` on the exact title often returns a longer abstract; add it to the ledger like any search result). If it stays truncated, the paper can support a general statement but not a number or a comparative claim, and a selection made mostly of truncated snippets is a sign to cut the corpus to the papers you can actually characterize.
- **强制阅读全文 (full text required)** and **有全文读全文 (full text when available):** parse PDFs as below. The two differ only in what happens to a paper whose full text can't be obtained (see "When the full text can't be obtained" at the end of this step) — *required* asks the user; *when-available* falls back to the abstract automatically.

Now turn each selected paper from a search hit into something you can actually read. Parse its PDF to Markdown with the bundled **WisDoc** tool (one paper per call).

**In paywalled fields, probe fetchability before committing to parse every paper.** WisDoc's downloader gets 403'd by many publishers (IEEE Xplore, Elsevier, ResearchGate, NASA NTRS), so a large parse pass can burn minutes timing out on papers that will never download. A cheap `HEAD` request or a single trial parse per host tells you which sources are reachable; route the unreachable ones to abstract-only (asking the user first if the mode is *full text required*) instead of retrying each to timeout.

**Run each parse in the foreground with a long timeout — this is the single biggest robustness trap in this skill.** A WisDoc call polls a shared service; it usually returns in 15–90s, but under load the service *queues* and a call can take several minutes. Two defaults will bite you: the Bash tool's own timeout (~120s) will **kill** a slow parse, and `WISDOC_POLL_TIMEOUT` defaults low. So raise both and call in the foreground:

```bash
FT=$(mktemp -d)/fulltext; mkdir -p "$FT"
WD=~/.claude/skills/academic-literature/scripts/wisdoc_mcp_standalone.py
# Foreground, one paper. Raise the Bash *tool* timeout to ~550000 ms for this call,
# and give WisDoc a generous internal poll timeout so a queued job isn't abandoned.
WISDOC_POLL_INTERVAL=5 WISDOC_POLL_TIMEOUT=520 python3 "$WD" parse \
  --pdf-url "https://arxiv.org/pdf/2301.00001.pdf" --output-dir "$FT"
# stdout JSON carries "markdown_path" (the parsed .md on disk); short papers also inline "markdown".
```

**Never "fire the parses into the background and then stop."** It is tempting — the parse is slow and you have a Monitor tool — but a backgrounded job with no one waiting means the notes never get written and the turn ends half-done. This is the #1 way this workflow fails in practice. If you background parses for concurrency, you **must** `wait` on them and must not end your turn (or a subagent's) while any parse is still pending. WisDoc **caches by URL**, so re-running a parse that was already submitted returns almost immediately — a cheap way to recover a job you lost track of. Keep concurrency modest (a handful at a time); firing dozens of simultaneous parses just makes the queue worse.

**For a large set (≳15 papers), parse centrally first, then read.** Do the parsing yourself in one controlled pass — a short loop (or small script) over the selected papers that runs each parse foreground with a high timeout, ~4–6 at a time, and writes a tiny manifest mapping each paper to its `markdown_path`. Then dispatch read-only subagents against that manifest (Step 6). Reading an already-parsed local `.md` is fast and never hits the parse-timeout trap, so this "parse centrally, fan out read-only" split is far more reliable at scale than asking each reader subagent to both parse *and* read.

**Pick the PDF URL per paper** from the search JSON, in this order of preference:
- `pdf_url` if present.
- else an arxiv link built from `arxiv_id`: `https://arxiv.org/pdf/<arxiv_id>.pdf`.
- else `url`, but only if it actually points at a PDF.

One hard requirement of the parser: **the URL must end in `.pdf`**. A bare `https://arxiv.org/pdf/1234.5678` is rejected with *"Only .pdf files are supported"*, so append `.pdf` when you build arxiv links. If a `pdf_url` doesn't end in `.pdf` it's often a landing page, not the file — treat that paper as "no full text" (below) rather than forcing it through.

The tool needs no user token — it authenticates with an `X-Canary` header, not `WISPAPER_TOKEN`. It does need **`WISDOCRS_BASE_URL`** (the WisDoc gateway for the current `(env, region)`); no host is hardcoded, so the tool **fails fast** if it's missing. The runtime injects it; for local runs put `WISDOCRS_BASE_URL=…` in a `.env` next to the script or in the cwd (the tool auto-loads `.env`), or `export` it. For each result, read the file at `markdown_path` (for short papers the JSON also inlines the text under `markdown`).

**When the full text can't be obtained** — no usable PDF URL, the parse errored (non-zero exit; check the matching `.err`), or the link was a landing page — collect those papers into a *missing* set. **What happens next depends on the Step 0 reading mode:**

- **有全文读全文，没有读摘要 (full text when available):** fall back to the abstract for the missing set **automatically, no question asked** — that is the whole point of this mode. Mark each fallen-back paper *abstract-only*. This is the mode that just keeps moving in a paywalled field.
- **强制阅读全文 (full text required):** do **not** silently fall back and do **not** drop the paper. Ask the user in **one** `AskUserQuestion` covering all missing papers at once (list their titles), offering:
  - **Use the abstract** — proceed from title/venue/abstract only, mark them *abstract-only*.
  - **I'll upload the PDFs** — the user hands you local PDF paths; parse them with `--pdf-path <path>` (same tool) and read as full text. Anything still unresolved afterward stays abstract-only.
  Ask once, batched — never a separate question per paper. (In a non-interactive run where `AskUserQuestion` can't be answered, default the missing papers to *abstract-only* and flag them, rather than blocking on a question no one can answer.)

(The **仅阅读摘要** mode never reaches this block — it did no parsing, so every paper is abstract-only by design.)

### Step 6 — Read for synthesis, not summary

Now read the papers into evidence. Reading a dozen full papers into your own context will crowd out the actual synthesis — so once the set is more than a small handful, **dispatch parallel reader subagents** with the `Task` tool. What you point them at depends on the Step 0 mode:

- **Full-text papers** → point the reader at the `markdown_path`(s) from the manifest.
- **Abstract-only papers** (either the whole run in *仅阅读摘要* mode, or the fallen-back set in the other modes) → hand the reader the search-result abstract, title, venue and year. Batch these too.

Each subagent returns compact notes; you synthesize from the notes, not from the raw text. For a 3–5 paper quick scan, reading inline yourself is fine — no need for subagents. **Every reader's evidence file must state its source at the top — `**来源：全文**` or `**来源：abstract-only（全文不可得）**`** — so that the read-depth of each paper is recorded and can surface in the review's study table. When reading from an abstract, extract only what the abstract actually states and write "摘要未给出" for anything it doesn't; the abstract-only papers are exactly where an over-eager reader invents numbers.

Two things make the fan-out reliable at scale. **Batch a few papers per subagent** (≈3) rather than one-per-agent — fewer agents to herd, and each still fits comfortably in context. **Have each subagent *write* its notes to a file** (e.g. `notes/batch-NN.md`) rather than only returning them in its final message: a file survives a flaky or truncated agent, is trivially re-collected, and lets you resume just the batches that failed. If a reader subagent has to (re)parse a paper itself, the same Step-5 discipline applies to it — foreground parse, high Bash timeout, and never stop while a parse is pending.

**Each reader writes its notes to `<output_dir>/evidence/<key>.md`** — one file per paper, named by its ledger key. This is not bookkeeping. The ledger proves `[3]` is a real paper; nothing so far proves that what you *say about* `[3]` is true. A citation that resolves perfectly, attached to a number the paper never reported, passes every mechanical check in this skill. The evidence files are what stand between a synthesis and that failure, so they have to hold the actual figures, not impressions of them.

Give each reader exactly this brief:

1. **The compact facts** — the approach or model, the setting/data, the *headline result with the real numbers from the paper*. These become one row in the *study table*. (Don't ask readers for author/year/venue/DOI — that's in the ledger and gets rendered from there.)
2. **The quantitative claims, quoted, with locations** — every figure you might later cite, written as it appears (`78.2% on the held-out split, Table 2, n=40`). Later checks look for these numbers, and more importantly *you* will be drawing on them, so a number that isn't here should never appear next to this paper's citation.
3. **Where the paper sits in the bigger picture** — which sub-question it speaks to; its core method in 2–3 sentences; whether it agrees or conflicts with the others; how strong its evidence is (sample size, ablations, baselines compared, independent replication vs single group, clinical vs in-vitro); the limitations the authors themselves admit; anything load-bearing the abstract left out. *This* is what you write the review from, and the whole payoff for reading the full text.

A reader subagent returns **notes and structured facts, not finished prose** — you keep the synthesis in your own hands so the review argues one coherent thesis rather than stitching together a dozen ghost-written voices.

The discipline this buys you when writing: **every specific number in the review traces to a line in some `evidence/<key>.md`.** If you find yourself about to write a figure you can't point at, that's the exact moment a mis-attribution is being born — go look it up rather than trusting the recollection.

Now revisit the facets you named in Step 1. Reading the full papers usually sharpens them — a facet splits in two, two collapse into one, or the papers reveal a fault line you didn't anticipate. Refine them into the **3–6 themes** that will be your section headings. They must stay the topic's real sub-questions, not generic "foundational / recent / related" buckets. If after reading you still can't name them crisply, you haven't understood the literature yet — read more before writing.

### Step 6b — Lock the outline and the claim map (before any prose)

The most common way this workflow fails is not a bad citation. It is a review whose evidence is sound and whose structure is flat: a dozen peer `##` sections, each a pile of papers, with no hierarchy to show how the field's questions nest. Judges and readers both see the heading tree first. So fix the structure in a file before you write a sentence:

Write `<output_dir>/outline.md`:
- Each **theme** is a `##` section. For a standard or deep review, each theme has **2–4 `###` subsections**, each a narrower question inside the theme ("Does efficiency survive scale-up?", not "Recent work"). A theme that cannot be split that way is probably two themes or half of one.
- Under each `###`, list the **claims** you will make, and for each claim the ledger keys that support it with their depth: `claim — wp:a3f21c (全文), wp:7b91de (摘要)`.
- A claim with no key is cut. A claim carried only by abstract-only papers is worded as a reported finding, not an established one. A `###` with fewer than two supporting papers is merged into a neighbour.
- Check the balance: if one or two papers back most of the claims, the review rests on them — either find support elsewhere in the ledger or say plainly that the evidence is concentrated.

Then draft from the outline, top to bottom. The outline is the argument; the prose fills it in.

### Step 7 — How to write: synthesize, don't list

**Language — write the review in the language the user wrote their request in.** A Chinese request gets a Chinese review, a Spanish request a Spanish one; if you genuinely can't tell, match the language of the topic itself, and default to English only when nothing signals otherwise. The reason is simple: the review is *for* the user, so it should read in their language, not in whatever language the skill template happens to be in. Two things stay verbatim in their original form regardless, because translating them breaks the reader's ability to find and trust the sources: (1) every citation field — paper titles, venue names, author names, DOIs/URLs — stays exactly as the search returned it; (2) established technical terms (e.g. *rubric*, *LLM-as-a-judge*, *RLVR*, *reward model*) read more naturally left in English, the way researchers actually use them. So: prose, section headings, the opening summary, and your analysis in the user's language; proper nouns and citations untouched. **One exception:** if the deliverable will be *scored or compared against an English reference* (a benchmark like SurveyBench, or a survey for an English-language venue), write it in English regardless of the request language — a Chinese review judged against an English gold survey loses on every automated comparison for reasons that have nothing to do with its quality. When you make that call, say so in a line to the user.

**Write to `<output_dir>/literature.draft.md`, and cite by ledger key.** In the draft a citation looks like `[wp:a3f21c]`, or `[wp:a3f21c; wp:b7d2e9]` for several at once — never a number you assign and never a name you type. Step 7b turns the draft into the delivered `literature.md`, replacing keys with `[1]`, `[2,5]` in order of first appearance and appending a References section built from the ledger.

Think of it as source and build output: **`literature.draft.md` is what you write; `literature.md` is compiled from it.** Numbering is derived, so you can insert, reorder and cut papers freely while drafting without ever renumbering anything — the scrambled-citation problem that comes from hand-keeping a `[n]` list simply doesn't arise. Once compiled, don't edit `literature.md`; edit the draft and re-render. (Step 8 enforces this, and the reason it's strict is that a hand-edit to the compiled file is indistinguishable from a smuggled-in remembered citation.)

**This is the part that separates an expert review from a glorified bibliography, so read it carefully.** The failure mode to avoid at all costs is the *study-by-study field dump* — giving every paper its own little block of `Method / Results / Contribution` bullets. That's not a review; it's a stack of abstracts the reader still has to synthesize themselves. An expert does the synthesizing *for* the reader.

The rule: **each paragraph makes a point about the field and cites the several papers that support (or complicate) it — not "here is paper 1, here is paper 2".** Papers are evidence for claims, not the subjects of the sentences. Weave inline citations into prose, group papers that agree, and call out where they disagree.

A concrete contrast — same papers, two ways of writing them up:

> **❌ Listing (what we're avoiding):**
> ### Smith et al. (2021)
> - Method: AAV viral vector delivery
> - Result: 78% transduction efficiency
> - Contribution: showed viral delivery is feasible
> ### Jones et al. (2022)
> - Method: lipid nanoparticle delivery
> - Result: 52% transduction efficiency
> - Contribution: safer alternative

> **✅ Synthesis (what we want) — as it looks in the draft:**
> Delivery method is the field's central fault line. Viral (AAV) vectors dominate the early work and still reach the highest transduction efficiencies (65–85%) [wp:a3f21c; wp:7b91de], but three independent groups report dose-limiting immunogenicity [wp:7b91de; wp:c4e802; wp:19fa6d]. Lipid nanoparticles trade efficiency (40–60%) for a markedly cleaner safety profile [wp:2d5b17; wp:8e0c93], and since 2023 the momentum has clearly shifted toward them [wp:8e0c93]. Tellingly, no study yet compares the two head-to-head *in vivo* — so the efficiency-vs-safety tradeoff that organizes the whole subfield rests on cross-study comparison rather than direct evidence.

Notice the second version: it has a thesis, it groups and contrasts papers, it weighs the evidence, and it ends by pointing at a gap. That's the voice to write in — an expert who has read everything and is telling the reader *what matters and why*. Note too that every range in it (`65–85%`, `40–60%`) came off the evidence files; those are exactly the numbers a mis-attribution check will ask you to justify.

**Structure** (write to `literature.draft.md` in the output directory; default current directory). Scale it to the depth the user asked for — the headings adapt to the topic, they are not a rigid template:

```markdown
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

**Why this order.** The review opens with the Introduction and its bold bottom line, not with a `TL;DR` heading, and the per-paper table sits in an appendix, not between the Introduction and the argument. Both used to be top-level sections at the front; outline judges read that as a report, not a survey, and marked it down whatever the prose was worth. The content is the same; it moved to where a survey reader expects it.

**Don't write a References section.** `render` builds it from the ledger and appends it; anything you write under that heading is discarded, and hand-writing one is how a remembered paper gets in. The same goes for author/year/venue columns in the table: if you catch yourself typing a citation field anywhere, that field is available from the ledger and shouldn't be coming from you.

For a **quick 3–5 paper scan**, collapse this hard: a TL;DR that directly answers the question, one short synthesis section (or just the table plus a couple of paragraphs), and references. Don't impose the full machinery on a quick lookup. For a **deep survey**, give each theme room: its `###` subsections from Step 6b, and a comparison table wherever several papers report on the same measure. Always match the weight of the output to what was asked.

**Citation style:** `render` produces numbered `[n]` references (Vancouver/Nature-style) by default, which is what the inline-citation prose above is built around; `--style ieee` is the same numbering in IEEE's layout. Consistency is automatic — you're not maintaining the list, so it can't drift.

Author-year styles (APA, Chicago) are deliberately **not** rendered. They need in-text markers like `(Wang et al., 2023)`, which would mean guessing surnames out of scraped author strings — precisely the sort of plausible-looking guess this pipeline exists to eliminate. If the user needs one, tell them straight: the ledger renders numeric styles, and an author-year list would have to be built by hand and would forfeit the guarantee. `references/citation_styles.md` has the formats if it comes to that.

### Step 7b — Render the deliverable

First fill the venues the search left empty, then compile the draft into the review you actually hand over:

```bash
python3 ~/.claude/skills/academic-literature/scripts/citation_ledger.py fill \
  --draft <output_dir>/literature.draft.md --ledger "$LEDGER"
python3 ~/.claude/skills/academic-literature/scripts/citation_ledger.py render \
  --draft <output_dir>/literature.draft.md --ledger "$LEDGER" --out <output_dir>/literature.md
```

**Why `fill` first.** The search backend often returns a paper without its journal or conference — in one batch of runs, 59% of cited entries rendered as `[venue unavailable]`. A reader, and every reference-quality judge, reads that as a sloppy bibliography however relevant the papers are. `fill` looks up each cited entry that lacks a venue in CrossRef: by its DOI when it has one, otherwise by title, accepted only when title, first author and year all match. It fills empty fields only, never overwrites what the search returned, and logs each fill as a `revise` with CrossRef as the source, so the ledger's rule — corrections from an authoritative record, never from memory — still holds. An entry CrossRef cannot match keeps `[venue unavailable]`; leave it, don't type a venue in. If `fill` reports lookups that got no answer (rate limiting), run it again; entries already filled are skipped.

Keys become `[1]`, `[2,5]` in order of first appearance, and a References section is built from the ledger — titles emphasized, venues not, DOIs resolved to `https://doi.org/…` links.

If `render` exits non-zero it has found a key with no ledger entry, and it names it. That means a citation entered the draft from somewhere other than a search result. Search for the paper and `add` it if it's real; otherwise cut the claim. Don't work around it by writing the reference in by hand — that's the failure this is here to catch.

### Step 8 — Check before delivering

```bash
python3 ~/.claude/skills/academic-literature/scripts/citation_ledger.py check \
  --draft <output_dir>/literature.draft.md --ledger "$LEDGER" \
  --review <output_dir>/literature.md --evidence <output_dir>/evidence
python3 ~/.claude/skills/academic-literature/scripts/verify_citations.py <output_dir>/literature.md
```

`check` re-renders from the ledger and diffs against what you're about to deliver. **Hard failures block delivery** and mean one of two things:

- *A key isn't in the ledger* — a citation that never came from a search.
- *The review doesn't match what the ledger renders* — `literature.md` was edited by hand after rendering, so its references are no longer provably real. Fix the draft and re-render. (This is strict on purpose: a hand-edit and a smuggled-in remembered citation look identical from here.)

`verify_citations.py` then resolves every DOI against doi.org and prints the CrossRef title beside it. The ledger guarantees a DOI was *copied* correctly, not that the scrape got it right in the first place — so this catches a dead or mis-scraped DOI. If one fails, don't retype it from memory: `citation_ledger.py revise --key wp:xxxxxx --ledger "$LEDGER" --from crossref` reconciles the entry against the authoritative record, then re-render.

**`check` also emits warnings, which don't block but do need your judgment** — they're the residue no script can settle:

- *A figure in the prose isn't in the cited paper's evidence.* Usually a rounding or rephrasing, sometimes a real mis-attribution: the number belongs to a different paper. Go back to `evidence/<key>.md` and confirm. This is the check for the failure the ledger can't see.
- *A cited paper has no evidence file* — cited but seemingly never read.
- *Scrape damage the ledger faithfully preserved* — no authors, a title with author names scraped into it, or a venue naming a conference on an arXiv DOI (an arXiv DOI record carries an empty venue, so claiming a specific conference reads as a mismatch); either find the published version's DOI or cite it as an arXiv preprint. `revise --from crossref` fixes most of these.

Mark anything genuinely unverifiable `[unverified]` — a self-hosted tech report, or a paper too new for the indexes — rather than letting it fail quietly.

## Quality bar

Before you finish, check that the review earns its keep:

- **`check` passes with zero hard failures**, and its warnings have each been looked at and either fixed or consciously accepted. This is the mechanical proof that every citation traces to a search result — you don't have to take your own word for it.
- **Every specific number in the prose traces to a line in some `evidence/<key>.md`.** The ledger can't check this and it's the likeliest surviving error: a real citation attached to a claim its paper never made.
- **Read-depth matches the Step 0 mode, and every paper's depth is marked.** In *full-text-required*, everything is full text except papers the user was explicitly asked about and agreed to leave abstract-only. In *full-text-when-available*, papers split between 全文 and 摘要 by what actually parsed. In *abstracts-only*, all are 摘要. In every case the study table's Source column (or an equivalent tag) tells the reader which — no paper is silently passed off as more deeply read than it was.
- **It reads as synthesis, not a list.** A reader can go top to bottom and follow an *argument* about the field. No section is a per-paper field dump; per-paper facts appear once, in the table; citations are there to support points, not to introduce papers one at a time. This is the bar this skill most often misses — hold it.
- **Themes are the topic's real sub-questions**, not generic "foundational / recent / related" buckets.
- **The heading tree has depth.** A standard or deep review has 3–6 `##` themes, each split into `###` subsections; read the headings alone, top to bottom, and they should outline the field's argument. No `TL;DR` or `At a glance` heading at the front.
- **The argument has synthesis aids**: at least one comparison table inside a theme, beyond the appendix table.
- **Citations are spread**: no single paper carries a large share of the claims unless the review says why it must.
- **Tension is surfaced**: the review says where papers agree, where they conflict, and which evidence is strongest and weakest — not just that each paper "is important".
- A substantive **Critical assessment** and **Gaps** section are present and specific.
- **DOIs verified**: `verify_citations.py` was run and every DOI resolves; resolved titles match what the review claims.
- Paper count matches the user's intent; a reasonable share are recent; every paper is on-topic. Delivered as `literature.md`, rendered — never hand-assembled.

## Example usage

```bash
# Quick novelty scan
/academic-literature "is there prior work on retrieval-augmented code generation?"

# Standard review, with an output directory
/academic-literature "graph neural networks for molecular property prediction" ./output/

# Explicit count
/academic-literature "find ~20 papers surveying diffusion models for image editing"
```

## Input parameters

- **Research topic** (required): the topic or question to review.
- **Output directory** (optional, default: current directory).

## What lands in the output directory

```
literature.md         the deliverable — rendered from the draft + ledger
literature.draft.md   the source you write, citing [wp:key]
citations.jsonl       the ledger: every paper found, verbatim from search
evidence/<key>.md     per-paper notes from the full text, keyed to the ledger
outline.md            the locked outline and claim map (Step 6b)
manifest.tsv          the selection (Step 4)
```

A submission-grade run adds `scope.md`, `search_log.tsv`, `figures/` and `handoff.md` (see `references/submission_mode.md`).

`literature.md` is what the user reads; the rest is the audit trail behind it. Keep them together — they're what makes the review's citations checkable months later, by you or by anyone who doubts an entry. If the user only wants the review, hand them `literature.md` and mention the rest is alongside it.
