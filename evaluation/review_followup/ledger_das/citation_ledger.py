#!/usr/bin/env python3
"""Append-only citation ledger: real paper metadata, mechanically rendered.

The problem this solves: a literature review's search results live only in the
model's context. By the time the References section gets written -- many steps,
several subagents and one context compaction later -- the real JSON is long gone
and the model is *recalling* metadata rather than copying it. That is where
fabricated authors, wrong years and invented DOIs come from. It is not
disobedience; the data simply isn't in front of it any more.

So we take the model out of the metadata path entirely:

    search JSON  --add-->  citations.jsonl  --render-->  References section

The model only ever chooses *which* papers to cite, by key. It never types a
citation field. `check` then proves this held, by re-rendering from the ledger
and diffing against the delivered file.

Ledger semantics -- "add and drop, never edit":
  add     a paper enters, from an actual search result
  drop    a paper leaves (off-topic, superseded)
  revise  a correction -- allowed ONLY with authoritative provenance (a fresh
          search or a CrossRef fetch), never a hand-edit from memory

The escape hatch matters. wispaper scrapes its metadata, so a field is
occasionally garbled; a rule of "never change anything, ever" would freeze that
error in place forever and push its user to just bypass the ledger. `revise`
keeps corrections possible while keeping them honest: the new value has to come
from somewhere citable, and the old value stays in the log.

Subcommands:
    add     --from-search f1.json ... --ledger citations.jsonl
    keys    --ledger citations.jsonl
    render  --draft d.md --ledger citations.jsonl --out literature.md
    check   --draft d.md --ledger citations.jsonl --review literature.md
    revise  --key wp:xxxxxx --ledger citations.jsonl --from crossref

Only dependency (for `revise --from crossref`): requests.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

KEY_PREFIX = "wp"
CITE_RE = re.compile(r"\[((?:wp:[0-9a-f]{6})(?:\s*;\s*wp:[0-9a-f]{6})*)\]")
KEY_RE = re.compile(r"wp:[0-9a-f]{6}")
REFS_HEADING_RE = re.compile(r"^##+\s*(References|参考文献|Bibliography)\s*$", re.M | re.I)
ARXIV_DOI_PREFIX = "10.48550/arXiv."

# CrossRef is a public, global scholarly registry with a single canonical host —
# not internal (env, region) infrastructure, so hardcoding it does not carry the
# routing hazard the "no hardcoded hosts" rule targets. It is still made
# env-overridable (with the canonical default) so a locked-down region can point
# it at a mirror/proxy without a code change.
CROSSREF_WORKS = os.environ.get("CROSSREF_API_BASE", "https://api.crossref.org/works/")

# Reading `add --from-search` files: the invoker (the agent) names the paths, the
# tool runs with the invoker's own privileges, and contents are parsed as search
# JSON — never returned to any external party. So directory confinement is the
# wrong control (and would break the skill's documented `DIR=$(mktemp -d)` inputs,
# which live under /tmp, not the output dir). What is proportionate: refuse
# anything that isn't a plain existing file, and cap size so a mistaken path can't
# stream an arbitrarily large file into memory.
MAX_SEARCH_FILE_BYTES = 64 * 1024 * 1024

# Bibliographic fields copied verbatim from the search result. Deliberately not
# the whole payload: relevance_score and flags describe *this search*, not the
# paper, and have no business in a citation.
BIB_FIELDS = (
    "title", "authors", "venue", "year", "doi", "arxiv_id",
    "url", "pdf_url", "citations", "abstract",
)


# --------------------------------------------------------------------------
# identity & keys
# --------------------------------------------------------------------------

def _norm_text(value: str) -> str:
    """Fold a title down to a comparison key: no case, no punctuation, no runs."""
    folded = unicodedata.normalize("NFKD", value or "").lower()
    folded = "".join(c for c in folded if not unicodedata.combining(c))
    folded = re.sub(r"[^a-z0-9一-鿿]+", " ", folded)
    return re.sub(r"\s+", " ", folded).strip()


def _norm_doi(doi: str) -> str:
    d = (doi or "").strip().lower()
    d = re.sub(r"^(https?://(dx\.)?doi\.org/|doi:)", "", d)
    return d.rstrip(".,;)")


def _norm_arxiv(arxiv_id: str) -> str:
    a = (arxiv_id or "").strip().lower()
    a = re.sub(r"^(arxiv:|https?://arxiv\.org/(abs|pdf)/)", "", a)
    return re.sub(r"(v\d+)?(\.pdf)?$", "", a)


# Publisher view suffixes that follow a DOI in an article URL. A closed list,
# so a DOI whose own suffix happens to be a slashed segment survives.
_VIEW_SUFFIX = re.compile(r"/(full|abstract|html|epdf|pdf|meta|citations?|references)$", re.I)


def _doi_of(rec: Dict[str, Any]) -> str:
    """The record's DOI, from the field or recovered out of its URL.

    Publisher links carry the DOI in the path (link.springer.com/article/10.1007/
    s11227-025-07583-2) while wispaper's `doi` field comes back null. Reading it
    out of the URL invents nothing -- the DOI was already in the record -- and it
    buys a resolvable locator, a stronger dedup identity, and something CrossRef
    can adjudicate in `revise`.

    Recovery happens on read, never on write: the stored record must stay a
    verbatim copy of what the search returned, or "the ledger is the search
    result" stops being literally true.

    The URL usually continues past the DOI with a view suffix -- Frontiers ends
    in `/full`, Wiley in `/abstract`, SAGE in `/meta`. Keeping that suffix gives
    a DOI that 404s on doi.org while the stripped one resolves, so a reference
    ships with a dead link. Only a closed list of view words is stripped: some
    real DOIs do carry a slashed segment (`10.1594/PANGAEA.726855/part2`).
    """
    if direct := _norm_doi(rec.get("doi") or ""):
        return direct
    for f in ("url", "pdf_url"):
        if m := re.search(r"(10\.\d{4,}/[^\s?&#]+)", rec.get(f) or ""):
            candidate = re.sub(r"\.pdf$", "", m.group(1))
            candidate = _VIEW_SUFFIX.sub("", candidate)
            return _norm_doi(candidate)
    return ""


def _arxiv_of(rec: Dict[str, Any]) -> str:
    """The record's arXiv id, from the field or recovered from the DOI.

    wispaper leaves `arxiv_id` null even for papers whose DOI is plainly an
    arXiv one (10.48550/arXiv.2502.03373), so trusting the field alone loses the
    identity — and with it the ability to recognise that a DOI-bearing hit and an
    id-bearing hit are the same paper.
    """
    if direct := _norm_arxiv(rec.get("arxiv_id") or ""):
        return direct
    if m := re.match(r"10\.48550/arxiv\.(.+)$", _doi_of(rec)):
        return _norm_arxiv(m.group(1))
    return ""


def identities(rec: Dict[str, Any]) -> Set[str]:
    """Every handle by which this record might be recognised as the same paper.

    A paper often surfaces in several facet searches, and the scraped fields
    differ slightly between hits -- one has the DOI, another only a title. We
    match on *any* shared identity so those collapse into one ledger entry
    instead of three near-duplicate references.
    """
    out: Set[str] = set()
    if doi := _doi_of(rec):
        out.add(f"doi:{doi}")
    if arx := _arxiv_of(rec):
        out.add(f"arxiv:{arx}")
    if title := _norm_text(rec.get("title") or ""):
        out.add(f"title:{title}")
    return out


def mint_key(rec: Dict[str, Any]) -> str:
    """Stable key from the most durable identity available.

    DOI beats arXiv id beats title, because that is the order in which they
    survive the paper being revised, renamed or re-hosted.
    """
    if doi := _doi_of(rec):
        seed = f"doi:{doi}"
    elif arx := _arxiv_of(rec):
        seed = f"arxiv:{arx}"
    else:
        seed = f"title:{_norm_text(rec.get('title') or '')}"
    return f"{KEY_PREFIX}:{hashlib.sha1(seed.encode()).hexdigest()[:6]}"


def completeness(rec: Dict[str, Any]) -> int:
    """How much of a usable citation this record carries.

    Used only to pick a winner among duplicates of the same paper -- never to
    invent anything. A hit with a DOI and a venue beats a bare title.
    """
    score = 4 * bool(_doi_of(rec)) + 2 * bool(_arxiv_of(rec))
    for f, w in (("venue", 2), ("year", 2), ("authors", 2),
                 ("title", 1), ("pdf_url", 1), ("abstract", 1)):
        v = rec.get(f)
        if v and str(v).strip() and str(v).strip().upper() != "N/A":
            score += w
    return score


# --------------------------------------------------------------------------
# ledger
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Entry:
    key: str
    record: Dict[str, Any]
    provenance: Dict[str, Any] = field(default_factory=dict)


class Ledger:
    """Replay of an append-only event log. Nothing here mutates history."""

    def __init__(self, entries: Dict[str, Entry], dropped: Set[str]) -> None:
        self.entries = entries
        self.dropped = dropped

    @classmethod
    def load(cls, path: Path) -> "Ledger":
        entries: Dict[str, Entry] = {}
        dropped: Set[str] = set()
        if not path.exists():
            return cls(entries, dropped)
        with path.open(encoding="utf-8") as fh:
            for lineno, line in enumerate(fh, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    ev = json.loads(line)
                except json.JSONDecodeError as e:
                    raise SystemExit(f"ledger corrupt at {path}:{lineno}: {e}")
                kind, key = ev.get("event"), ev.get("key")
                if not key:
                    continue
                if kind in ("add", "revise"):
                    entries[key] = Entry(key, ev.get("record", {}), ev.get("provenance", {}))
                    dropped.discard(key)
                elif kind == "drop":
                    dropped.add(key)
        return cls(entries, dropped)

    def active(self) -> Dict[str, Entry]:
        return {k: v for k, v in self.entries.items() if k not in self.dropped}

    def identity_index(self) -> Dict[str, str]:
        idx: Dict[str, str] = {}
        for key, entry in self.entries.items():
            for ident in identities(entry.record):
                idx[ident] = key
        return idx


def append_event(path: Path, event: Dict[str, Any]) -> None:
    event.setdefault("ts", datetime.now(timezone.utc).isoformat())
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, ensure_ascii=False) + "\n")


# --------------------------------------------------------------------------
# rendering
# --------------------------------------------------------------------------

def _authors_str(authors: Any) -> str:
    if isinstance(authors, str):
        names = [a.strip() for a in re.split(r"[;,]| and ", authors) if a.strip()]
    elif isinstance(authors, (list, tuple)):
        names = []
        for a in authors:
            if isinstance(a, dict):
                a = a.get("name") or a.get("full_name") or ""
            if str(a).strip():
                names.append(str(a).strip())
    else:
        names = []
    names = [n for n in names if n.upper() != "N/A"]
    if not names:
        return "[authors unavailable]"
    if len(names) > 3:
        return f"{names[0]}, et al."
    return ", ".join(names)


def _venue_str(rec: Dict[str, Any]) -> str:
    venue = (rec.get("venue") or "").strip()
    if venue and venue.upper() != "N/A":
        return venue
    # An arXiv DOI record carries an empty venue. Naming a conference against it
    # reads as a mismatch to a citation gate, so say what we actually know.
    if _arxiv_of(rec):
        return "arXiv preprint"
    return "[venue unavailable]"


def _locator(rec: Dict[str, Any]) -> str:
    if doi := _doi_of(rec):
        return f"https://doi.org/{doi}"
    if arx := _arxiv_of(rec):
        return f"https://arxiv.org/abs/{arx}"
    for f in ("url", "pdf_url"):
        if (v := (rec.get(f) or "").strip()):
            return v
    return "[no locator] [unverified]"


def _stop(text: str) -> str:
    """End a field with exactly one full stop.

    Scraped titles and 'et al.' both already end in a period, and blindly
    appending another yields 'Lei Wang, et al..' -- which looks like exactly the
    sloppiness this module exists to disprove.
    """
    text = text.strip()
    return text if text.endswith((".", "?", "!")) else text + "."


def render_reference(num: int, rec: Dict[str, Any], style: str = "numbered") -> str:
    """One reference line, every field copied from the ledger.

    Across every style the title is the emphasised span and the venue is not:
    citation gates read the first *italic* run as the title, so italicising the
    venue (the usual academic habit) makes every entry look like it points at a
    different paper -- a mass false alarm that reads as fabrication but is pure
    formatting.
    """
    title = (rec.get("title") or "").strip() or "[title unavailable]"
    year = str(rec.get("year") or "").strip() or "n.d."
    authors = _authors_str(rec.get("authors"))
    venue, locator = _venue_str(rec), _locator(rec)

    # Numeric styles only, by design. An author-year style (APA, Chicago) needs
    # in-text markers like "(Wang et al., 2023)", which means deriving surnames
    # from scraped author strings -- a guess that breaks on exactly the names it
    # shouldn't. Rendering APA reference lines under [n] in-text markers would be
    # worse: incoherent output that merely looks supported. If a venue demands an
    # author-year style, say so rather than half-doing it here.
    if style == "ieee":
        return f'[{num}] {_stop(authors)} "*{_stop(title)}*" {venue}, {year}. {locator}'
    return f"[{num}] {_stop(authors)} *{_stop(title)}* {venue}, {year}. {locator}"


def collect_keys(draft: str) -> List[str]:
    """Cited keys in order of first appearance -- the numbering order."""
    ordered: List[str] = []
    for match in CITE_RE.finditer(draft):
        for key in KEY_RE.findall(match.group(1)):
            if key not in ordered:
                ordered.append(key)
    return ordered


def render(draft: str, ledger: Ledger, style: str = "numbered") -> Tuple[str, List[str]]:
    """Replace [wp:key] with [n] and append a ledger-derived References section.

    Returns (rendered_markdown, unknown_keys). Numbering is derived here and
    never by hand: hand-maintained numbers silently scramble the moment a paper
    is inserted or dropped mid-draft, and re-deriving them from memory is
    exactly the failure this whole module exists to prevent.
    """
    active = ledger.active()
    ordered = collect_keys(draft)
    unknown = [k for k in ordered if k not in active]
    numbering = {k: i for i, k in enumerate((k for k in ordered if k in active), start=1)}

    def sub(match: re.Match) -> str:
        keys = KEY_RE.findall(match.group(1))
        nums = [str(numbering[k]) for k in keys if k in numbering]
        missing = [k for k in keys if k not in numbering]
        rendered = ",".join(nums)
        if missing:
            rendered = (rendered + "," if rendered else "") + ",".join(f"??{k}" for k in missing)
        return f"[{rendered}]"

    body = CITE_RE.sub(sub, draft)
    body = REFS_HEADING_RE.split(body)[0].rstrip()

    # The style marker lets `check` re-render exactly as this run did, instead of
    # guessing and hard-failing a perfectly good review over a flag mismatch.
    lines = [body, "", f"<!-- citation-ledger: rendered, style={style} -->", "", "## References", ""]
    lines.extend(render_reference(n, active[k].record, style) for k, n in numbering.items())
    return "\n".join(lines) + "\n", unknown


STYLE_MARKER_RE = re.compile(r"<!--\s*citation-ledger:\s*rendered,\s*style=(\w+)\s*-->")


def style_of(rendered: str) -> str:
    """The style a delivered review was rendered in, read back from its marker."""
    m = STYLE_MARKER_RE.search(rendered)
    return m.group(1) if m else "numbered"


# --------------------------------------------------------------------------
# subcommands
# --------------------------------------------------------------------------

def _load_search_records(paths: Sequence[Path]) -> List[Tuple[Dict[str, Any], Dict[str, Any]]]:
    out: List[Tuple[Dict[str, Any], Dict[str, Any]]] = []
    for p in paths:
        try:
            st = p.stat()
            if not p.is_file():  # reject dirs, /dev/*, sockets, fifos
                sys.stderr.write(f"skip {p}: not a regular file\n")
                continue
            if st.st_size > MAX_SEARCH_FILE_BYTES:
                sys.stderr.write(f"skip {p}: {st.st_size} bytes exceeds the search-file cap\n")
                continue
            payload = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            sys.stderr.write(f"skip {p}: {e}\n")
            continue
        papers = payload.get("papers") if isinstance(payload, dict) else payload
        for paper in papers or []:
            if not (paper.get("title") or "").strip():
                continue
            rec = {f: paper.get(f) for f in BIB_FIELDS}
            out.append((rec, {"source": "wispaper-search", "file": p.name}))
    return out


def cmd_add(args: argparse.Namespace) -> int:
    path = Path(args.ledger)
    ledger = Ledger.load(path)
    index = ledger.identity_index()
    candidates = _load_search_records([Path(p) for p in args.from_search])

    # Collapse duplicates of the same paper across facets before writing, keeping
    # the most complete hit. Batch-then-write keeps one add event per paper.
    merged: Dict[str, Tuple[Dict[str, Any], Dict[str, Any]]] = {}
    for rec, prov in candidates:
        hit = next((index[i] for i in identities(rec) if i in index), None)
        if hit:
            continue  # already in the ledger from an earlier run
        pending = next((k for k, (r, _) in merged.items() if identities(rec) & identities(r)), None)
        if pending is None:
            merged[mint_key(rec)] = (rec, prov)
        elif completeness(rec) > completeness(merged[pending][0]):
            merged[pending] = (rec, prov)

    for key, (rec, prov) in merged.items():
        append_event(path, {"event": "add", "key": key, "record": rec, "provenance": prov})

    skipped = len(candidates) - len(merged)
    sys.stderr.write(f"added {len(merged)} new paper(s); {skipped} duplicate/known hit(s) collapsed\n")
    _print_keys(Ledger.load(path))
    return 0


def _print_keys(ledger: Ledger) -> None:
    active = ledger.active()
    if not active:
        print("(ledger empty)")
        return
    print(f"{'KEY':<12} {'YEAR':<6} {'CITES':<6} TITLE")
    print("-" * 100)
    for key, entry in sorted(active.items(), key=lambda kv: -(kv[1].record.get("citations") or 0)):
        rec = entry.record
        title = (rec.get("title") or "")[:62]
        print(f"{key:<12} {str(rec.get('year') or '?'):<6} {str(rec.get('citations') or 0):<6} {title}")
    print(f"\n{len(active)} paper(s). Cite in the draft as [wp:xxxxxx]; never retype the metadata.")


def cmd_keys(args: argparse.Namespace) -> int:
    _print_keys(Ledger.load(Path(args.ledger)))
    return 0


def cmd_drop(args: argparse.Namespace) -> int:
    path = Path(args.ledger)
    ledger = Ledger.load(path)
    for key in args.key:
        if key not in ledger.entries:
            sys.stderr.write(f"unknown key {key}\n")
            return 2
        append_event(path, {"event": "drop", "key": key, "reason": args.reason})
        sys.stderr.write(f"dropped {key}\n")
    return 0


def cmd_restore(args: argparse.Namespace) -> int:
    """Bring a dropped paper back into the active set.

    `drop` is easy to over-apply while curating, and then a citation you kept
    turns out to need it after all. `add --from-search` won't undo the drop --
    it treats the key as already known and skips it -- so without this there is
    no honest path back. Restore re-emits the paper's *original* add record
    (already in the log, from a real search), never a hand-typed one.
    """
    path = Path(args.ledger)
    ledger = Ledger.load(path)
    for key in args.key:
        if key not in ledger.entries:
            sys.stderr.write(f"unknown key {key}; nothing to restore\n")
            return 2
        if key not in ledger.dropped:
            sys.stderr.write(f"{key} is already active; skipping\n")
            continue
        append_event(path, {
            "event": "add", "key": key, "record": ledger.entries[key].record,
            "provenance": {"source": "restore", "reason": args.reason or "re-activated after drop"},
        })
        sys.stderr.write(f"restored {key}\n")
    return 0


def cmd_render(args: argparse.Namespace) -> int:
    draft = Path(args.draft).read_text(encoding="utf-8")
    ledger = Ledger.load(Path(args.ledger))
    out, unknown = render(draft, ledger, args.style)
    if unknown:
        sys.stderr.write(
            "ERROR: draft cites keys that are not in the ledger: "
            + ", ".join(unknown)
            + "\n  A citation with no ledger entry came from somewhere other than a search\n"
              "  result. Search for the paper and `add` it, or remove the claim.\n"
        )
        return 1
    Path(args.out).write_text(out, encoding="utf-8")
    n = len(collect_keys(draft))
    sys.stderr.write(f"rendered {n} citation(s) -> {args.out}\n")
    return 0


def _split_prose(text: str) -> List[str]:
    # Only true sentence enders. A semicolon joins clauses *within* a sentence,
    # and a comparison sentence routinely spans papers across one -- "REDCODER
    # reports X [key1]; ReACC reports Y [key2]". Cutting there strands the second
    # clause's figures in a window holding only the first clause's key, and the
    # checker reports a mis-attribution against prose that is perfectly correct.
    parts = re.split(r"(?<=[。！？])|(?<=[.!?])\s+|\n{2,}", text)
    return [p for p in parts if p and p.strip()]


def _sentences(text: str) -> List[str]:
    """Split prose into sentences, in Chinese as well as English.

    Two things this has to get right, both learned the hard way:

    Chinese writes 「第一句。第二句。」 with no space after the full stop, so a
    splitter that requires trailing whitespace treats a whole Chinese review as
    one sentence -- collapsing the number-attribution check into "does this
    figure appear anywhere at all", the weak version of the question.

    And a markdown table row is atomic. Rows carry their own [wp:key] plus
    several figures, and cells routinely contain sentence-enders ("EM 18.6 →
    23.4；目标回填则 10.21 → 36.99"). Splitting inside a row lets its tail merge
    with the *next* row's opening key, so one study's numbers get checked against
    the following study's evidence -- a stream of false alarms that all look real.
    Noisy warnings get skimmed, and skimmed warnings check nothing.
    """
    out: List[str] = []
    buf: List[str] = []
    for line in text.split("\n"):
        if line.lstrip().startswith("|"):
            if buf:
                out.extend(_split_prose("\n".join(buf)))
                buf = []
            out.append(line)  # the row, whole
        else:
            buf.append(line)
    if buf:
        out.extend(_split_prose("\n".join(buf)))
    return [s.strip() for s in out if s.strip()]


def _evidence_numbers(text: str) -> Set[str]:
    # Strip thousands separators first: an evidence file writes "5,510" or "1,881"
    # where the prose writes "5510" / "1881". Without this the digits match by
    # eye but not by string, and the checker cries mis-attribution over a figure
    # that is right there in the source -- the noisy false alarm that trains a
    # reader to ignore the warnings.
    return set(re.findall(r"\d+(?:\.\d+)?", re.sub(r"(?<=\d),(?=\d{3}\b)", "", text)))


def _claim_numbers(sentence: str) -> Set[str]:
    """Numbers in prose worth tracing back to a source.

    Bare small integers and years are dropped: they are almost always counts,
    enumerations or publication dates rather than reported results, and flagging
    them buries the real mis-attributions in noise.

    So are digits inside an identifier -- DS-1000, GPT-4, CodeT5, pass@1. They
    name a thing rather than report a measurement, and no evidence file will
    ever "contain" them as figures. Every one flagged is a false alarm, and false
    alarms are what teach a reader to stop reading the warnings.
    """
    out: Set[str] = set()
    sentence = re.sub(r"(?<=\d),(?=\d{3}\b)", "", sentence)  # 5,510 -> 5510, matching evidence
    for m in re.finditer(r"\d+(?:\.\d+)?%?", sentence):
        start = m.start()
        if start > 0 and (sentence[start - 1].isalpha() or sentence[start - 1] in "-@_"):
            continue  # part of a name, not a result
        tok = m.group(0)
        bare = tok.rstrip("%")
        try:
            val = float(bare)
        except ValueError:
            continue
        if tok.endswith("%") or "." in bare:
            out.add(bare)
        elif val >= 10 and not (1900 <= val <= 2100):
            out.add(bare)
    return out


def _check_evidence(draft: str, ledger: Ledger, evidence_dir: Path) -> List[str]:
    """Soft checks for mis-attribution: is the claim actually in that paper?

    This cannot be a hard gate. Free-text claims get legitimately rephrased,
    rounded and aggregated, so a strict rule would cry wolf until it was ignored.
    These are review prompts for a human, not verdicts.
    """
    warnings: List[str] = []
    active = ledger.active()
    cited = [k for k in collect_keys(draft) if k in active]

    for key in cited:
        if not (evidence_dir / f"{key}.md").exists():
            title = (active[key].record.get("title") or "")[:60]
            warnings.append(f"{key} is cited but has no evidence file — was it actually read? ({title})")

    for sentence in _sentences(draft):
        keys = [k for m in CITE_RE.finditer(sentence) for k in KEY_RE.findall(m.group(1))]
        if not keys:
            continue
        nums = _claim_numbers(CITE_RE.sub("", sentence))
        if not nums:
            continue
        pool: Set[str] = set()
        for key in keys:
            ev = evidence_dir / f"{key}.md"
            if ev.exists():
                pool |= _evidence_numbers(ev.read_text(encoding="utf-8"))
        if not pool:
            continue
        for num in sorted(nums - pool):
            quote = re.sub(r"\s+", " ", sentence).strip()[:80]
            warnings.append(
                f"{','.join(keys)}: the figure {num} is not in the cited paper's evidence — "
                f"verify or re-attribute: \"{quote}\""
            )
    return warnings


def _record_warnings(rec: Dict[str, Any]) -> List[str]:
    """Flag scrape damage the ledger faithfully preserved.

    Copying verbatim buys freedom from *invented* metadata, not from wrong
    metadata: wispaper scrapes, so fields arrive garbled or thin. These are the
    residue the ledger cannot fix by itself, surfaced so a human can decide
    whether to `revise` from CrossRef or cite it differently.
    """
    out: List[str] = []
    title = (rec.get("title") or "")[:55]
    authors = rec.get("authors")
    if not authors or str(authors).strip().upper() in ("N/A", "[]", ""):
        out.append(f"no authors on the record (scrape gap) — check before delivering: {title}")

    venue = (rec.get("venue") or "").strip()
    is_arxiv_doi = _doi_of(rec).startswith("10.48550/arxiv.")
    generic = re.match(r"^(arxiv|corr|preprint)\b", venue, re.I)
    if is_arxiv_doi and venue and not generic:
        out.append(
            f"venue says {venue!r} but the DOI is an arXiv DOI. arXiv DOI records carry an "
            f"empty venue, so a citation gate resolving it sees a mismatch and may hard-fail. "
            f"Find the published version's DOI, or cite it as an arXiv preprint: {title}"
        )
    if not _doi_of(rec) and not _arxiv_of(rec):
        out.append(f"no DOI, arXiv id or URL — mark this one [unverified]: {title}")

    # Author names bleeding into the title is a common scrape artifact, e.g.
    # "...self-optimization prompting: H. Chen et al.". Copying it verbatim is
    # correct (we invent nothing) but it will not match the authoritative title,
    # so a gate reads it as a different paper. `revise --from crossref` fixes it.
    raw_title = (rec.get("title") or "").strip()
    if re.search(r"\bet al\.?\s*$", raw_title, re.I):
        out.append(f"the title ends in 'et al.' — author names look scraped into it; "
                   f"`revise --from crossref` to reconcile: {title}")
    return out


def cmd_check(args: argparse.Namespace) -> int:
    draft = Path(args.draft).read_text(encoding="utf-8")
    ledger = Ledger.load(Path(args.ledger))
    review_path = Path(args.review)
    if not review_path.exists():
        sys.stderr.write(f"no rendered review at {review_path}; run `render` first\n")
        return 2

    actual = review_path.read_text(encoding="utf-8")
    expected, unknown = render(draft, ledger, style_of(actual))
    hard: List[str] = []

    if unknown:
        hard.append(
            "draft cites keys absent from the ledger: " + ", ".join(unknown)
            + "\n    Every citation must trace to a search result. Search and `add` it, or cut the claim."
        )

    # The load-bearing assertion. If the delivered file is not byte-identical to
    # what the ledger renders, then something in it -- a reference line, a
    # citation number -- was written by hand. That is precisely the channel
    # through which a remembered paper smuggles itself in.
    if expected != actual:
        hard.append(
            f"{review_path.name} does not match what the ledger renders.\n"
            "    Its References were hand-written or hand-edited, so they are no longer\n"
            "    provably real. Edit the draft and re-run `render` — never edit the\n"
            f"    rendered file directly. Diff:\n{_diff(expected, actual)}"
        )

    if stray := [k for k in KEY_RE.findall(actual) if k]:
        hard.append(f"unrendered keys left in the review: {', '.join(sorted(set(stray)))}")

    warnings = _check_evidence(draft, ledger, Path(args.evidence)) if args.evidence else []
    # Only papers that actually made it into the review matter here. The ledger
    # also holds the un-cited candidate pool, and griping about those buries the
    # warnings that bear on what is being delivered.
    active = ledger.active()
    for key in collect_keys(draft):
        if key in active:
            warnings.extend(_record_warnings(active[key].record))

    print("=" * 64)
    print("CITATION LEDGER CHECK")
    print("=" * 64)
    print(f"cited papers : {len([k for k in collect_keys(draft) if k in ledger.active()])}")
    print(f"ledger size  : {len(ledger.active())} active, {len(ledger.dropped)} dropped")
    print(f"hard failures: {len(hard)}")
    print(f"warnings     : {len(warnings)}")
    if hard:
        print("\nHARD FAILURES (fix before delivering):")
        for h in hard:
            print(f"  ✗ {h}")
    if warnings:
        print("\nWARNINGS (human judgement — not auto-fixable):")
        for w in warnings:
            print(f"  ! {w}")
    if not hard and not warnings:
        print("\n✓ every citation traces to a ledger entry; references render exactly.")
    return 1 if hard else 0


def _diff(expected: str, actual: str) -> str:
    import difflib
    lines = list(difflib.unified_diff(
        expected.splitlines(), actual.splitlines(),
        fromfile="ledger-rendered", tofile="delivered", lineterm="", n=0,
    ))
    return "\n".join(f"      {ln}" for ln in lines[:24]) or "      (whitespace only)"


REF_LINE_RE = re.compile(r"^\s*\[(\d+)\]\s+(.+)$", re.M)


def cmd_audit(args: argparse.Namespace) -> int:
    """Trace a freehand report's references back to real search results.

    For pipelines that write their own reference list (the swarm), we cannot put
    the model outside the metadata path, so we check afterwards instead: every
    reference should correspond to a paper some search actually returned. One
    that matches nothing came from somewhere else -- and 'somewhere else' is
    usually the model's memory.

    Detection, not prevention. Weaker than `render`, and the honest option when
    the writing step isn't ours to change.
    """
    report = Path(args.review).read_text(encoding="utf-8")
    ledger = Ledger.load(Path(args.ledger))
    active = ledger.active()
    if not active:
        sys.stderr.write(f"ledger {args.ledger} is empty — was CITATION_LEDGER set for the run?\n")
        return 2

    index: Dict[str, str] = {}
    for key, entry in active.items():
        for ident in identities(entry.record):
            index[ident] = key

    section = report
    if parts := REFS_HEADING_RE.split(report):
        section = parts[-1]

    matched: List[Tuple[str, str]] = []
    unmatched: List[Tuple[str, str]] = []
    for num, line in REF_LINE_RE.findall(section):
        hit = None
        if doi := _norm_doi(m.group(1)) if (m := re.search(r"(10\.\d{4,}/[^\s;,)\]]+)", line)) else "":
            hit = index.get(f"doi:{doi}")
        if not hit and (m := re.search(r"arxiv\.org/abs/([^\s;,)\]]+)", line, re.I)):
            hit = index.get(f"arxiv:{_norm_arxiv(m.group(1))}")
        if not hit:
            # The title appears near-verbatim in a reference line, so containment
            # of the folded title survives whatever citation style was used.
            folded = _norm_text(line)
            for key, entry in active.items():
                t = _norm_text(entry.record.get("title") or "")
                if len(t) > 20 and t in folded:
                    hit = key
                    break
        (matched if hit else unmatched).append((num, line.strip()[:88]))

    print("=" * 64)
    print("CITATION AUDIT — references vs. what the searches actually returned")
    print("=" * 64)
    print(f"ledger holds : {len(active)} retrieved paper(s)")
    print(f"references   : {len(matched) + len(unmatched)}")
    print(f"traceable    : {len(matched)}")
    print(f"NOT traceable: {len(unmatched)}")
    if unmatched:
        print("\nReferences that match no retrieved paper — each needs an explanation:")
        for num, line in unmatched:
            print(f"  ✗ [{num}] {line}")
        print(
            "\n  A paper found via paper_search would be in the ledger. One that isn't\n"
            "  either came from a web_fetch of an authoritative page (legitimate — say so,\n"
            "  and non-academic sources like datasheets/patents belong here) or from the\n"
            "  model's memory (fabrication — cut it or search for it and re-run)."
        )
    else:
        print("\n✓ every reference traces back to a real search result.")
    return 1 if unmatched else 0


def cmd_revise(args: argparse.Namespace) -> int:
    """Correct an entry from an authoritative record -- never from memory."""
    import requests

    path = Path(args.ledger)
    ledger = Ledger.load(path)
    if args.key not in ledger.entries:
        sys.stderr.write(f"unknown key {args.key}\n")
        return 2
    rec = dict(ledger.entries[args.key].record)
    doi = _doi_of(rec)
    if not doi:
        sys.stderr.write("entry has no DOI, so CrossRef cannot adjudicate it. "
                         "Re-search the paper and `add` the fresh hit instead.\n")
        return 2

    resp = requests.get(f"{CROSSREF_WORKS}{doi}", timeout=15,
                        headers={"User-Agent": "citation-ledger/1.0"})
    if resp.status_code != 200:
        sys.stderr.write(f"CrossRef returned {resp.status_code} for {doi}\n")
        return 1
    msg = resp.json().get("message", {})
    authors = [" ".join(x for x in (a.get("given"), a.get("family")) if x)
               for a in msg.get("author", [])]
    updated = dict(rec)
    if titles := msg.get("title"):
        updated["title"] = titles[0]
    if authors:
        updated["authors"] = authors
    if containers := msg.get("container-title"):
        updated["venue"] = containers[0]
    for k in ("published-print", "published-online", "issued"):
        if parts := msg.get(k, {}).get("date-parts", [[]])[0]:
            updated["year"] = parts[0]
            break

    changed = {k: (rec.get(k), updated.get(k)) for k in BIB_FIELDS if rec.get(k) != updated.get(k)}
    if not changed:
        sys.stderr.write("CrossRef agrees with the ledger; nothing to revise.\n")
        return 0
    append_event(path, {
        "event": "revise", "key": args.key, "record": updated,
        "provenance": {"source": "crossref", "doi": doi},
        "reason": args.reason or "reconciled against CrossRef",
        "superseded": {k: v[0] for k, v in changed.items()},
    })
    for f, (old, new) in changed.items():
        sys.stderr.write(f"  {f}: {str(old)[:40]!r} -> {str(new)[:40]!r}\n")
    sys.stderr.write(f"revised {args.key} (old values kept in the log)\n")
    return 0


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("add", help="ingest wispaper search JSON into the ledger")
    p.add_argument("--from-search", nargs="+", required=True)
    p.add_argument("--ledger", default="citations.jsonl")
    p.set_defaults(fn=cmd_add)

    p = sub.add_parser("keys", help="list ledger keys to cite by")
    p.add_argument("--ledger", default="citations.jsonl")
    p.set_defaults(fn=cmd_keys)

    p = sub.add_parser("drop", help="remove a paper from the review")
    p.add_argument("--key", nargs="+", required=True)
    p.add_argument("--ledger", default="citations.jsonl")
    p.add_argument("--reason", default="")
    p.set_defaults(fn=cmd_drop)

    p = sub.add_parser("restore", help="re-activate a dropped paper (undo drop)")
    p.add_argument("--key", nargs="+", required=True)
    p.add_argument("--ledger", default="citations.jsonl")
    p.add_argument("--reason", default="")
    p.set_defaults(fn=cmd_restore)

    p = sub.add_parser("render", help="draft + ledger -> delivered review")
    p.add_argument("--draft", required=True)
    p.add_argument("--ledger", default="citations.jsonl")
    p.add_argument("--out", required=True)
    p.add_argument("--style", choices=["numbered", "ieee"], default="numbered",
                   help="numeric styles only; author-year styles are not rendered")
    p.set_defaults(fn=cmd_render)

    p = sub.add_parser("check", help="prove the review's citations came from the ledger")
    p.add_argument("--draft", required=True)
    p.add_argument("--ledger", default="citations.jsonl")
    p.add_argument("--review", required=True)
    p.add_argument("--evidence", default=None, help="evidence dir for mis-attribution checks")
    p.set_defaults(fn=cmd_check)

    p = sub.add_parser("audit", help="trace a freehand report's references back to search results")
    p.add_argument("--review", required=True)
    p.add_argument("--ledger", default="citations.jsonl")
    p.set_defaults(fn=cmd_audit)

    p = sub.add_parser("revise", help="correct an entry from CrossRef (never from memory)")
    p.add_argument("--key", required=True)
    p.add_argument("--ledger", default="citations.jsonl")
    p.add_argument("--from", dest="source", choices=["crossref"], default="crossref")
    p.add_argument("--reason", default="")
    p.set_defaults(fn=cmd_revise)

    args = ap.parse_args()
    sys.exit(args.fn(args))


if __name__ == "__main__":
    main()
