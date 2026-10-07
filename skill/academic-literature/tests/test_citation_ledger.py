#!/usr/bin/env python3
"""Adversarial tests for citation_ledger.

The point is not that the happy path works -- it's that each hallucination
channel we claim to have closed is actually closed. Every test below plants a
specific attack the old skill would have shipped.
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT = Path.home() / ".claude/skills/academic-literature/scripts/citation_ledger.py"
sys.path.insert(0, str(SCRIPT.parent))
from citation_ledger import Ledger, identities, mint_key, render  # noqa: E402

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  {'✓' if cond else '✗'} {name}" + (f"\n      {detail}" if not cond and detail else ""))


def run(*args, cwd):
    return subprocess.run([sys.executable, str(SCRIPT), *args], cwd=cwd,
                          capture_output=True, text=True)


def paper(**kw):
    base = dict(title="T", authors=["A B"], venue="V", year=2024, doi=None,
                arxiv_id=None, url=None, pdf_url=None, citations=1, abstract="x")
    base.update(kw)
    return base


def write_search(path, papers):
    path.write_text(json.dumps({"papers": papers, "stats": {}}), encoding="utf-8")


# ---------------------------------------------------------------- identity
print("\n[identity & dedup]")
a = paper(title="Attention Is All You Need", doi="10.48550/arXiv.1706.03762")
b = paper(title="attention is all you need", arxiv_id="1706.03762")
check("arXiv DOI and bare arXiv id resolve to the same paper",
      bool(identities(a) & identities(b)), f"{identities(a)} vs {identities(b)}")

c = paper(title="Attention Is All You Need!", doi="10.48550/arXiv.1706.03762v2")
check("title punctuation/case differences still match",
      bool(identities(a) & identities(c)))

d = paper(title="A Totally Different Paper", doi="10.1000/xyz")
check("unrelated papers do not collide", not (identities(a) & identities(d)))
check("key is stable across records of the same paper", mint_key(a) == mint_key(
    paper(title="ATTENTION IS ALL YOU NEED", doi="10.48550/arxiv.1706.03762")))

# Publisher URLs append a view suffix after the DOI. Carrying it into the DOI
# yields a locator that 404s on doi.org while the stripped form resolves --
# a dead link in a delivered reference list, from a record whose `doi` field
# was simply null. Seen live: Frontiers .../10.3389/frma.2021.694307/full
from citation_ledger import _doi_of  # noqa: E402
for suffix, host in (("full", "frontiersin.org/journals/x/articles"),
                     ("abstract", "onlinelibrary.wiley.com/doi"),
                     ("html", "example.org/doi"),
                     ("meta", "journals.sagepub.com/doi"),
                     ("epdf", "example.org/doi")):
    rec = paper(title="Suffixed", doi=None,
                url=f"https://www.{host}/10.3389/frma.2021.694307/{suffix}")
    check(f"URL-derived DOI drops the trailing /{suffix}",
          _doi_of(rec) == "10.3389/frma.2021.694307", f"got {_doi_of(rec)!r}")

check("a DOI that genuinely contains a slashed segment is left alone",
      _doi_of(paper(title="T", doi=None, url="https://x.org/10.1594/PANGAEA.726855/part2"))
      == "10.1594/pangaea.726855/part2")

# ---------------------------------------------------------------- add/dedup
print("\n[add: dedup, merge, idempotence]")
with tempfile.TemporaryDirectory() as td:
    td = Path(td)
    # same paper in two facets; the second hit is richer
    write_search(td / "f1.json", [paper(title="Same Paper", doi=None, venue=None, citations=5)])
    write_search(td / "f2.json", [paper(title="Same Paper", doi="10.1000/same", venue="NeurIPS",
                                        year=2023, citations=5)])
    run("add", "--from-search", "f1.json", "f2.json", "--ledger", "l.jsonl", cwd=td)
    led = Ledger.load(td / "l.jsonl")
    check("one paper across two facets yields one entry", len(led.active()) == 1,
          f"got {len(led.active())}")
    rec = next(iter(led.active().values())).record
    check("the more complete hit wins the merge", rec.get("doi") == "10.1000/same",
          f"doi={rec.get('doi')}")

    before = (td / "l.jsonl").read_text()
    run("add", "--from-search", "f1.json", "f2.json", "--ledger", "l.jsonl", cwd=td)
    check("re-running add appends nothing (idempotent)",
          (td / "l.jsonl").read_text() == before)

# ---------------------------------------------------------------- drop
print("\n[drop: the '减' half of add-and-drop]")
with tempfile.TemporaryDirectory() as td:
    td = Path(td)
    write_search(td / "f.json", [paper(title="Keep", doi="10.1000/k"),
                                 paper(title="Toss", doi="10.1000/t")])
    run("add", "--from-search", "f.json", "--ledger", "l.jsonl", cwd=td)
    key_toss = mint_key(paper(title="Toss", doi="10.1000/t"))
    run("drop", "--key", key_toss, "--ledger", "l.jsonl", "--reason", "off-topic", cwd=td)
    led = Ledger.load(td / "l.jsonl")
    check("dropped paper leaves the active set", key_toss not in led.active())
    check("drop is recorded, not erased (history intact)",
          key_toss in led.entries and key_toss in led.dropped)

# ---------------------------------------------------------------- render
print("\n[render: numbering is derived, never hand-kept]")
with tempfile.TemporaryDirectory() as td:
    td = Path(td)
    write_search(td / "f.json", [
        paper(title="First Paper", doi="10.1000/a", authors=["Alice A", "Bob B"], year=2021),
        paper(title="Second Paper", doi="10.1000/b", authors=["Carol C"], year=2022),
        paper(title="Third Paper", doi="10.1000/c",
              authors=["D D", "E E", "F F", "G G"], year=2023),
    ])
    run("add", "--from-search", "f.json", "--ledger", "l.jsonl", cwd=td)
    k = {t: mint_key(paper(title=t, doi=d)) for t, d in
         (("First Paper", "10.1000/a"), ("Second Paper", "10.1000/b"), ("Third Paper", "10.1000/c"))}

    draft = (f"Alpha [{k['Second Paper']}]. Beta [{k['First Paper']}; {k['Third Paper']}].\n")
    (td / "d.md").write_text(draft)
    run("render", "--draft", "d.md", "--ledger", "l.jsonl", "--out", "out.md", cwd=td)
    out = (td / "out.md").read_text()
    check("numbering follows order of first appearance", "Alpha [1]. Beta [2,3]." in out,
          out.splitlines()[0])
    check("4+ authors collapse to et al.", "D D, et al." in out)
    check("2 authors are both listed", "Alice A, Bob B" in out)
    check("title is the emphasised span, venue is not", "*Second Paper.* V, 2022" in out)
    check("DOI renders as a resolvable URL", "https://doi.org/10.1000/b" in out)

    # Inserting a citation must renumber everything downstream -- the exact thing
    # a hand-maintained [n] list gets wrong.
    (td / "d.md").write_text(f"Zero [{k['Third Paper']}]. " + draft)
    run("render", "--draft", "d.md", "--ledger", "l.jsonl", "--out", "out2.md", cwd=td)
    out2 = (td / "out2.md").read_text()
    check("inserting a citation renumbers the rest correctly",
          "Zero [1]. Alpha [2]. Beta [3,1]." in out2, out2.splitlines()[0])

# ---------------------------------------------- ATTACK 1: invented citation
print("\n[ATTACK: a citation with no ledger entry]")
with tempfile.TemporaryDirectory() as td:
    td = Path(td)
    write_search(td / "f.json", [paper(title="Real", doi="10.1000/r")])
    run("add", "--from-search", "f.json", "--ledger", "l.jsonl", cwd=td)
    (td / "d.md").write_text(f"Real [{mint_key(paper(title='Real', doi='10.1000/r'))}] "
                             "and invented [wp:deadbe].\n")
    r = run("render", "--draft", "d.md", "--ledger", "l.jsonl", "--out", "out.md", cwd=td)
    check("render refuses a key that is not in the ledger", r.returncode != 0)
    check("...and names the offending key", "wp:deadbe" in r.stderr)

# ------------------------------------- ATTACK 2: hand-edited reference list
print("\n[ATTACK: references edited by hand after rendering]")
with tempfile.TemporaryDirectory() as td:
    td = Path(td)
    write_search(td / "f.json", [paper(title="Real Paper", doi="10.1000/r",
                                       authors=["Real Author"], year=2020)])
    run("add", "--from-search", "f.json", "--ledger", "l.jsonl", cwd=td)
    key = mint_key(paper(title="Real Paper", doi="10.1000/r"))
    (td / "d.md").write_text(f"A claim [{key}].\n")
    run("render", "--draft", "d.md", "--ledger", "l.jsonl", "--out", "out.md", cwd=td)
    r = run("check", "--draft", "d.md", "--ledger", "l.jsonl", "--review", "out.md", cwd=td)
    check("a clean rendered review passes check", r.returncode == 0, r.stdout[-300:])

    # the classic: model "fixes up" the year from memory
    tampered = (td / "out.md").read_text().replace("2020", "2019")
    (td / "out.md").write_text(tampered)
    r = run("check", "--draft", "d.md", "--ledger", "l.jsonl", "--review", "out.md", cwd=td)
    check("hand-changing a year in the references hard-fails", r.returncode != 0)

    # the dangerous one: an extra reference smuggled in from memory
    (td / "out.md").write_text(
        (td / "d.md").read_text().replace(f"[{key}]", "[1]")
        + "\n## References\n\n"
        + "[1] Real Author. *Real Paper.* V, 2020. https://doi.org/10.1000/r\n"
        + "[2] Vaswani et al. *Attention Is All You Need.* NeurIPS, 2017. https://doi.org/10.48550/arXiv.1706.03762\n"
    )
    r = run("check", "--draft", "d.md", "--ledger", "l.jsonl", "--review", "out.md", cwd=td)
    check("a reference smuggled in from memory hard-fails", r.returncode != 0)
    check("...even though that paper is genuinely real",
          "does not match what the ledger renders" in r.stdout)

# -------------------------------------- ATTACK 3: misattributed numbers (b)
print("\n[ATTACK: right citation, wrong number (mis-attribution)]")
with tempfile.TemporaryDirectory() as td:
    td = Path(td)
    write_search(td / "f.json", [paper(title="P One", doi="10.1000/1"),
                                 paper(title="P Two", doi="10.1000/2")])
    run("add", "--from-search", "f.json", "--ledger", "l.jsonl", cwd=td)
    k1 = mint_key(paper(title="P One", doi="10.1000/1"))
    k2 = mint_key(paper(title="P Two", doi="10.1000/2"))
    ev = td / "ev"
    ev.mkdir()
    (ev / f"{k1}.md").write_text("Reports 78.2% accuracy on the held-out split.\n")
    # k2 deliberately has no evidence file: cited but never read
    (td / "d.md").write_text(
        f"It reaches 78.2% accuracy [{k1}]. "
        f"A later model hits 91.4% [{k1}]. "
        f"Others agree [{k2}].\n"
    )
    run("render", "--draft", "d.md", "--ledger", "l.jsonl", "--out", "out.md", cwd=td)
    r = run("check", "--draft", "d.md", "--ledger", "l.jsonl", "--review", "out.md",
            "--evidence", "ev", cwd=td)
    check("a figure backed by evidence is not flagged", "78.2 is not in" not in r.stdout)
    check("a figure absent from the cited paper's evidence is flagged",
          "91.4" in r.stdout, r.stdout[-400:])
    check("a paper cited but never read is flagged",
          "has no evidence file" in r.stdout and k2 in r.stdout)
    check("soft warnings alone do not block delivery", r.returncode == 0)

# ---------------------------------------------- record-quality warnings
print("\n[scrape damage the ledger faithfully preserved]")
with tempfile.TemporaryDirectory() as td:
    td = Path(td)
    write_search(td / "f.json", [
        paper(title="Conf Paper", doi="10.48550/arXiv.2309.13339", venue="LREC/COLING"),
        paper(title="No Authors", doi="10.1000/na", authors=[]),
    ])
    run("add", "--from-search", "f.json", "--ledger", "l.jsonl", cwd=td)
    ka = mint_key(paper(title="Conf Paper", doi="10.48550/arXiv.2309.13339"))
    kb = mint_key(paper(title="No Authors", doi="10.1000/na"))
    (td / "d.md").write_text(f"X [{ka}] Y [{kb}].\n")
    run("render", "--draft", "d.md", "--ledger", "l.jsonl", "--out", "out.md", cwd=td)
    r = run("check", "--draft", "d.md", "--ledger", "l.jsonl", "--review", "out.md", cwd=td)
    check("conference venue on an arXiv DOI is flagged (gate hard-fail risk)",
          "arXiv DOI records carry an empty venue" in r.stdout)
    check("missing authors are flagged rather than invented", "no authors on the record" in r.stdout)
    check("[authors unavailable] is rendered, not a guessed name",
          "[authors unavailable]" in (td / "out.md").read_text())

# ---------------- ATTACK 4: a real number attached to the wrong paper (zh)
# The sharpest version of mis-attribution: nothing is invented. The figure is
# real and it is in the ledger's evidence -- just for a different paper. Every
# citation resolves; the claim is still false. Reviews here are usually written
# in Chinese, so the check has to survive Chinese sentence structure to see it.
print("\n[ATTACK: a real figure attributed to the wrong paper (Chinese prose)]")
with tempfile.TemporaryDirectory() as td:
    td = Path(td)
    write_search(td / "f.json", [paper(title="P One", doi="10.1000/1"),
                                 paper(title="P Two", doi="10.1000/2")])
    run("add", "--from-search", "f.json", "--ledger", "l.jsonl", cwd=td)
    k1 = mint_key(paper(title="P One", doi="10.1000/1"))
    k2 = mint_key(paper(title="P Two", doi="10.1000/2"))
    ev = td / "ev"
    ev.mkdir()
    (ev / f"{k1}.md").write_text("在 GSM8K 上达到 58.2% 的准确率（Table 3）。\n", encoding="utf-8")
    (ev / f"{k2}.md").write_text("在 GSM8K 上达到 91.3% 的准确率（Table 1）。\n", encoding="utf-8")
    # 58.2 belongs to k1; the second sentence hands it to k2.
    (td / "d.md").write_text(
        f"# T\n\n## 主题\n方法一达到 58.2% [{k1}]。方法二同样达到 58.2% [{k2}]。\n",
        encoding="utf-8")
    run("render", "--draft", "d.md", "--ledger", "l.jsonl", "--out", "out.md", cwd=td)
    r = run("check", "--draft", "d.md", "--ledger", "l.jsonl", "--review", "out.md",
            "--evidence", "ev", cwd=td)
    check("a real figure attributed to the wrong paper is caught in Chinese prose",
          "58.2 is not in the cited paper" in r.stdout and k2 in r.stdout, r.stdout[-350:])
    check("...and the paper it truly belongs to is not flagged",
          r.stdout.count("58.2 is not in") == 1, r.stdout[-350:])

# ---------------------------------------------- restore: undo a drop
print("\n[restore: bringing a dropped paper back]")
with tempfile.TemporaryDirectory() as td:
    td = Path(td)
    write_search(td / "f.json", [paper(title="Kept", doi="10.1/k"),
                                 paper(title="Oops", doi="10.1/o")])
    run("add", "--from-search", "f.json", "--ledger", "l.jsonl", cwd=td)
    k_oops = mint_key(paper(title="Oops", doi="10.1/o"))
    run("drop", "--key", k_oops, "--ledger", "l.jsonl", cwd=td)
    check("dropped paper is inactive before restore", k_oops not in Ledger.load(td / "l.jsonl").active())
    run("restore", "--key", k_oops, "--ledger", "l.jsonl", "--reason", "needed after all", cwd=td)
    check("restore re-activates a dropped paper", k_oops in Ledger.load(td / "l.jsonl").active())
    # and the restored record is the real one, not hand-typed
    rec = Ledger.load(td / "l.jsonl").active()[k_oops].record
    check("restored record keeps its original metadata", rec.get("doi") == "10.1/o")

# ---------------------------------- thousands separators in figures
print("\n[mis-attribution check tolerates thousands separators]")
with tempfile.TemporaryDirectory() as td:
    td = Path(td)
    write_search(td / "f.json", [paper(title="Q Paper", doi="10.1/q")])
    run("add", "--from-search", "f.json", "--ledger", "l.jsonl", cwd=td)
    key = mint_key(paper(title="Q Paper", doi="10.1/q"))
    ev = td / "ev"; ev.mkdir()
    (ev / f"{key}.md").write_text("Q of 5,510 at 2.92 GHz; around 3,000.\n", encoding="utf-8")
    (td / "d.md").write_text(f"# T\n\n## S\n谐振器 Q 值达 3000–5510 [{key}]。\n", encoding="utf-8")
    run("render", "--draft", "d.md", "--ledger", "l.jsonl", "--out", "out.md", cwd=td)
    r = run("check", "--draft", "d.md", "--ledger", "l.jsonl", "--review", "out.md",
            "--evidence", "ev", cwd=td)
    check("'5510' in prose matches '5,510' in evidence (no false alarm)",
          "5510 is not in" not in r.stdout and "3000 is not in" not in r.stdout, r.stdout[-300:])

print(f"\n{'=' * 58}\n{len(PASS)} passed, {len(FAIL)} failed")
if FAIL:
    print("FAILED: " + ", ".join(FAIL))
sys.exit(1 if FAIL else 0)
