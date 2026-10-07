"""Add the SurveyBench reference-survey filter to evalbot's copy of wis_mcp_search.py (idempotent)."""
import sys
from pathlib import Path

p = Path(sys.argv[1]); s = p.read_text(encoding="utf-8")
if "_drop_excluded_reference" in s:
    # upgrade an earlier version that assumed every reference survey has an arXiv id
    s = s.replace('ex["arxiv_id"], [d.lower()', 'ex.get("arxiv_id"), [d.lower()')
    s = s.replace('or aid in blob or any', 'or bool(aid and aid in blob) or any')
    s = s.replace('    title, aid, dois = norm(ex["title"]), ex.get("arxiv_id"), [d.lower() for d in ex["dois"]]',
                  '    titles = {norm(t) for t in ex.get("titles") or [ex["title"]]}\n    aid, dois = ex.get("arxiv_id"), [d.lower() for d in ex["dois"]]')
    s = s.replace('return norm(p.get("title")) == title or bool(aid', 'return norm(p.get("title")) in titles or bool(aid')
    p.write_text(s, encoding="utf-8"); print("upgraded"); sys.exit(0)
FUNC = '''
def _drop_excluded_reference(papers: List[Dict[str, Any]]) -> tuple:
    """SurveyBench runs only: drop the topic's held-out human reference survey.

    ``SB_EXCLUDE_FILE`` names a JSON object {arxiv_id, dois, title}; when it is unset nothing is filtered.
    """
    path = os.environ.get("SB_EXCLUDE_FILE")
    if not path:
        return papers, None
    import re
    ex = json.loads(Path(path).read_text(encoding="utf-8"))
    norm = lambda s: re.sub(r"[^a-z0-9]+", " ", str(s or "").lower()).strip()
    titles = {norm(t) for t in ex.get("titles") or [ex["title"]]}
    aid, dois = ex.get("arxiv_id"), [d.lower() for d in ex["dois"]]

    def hit(p: Dict[str, Any]) -> bool:
        blob = " ".join(str(p.get(k) or "") for k in ("arxiv_id", "doi", "url", "pdf_url")).lower()
        return norm(p.get("title")) in titles or bool(aid and aid in blob) or any(d in blob for d in dois)

    kept = [p for p in papers if not hit(p)]
    return kept, len(papers) - len(kept)


def search('''
old_line = '    papers = [p for p in raw_papers if str(p.get("title") or "").strip()]\n'
assert s.count("\ndef search(") == 1 and old_line in s
s = s.replace("\ndef search(", FUNC, 1)
s = s.replace(old_line, old_line + "    papers, n_excluded = _drop_excluded_reference(papers)\n", 1)
anchor = '            "request_id": cli.last_request_id,\n        }\n    )\n'
assert anchor in s
s = s.replace(anchor, anchor + '    if n_excluded is not None:\n        stats["excluded_reference"] = n_excluded\n', 1)
p.write_text(s, encoding="utf-8"); print("patched")
