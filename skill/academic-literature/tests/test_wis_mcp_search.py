#!/usr/bin/env python3
"""Tests for wis_mcp_search: the MCP-backed replacement for wispaper_search_standalone.

Every test isolates the network: the client is driven through a fake `_post` so
the session handshake, error mapping and result handling are checked without
touching the remote server.

Server contract under test is the v0.1 `top_n` API: the backend returns papers
already in this skill's schema, so the script's job is to carry them through
verbatim -- not to re-derive fields the ledger will later copy.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List

import pytest

SCRIPT = Path.home() / ".claude/skills/academic-literature/scripts/wis_mcp_search.py"
sys.path.insert(0, str(SCRIPT.parent))

import wis_mcp_search as wms  # noqa: E402

# A paper exactly as the v0.1 backend returns it (already normalised).
SERVER_PAPER: Dict[str, Any] = {
    "paper_id": None,
    "title": "RAG vs. GraphRAG: A Systematic Evaluation and Key Insights",
    "authors": ["Haoyu Han", "Harry Shomer"],
    "abstract": "We compare RAG and GraphRAG.",
    "url": "https://arxiv.org/abs/2502.11371",
    "pdf_url": None,
    "venue": None,
    "year": 2025,
    "citations": 12,
    "doi": None,
    "arxiv_id": "2502.11371",
    "relevance_score": 0.8166251192783329,
    "research_field": None,
    "source_url": "https://arxiv.org/abs/2502.11371",
    "flags": {"no": False, "partial": False, "perfect": True},
}

SERVER_STATS: Dict[str, Any] = {
    "dropped_parse": 0,
    "eligible_perfect_or_partial": 27,
    "kept": 61,
    "returned": 1,
    "topn": 10,
    "total": 61,
}


class FakeResponse:
    def __init__(self, status: int, body: str, headers: Dict[str, str] | None = None) -> None:
        self.status_code = status
        self._body = body
        self.headers = headers or {}

    @property
    def content(self) -> bytes:
        return self._body.encode("utf-8")

    @property
    def text(self) -> str:
        # Mimic requests' behaviour for `text/event-stream` with no charset:
        # RFC 2616 says ISO-8859-1, so requests mangles UTF-8 here. Any code
        # reading `.text` on this response gets the same mojibake it would in
        # production -- which is the point of modelling it.
        if self.headers.get("content-type", "").startswith("text/"):
            return self._body.encode("utf-8").decode("latin-1")
        return self._body


def _rpc_result(rid: int, result: Dict[str, Any]) -> str:
    return json.dumps({"jsonrpc": "2.0", "id": rid, "result": result}, ensure_ascii=False)


def _tool_text(payload: Dict[str, Any], is_error: bool = False) -> Dict[str, Any]:
    return {
        "content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}],
        "isError": is_error,
    }


def _ok_payload(papers: List[Dict[str, Any]] | None = None, **stats: Any) -> Dict[str, Any]:
    merged = dict(SERVER_STATS)
    merged.update(stats)
    return {"papers": papers if papers is not None else [SERVER_PAPER], "stats": merged, "raw_path": None}


class ScriptedTransport:
    """Answers each JSON-RPC method from a queue of canned responses."""

    def __init__(self, replies: List[FakeResponse]) -> None:
        self.replies = list(replies)
        self.sent: List[Dict[str, Any]] = []
        self.headers_seen: List[Dict[str, str]] = []

    def __call__(self, payload: Dict[str, Any], headers: Dict[str, str]) -> FakeResponse:
        self.sent.append(payload)
        self.headers_seen.append(dict(headers))
        if not self.replies:
            raise AssertionError(f"unexpected request: {payload.get('method')}")
        return self.replies.pop(0)

    def last_args(self) -> Dict[str, Any]:
        calls = [p for p in self.sent if p.get("method") == "tools/call"]
        return calls[-1]["params"]["arguments"]


def _handshake_replies(session_id: str = "sess-1") -> List[FakeResponse]:
    return [
        FakeResponse(
            200,
            _rpc_result(1, {"protocolVersion": "2025-03-26"}),
            {"mcp-session-id": session_id, "content-type": "text/event-stream"},
        ),
        FakeResponse(202, ""),
    ]


def make_client(replies: List[FakeResponse]) -> tuple[wms.McpClient, ScriptedTransport]:
    transport = ScriptedTransport(replies)
    client = wms.McpClient(url="https://example.invalid/mcp", token="tok", post=transport)
    return client, transport


# ---------------------------------------------------------------- handshake

def test_handshake_sends_initialize_then_initialized_and_keeps_session_id() -> None:
    client, transport = make_client(_handshake_replies("abc") + [
        FakeResponse(200, _rpc_result(3, _tool_text(_ok_payload()))),
    ])
    client.call_tool("quick_search", {"query": "x"})
    methods = [p.get("method") for p in transport.sent]
    assert methods == ["initialize", "notifications/initialized", "tools/call"]
    assert "Mcp-Session-Id" not in transport.headers_seen[0]
    assert transport.headers_seen[1]["Mcp-Session-Id"] == "abc"
    assert transport.headers_seen[2]["Mcp-Session-Id"] == "abc"
    assert transport.headers_seen[0]["Authorization"] == "Bearer tok"


def test_handshake_without_session_id_header_fails_loudly() -> None:
    client, _ = make_client([FakeResponse(200, _rpc_result(1, {}), {})])
    with pytest.raises(wms.McpError, match="Mcp-Session-Id"):
        client.call_tool("quick_search", {"query": "x"})


def test_session_is_reused_across_calls() -> None:
    client, transport = make_client(_handshake_replies() + [
        FakeResponse(200, _rpc_result(3, _tool_text(_ok_payload()))),
        FakeResponse(200, _rpc_result(4, _tool_text(_ok_payload()))),
    ])
    client.call_tool("quick_search", {"query": "a"})
    client.call_tool("quick_search", {"query": "b"})
    assert [p.get("method") for p in transport.sent].count("initialize") == 1


# ------------------------------------------------------- SSE framing / utf-8

def test_sse_framed_response_is_parsed() -> None:
    sse = "event: message\ndata: " + _rpc_result(3, _tool_text(_ok_payload())) + "\n\n"
    client, _ = make_client(_handshake_replies() + [
        FakeResponse(200, sse, {"content-type": "text/event-stream"}),
    ])
    out = client.call_tool("quick_search", {"query": "x"})
    assert out["papers"][0]["title"] == SERVER_PAPER["title"]


def test_sse_chinese_payload_survives_latin1_trap() -> None:
    """Regression: `text/event-stream` carries no charset, so requests decodes it
    as ISO-8859-1. UTF-8 Chinese containing byte 0x85 then becomes U+0085 (NEL),
    which `str.splitlines()` treats as a line break and which shatters the JSON.
    The tool list description ("按 perfect、partial、相关度排序") hits this.
    """
    payload = {"papers": [dict(SERVER_PAPER, title="优先级排序与访问控制")], "stats": SERVER_STATS,
               "raw_path": None}
    sse = "data: " + _rpc_result(3, _tool_text(payload)) + "\n\n"
    assert "\x85" in sse.encode("utf-8").decode("latin-1"), "fixture must contain the trap byte"
    client, _ = make_client(_handshake_replies() + [
        FakeResponse(200, sse, {"content-type": "text/event-stream"}),
    ])
    out = client.call_tool("quick_search", {"query": "访问控制"})
    assert out["papers"][0]["title"] == "优先级排序与访问控制"


def test_multiline_sse_data_frame_is_joined() -> None:
    body = _rpc_result(3, _tool_text(_ok_payload()))
    half = len(body) // 2
    sse = f"data: {body[:half]}\ndata: {body[half:]}\n\n"
    client, _ = make_client(_handshake_replies() + [
        FakeResponse(200, sse, {"content-type": "text/event-stream"}),
    ])
    out = client.call_tool("quick_search", {"query": "x"})
    assert out["papers"][0]["title"] == SERVER_PAPER["title"]


# ------------------------------------------------------------- error mapping

def test_http_401_maps_to_auth_error() -> None:
    client, _ = make_client([FakeResponse(401, "invalid bearer token")])
    with pytest.raises(wms.McpAuthError, match="invalid bearer token"):
        client.call_tool("quick_search", {"query": "x"})


def test_business_error_40101_maps_to_auth_error() -> None:
    client, _ = make_client(_handshake_replies() + [
        FakeResponse(200, _rpc_result(3, _tool_text({"code": "40101", "message": "bad token"}, is_error=True))),
    ])
    with pytest.raises(wms.McpAuthError, match="40101"):
        client.call_tool("quick_search", {"query": "x"})


def test_parameter_error_40001_is_not_retried() -> None:
    client, transport = make_client(_handshake_replies() + [
        FakeResponse(200, _rpc_result(3, _tool_text(
            {"code": "40001", "message": "invalid parameter: top_n must be an integer between 1 and 100"},
            is_error=True))),
    ])
    with pytest.raises(wms.McpError, match="40001"):
        client.call_tool("quick_search", {"query": "x", "top_n": 0})
    assert [p.get("method") for p in transport.sent].count("tools/call") == 1


def test_rate_limit_42901_retries_with_backoff_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    sleeps: List[float] = []
    monkeypatch.setattr(wms.time, "sleep", lambda s: sleeps.append(s))
    client, transport = make_client(_handshake_replies() + [
        FakeResponse(200, _rpc_result(3, _tool_text({"code": "42901", "message": "slow down"}, is_error=True))),
        FakeResponse(200, _rpc_result(4, _tool_text(_ok_payload()))),
    ])
    client.call_tool("quick_search", {"query": "x"})
    assert len(sleeps) == 1 and sleeps[0] > 0
    assert [p.get("method") for p in transport.sent].count("tools/call") == 2


def test_jsonrpc_level_error_is_raised() -> None:
    body = json.dumps({"jsonrpc": "2.0", "id": 3, "error": {"code": -32602, "message": "Invalid params"}})
    client, _ = make_client(_handshake_replies() + [FakeResponse(200, body)])
    with pytest.raises(wms.McpError, match="Invalid params"):
        client.call_tool("quick_search", {"query": "x"})


def test_agent_error_events_surface_as_error() -> None:
    """The backend once reported deep_search failures as isError=false with the
    real cause buried in an onAgentError event. Fixed server-side, guarded here.
    """
    payload = {
        "events": [
            {"event": "onAgentStart", "data": {"error": None}},
            {"event": "onAgentError", "data": {"error": "Custom Error: Slug Agent failed"}},
        ],
        "session": {"run_id": "r"},
    }
    client, _ = make_client(_handshake_replies() + [FakeResponse(200, _rpc_result(3, _tool_text(payload)))])
    with pytest.raises(wms.McpError, match="Slug Agent failed"):
        client.call_tool("deep_search", {"query": "x"})


# ------------------------------------------------------------- request ident

def test_each_call_sends_a_dashscope_request_id_for_log_correlation() -> None:
    client, transport = make_client(_handshake_replies() + [
        FakeResponse(200, _rpc_result(3, _tool_text(_ok_payload()))),
    ])
    client.call_tool("quick_search", {"query": "x"})
    rid = transport.headers_seen[-1].get("X-DashScope-Request-ID")
    assert rid and len(rid) >= 8


def test_request_id_is_reported_in_the_error_message() -> None:
    client, _ = make_client(_handshake_replies() + [
        FakeResponse(200, _rpc_result(3, _tool_text({"code": "50001", "message": "boom"}, is_error=True))),
    ])
    with pytest.raises(wms.McpError) as exc:
        client.call_tool("quick_search", {"query": "x"})
    assert client.last_request_id and client.last_request_id in str(exc.value)


# -------------------------------------------------------------------- search

def test_search_passes_top_n_and_never_sends_legacy_paging() -> None:
    client, transport = make_client(_handshake_replies() + [
        FakeResponse(200, _rpc_result(3, _tool_text(_ok_payload()))),
    ])
    wms.search("q", topn=5, client=client)
    args = transport.last_args()
    assert args == {"query": "q", "top_n": 5}
    assert "page" not in args and "page_size" not in args


def test_search_defaults_to_ten_when_topn_is_omitted() -> None:
    client, transport = make_client(_handshake_replies() + [
        FakeResponse(200, _rpc_result(3, _tool_text(_ok_payload()))),
    ])
    wms.search("q", client=client)
    assert transport.last_args()["top_n"] == wms.DEFAULT_TOP_N == 10


@pytest.mark.parametrize("given,sent", [(0, 1), (-3, 1), (101, 100), (500, 100)])
def test_search_clamps_top_n_into_the_accepted_range(given: int, sent: int) -> None:
    """The server rejects out-of-range top_n with 40001; clamping spends one
    round trip on a usable answer instead of an error the caller cannot act on.
    """
    client, transport = make_client(_handshake_replies() + [
        FakeResponse(200, _rpc_result(3, _tool_text(_ok_payload()))),
    ])
    wms.search("q", topn=given, client=client)
    assert transport.last_args()["top_n"] == sent


def test_search_returns_server_papers_verbatim() -> None:
    """The ledger copies these records; re-deriving fields here would make the
    stored citation something other than what the search actually returned.
    """
    client, _ = make_client(_handshake_replies() + [
        FakeResponse(200, _rpc_result(3, _tool_text(_ok_payload()))),
    ])
    out = wms.search("q", topn=10, client=client)
    assert out["papers"] == [SERVER_PAPER]


def test_search_merges_server_stats_and_tags_the_backend() -> None:
    client, _ = make_client(_handshake_replies() + [
        FakeResponse(200, _rpc_result(3, _tool_text(_ok_payload()))),
    ])
    out = wms.search("q", topn=10, client=client)
    assert out["stats"]["total"] == 61
    assert out["stats"]["eligible_perfect_or_partial"] == 27
    assert out["stats"]["backend"] == "wis-mcp/quick_search"
    assert out["raw_path"] is None


def test_search_deep_tool_is_selectable() -> None:
    client, transport = make_client(_handshake_replies() + [
        FakeResponse(200, _rpc_result(3, _tool_text(_ok_payload()))),
    ])
    out = wms.search("q", topn=10, tool=wms.TOOL_DEEP, client=client)
    calls = [p for p in transport.sent if p.get("method") == "tools/call"]
    assert calls[-1]["params"]["name"] == "deep_search"
    assert out["stats"]["backend"] == "wis-mcp/deep_search"


def test_search_drops_untitled_records_and_counts_them() -> None:
    papers = [SERVER_PAPER, dict(SERVER_PAPER, title="  "), dict(SERVER_PAPER, title=None)]
    client, _ = make_client(_handshake_replies() + [
        FakeResponse(200, _rpc_result(3, _tool_text(_ok_payload(papers)))),
    ])
    out = wms.search("q", topn=10, client=client)
    assert len(out["papers"]) == 1
    assert out["stats"]["dropped_untitled"] == 2


def test_search_error_is_not_swallowed_into_an_empty_result() -> None:
    client, _ = make_client([FakeResponse(401, "invalid bearer token")])
    with pytest.raises(wms.McpAuthError):
        wms.search("q", topn=3, client=client)


def test_search_on_a_genuinely_empty_topic_returns_no_papers_without_raising() -> None:
    client, _ = make_client(_handshake_replies() + [
        FakeResponse(200, _rpc_result(3, _tool_text(_ok_payload([], total=0, kept=0, returned=0)))),
    ])
    out = wms.search("q", topn=10, client=client)
    assert out["papers"] == [] and out["stats"]["total"] == 0


# ----------------------------------------------------------------------- CLI

def _run_cli(args: List[str], cwd: str, env: Dict[str, str]) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, *args], cwd=cwd, env=env, capture_output=True, text=True)


def test_cli_fails_fast_without_credentials() -> None:
    with tempfile.TemporaryDirectory() as td:
        copy = Path(td) / "wis_mcp_search.py"
        shutil.copy(SCRIPT, copy)  # away from any .env next to the real script
        env = {k: v for k, v in os.environ.items() if not k.startswith("WIS_MCP")}
        env["PATH"] = os.environ.get("PATH", "")
        proc = _run_cli([str(copy), "q", "--topn", "2", "-q"], cwd=td, env=env)
    assert proc.returncode == 2
    assert "WIS_MCP_TOKEN" in proc.stderr and "WIS_MCP_URL" in proc.stderr
    assert proc.stdout.strip() == ""


def test_cli_rejects_a_legacy_page_flag_rather_than_ignoring_it() -> None:
    """`--page` was real in the previous API. Silently dropping it would hand
    back page 1 while the caller believed they were paging.
    """
    with tempfile.TemporaryDirectory() as td:
        copy = Path(td) / "wis_mcp_search.py"
        shutil.copy(SCRIPT, copy)
        env = {k: v for k, v in os.environ.items() if not k.startswith("WIS_MCP")}
        env["PATH"] = os.environ.get("PATH", "")
        proc = _run_cli([str(copy), "q", "--page", "2"], cwd=td, env=env)
    assert proc.returncode != 0
    assert "page" in proc.stderr.lower()
