#!/usr/bin/env python3
"""Wispaper 学术检索 —— MCP 版（wis-scholar-search，Streamable HTTP）。

取代 ``wispaper_search_standalone.py`` 对 ``/api/v1/search/completions`` 的 SSE 直连：
CLI 与输出 JSON schema 保持一致（``query --topn N -q --debug-dir``），传输层换成标准
MCP 会话：``initialize`` → ``notifications/initialized`` → ``tools/call``。

服务端 v0.1（top_n API）已经按本 skill 的 schema 返回论文，所以脚本原样带出
``papers``——ledger 随后逐字拷贝这些记录，任何"顺手补全"都会让台账里的引用不再等于
检索真正返回的东西。

依赖：pip install requests

环境变量（缺任一即 fail-fast，绝不硬编码 host / token）：
  WIS_MCP_URL        MCP 端点，如 https://<host>/api/v1/mcp
  WIS_MCP_TOKEN      Bearer token（raw，不带 "Bearer " 前缀）
  WIS_MCP_CONSUMER   可选；网关要求 X-Mse-Consumer 时填实例 ID
脚本启动时加载同目录或当前工作目录下的 ``.env``（不覆盖已在环境中的变量）。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)

PROTOCOL_VERSION = "2025-03-26"
DEFAULT_TOP_N = 10
MIN_TOP_N = 1
MAX_TOP_N = 100
REQUEST_TIMEOUT: tuple[int, int] = (30, 600)
MAX_RETRIES = 3
BACKOFF_BASE_SECONDS = 2.0
CLIENT_INFO = {"name": "wis-mcp-search", "version": "0.2"}

TOOL_QUICK = "quick_search"
TOOL_DEEP = "deep_search"

# 业务错误码（见《MCP 远端功能测试说明 v0.2》第 7 节）
CODE_PARAM = "40001"
CODE_DOWNSTREAM = "40002"
CODE_AUTH = "40101"
CODE_RATE_LIMIT = "42901"
CODE_SYSTEM = "50001"


def _load_dotenv() -> None:
    """从 ``.env`` 注入环境变量（不覆盖已设置的项）；无 python-dotenv 依赖。"""
    for candidate in (Path(__file__).resolve().parent / ".env", Path.cwd() / ".env"):
        if not candidate.is_file():
            continue
        try:
            text = candidate.read_text(encoding="utf-8")
        except OSError:
            continue
        for line in text.splitlines():
            s = line.strip()
            if not s or s.startswith("#") or "=" not in s:
                continue
            key, _, val = s.partition("=")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = val
        break


_load_dotenv()


class McpError(RuntimeError):
    """协议层或业务层错误；绝不静默成空结果。"""


class McpAuthError(McpError):
    """鉴权失败（HTTP 401 或业务码 40101）。"""


class McpRateLimited(McpError):
    """限流（HTTP 429 或业务码 42901），重试耗尽后抛出。"""


PostFn = Callable[[Dict[str, Any], Dict[str, str]], Any]


def _decode_body(resp: Any) -> str:
    """把响应正文按 UTF-8 取出。

    ``text/event-stream`` 不带 charset，requests 依 RFC 2616 按 ISO-8859-1 解码；
    UTF-8 中文里凡含字节 ``0x85`` 的字（如"先"= E5 85 88）会变成 U+0085(NEL)，而
    ``str.splitlines()`` 把 NEL 当换行——一条 SSE 事件被切碎，JSON 再也闭合不了。
    实测 ``tools/list`` 的中文工具描述就会踩中。所以一律从 ``content`` 解 UTF-8。
    """
    raw = getattr(resp, "content", None)
    if isinstance(raw, (bytes, bytearray)):
        return raw.decode("utf-8", errors="replace")
    return getattr(resp, "text", "") or ""


def _parse_sse_or_json(text: str) -> Optional[Dict[str, Any]]:
    """响应可能是纯 JSON，也可能是 SSE；取最后一条完整的 JSON-RPC 消息。

    按 SSE 规范，一个事件可以有多行 ``data:``，以空行结束。只在真正的 ``\\n`` 上
    切行——绝不用 ``splitlines()``，它还会在 NEL / LS / PS 等字符上断开。
    """
    body = (text or "").strip()
    if not body:
        return None
    if body.startswith("{"):
        return json.loads(body)

    last: Optional[Dict[str, Any]] = None
    pending: List[str] = []

    def flush() -> None:
        nonlocal last, pending
        if not pending:
            return
        for joiner in ("\n", ""):  # 规范用 \n；有网关直接按字节切块，退回无缝拼接
            try:
                msg = json.loads(joiner.join(pending))
            except json.JSONDecodeError:
                continue
            if isinstance(msg, dict):
                last = msg
            break
        pending = []

    for line in body.split("\n"):
        line = line.rstrip("\r")
        if line.startswith("data:"):
            pending.append(line[5:].lstrip())
        elif not line.strip():
            flush()
    flush()
    return last


def clamp_top_n(value: Optional[int]) -> int:
    """把 ``top_n`` 夹进服务端接受的 1~100。

    越界服务端回 40001，那是一次白花的往返和一个调用方无从处置的错误；夹住则换回
    一份可用结果。夹取会记进 stats（``top_n_requested``），不静默。
    """
    try:
        n = int(value) if value is not None else DEFAULT_TOP_N
    except (TypeError, ValueError):
        n = DEFAULT_TOP_N
    return max(MIN_TOP_N, min(n, MAX_TOP_N))


class McpClient:
    """最小 Streamable HTTP MCP 客户端：只做本 skill 需要的 tools/call。

    ``post`` 可注入（测试用）；默认用一个 ``requests.Session``，保住网关下发的
    SERVERID cookie，让同一 MCP 会话始终落到同一后端实例。
    """

    def __init__(
        self,
        url: str,
        token: str,
        consumer: Optional[str] = None,
        post: Optional[PostFn] = None,
        timeout: tuple[int, int] = REQUEST_TIMEOUT,
        max_retries: int = MAX_RETRIES,
    ) -> None:
        self.url = url.strip()
        self.token = token.strip()
        self.consumer = (consumer or "").strip() or None
        self.timeout = timeout
        self.max_retries = max_retries
        self.session_id: Optional[str] = None
        self.last_request_id: Optional[str] = None
        self._next_id = 1
        self._post: PostFn = post or self._default_post
        self._http: Optional[requests.Session] = None

    # ------------------------------------------------------------ transport
    def _default_post(self, payload: Dict[str, Any], headers: Dict[str, str]) -> requests.Response:
        if self._http is None:
            self._http = requests.Session()
        return self._http.post(self.url, json=payload, headers=headers, timeout=self.timeout)

    def _headers(self, request_id: Optional[str] = None) -> Dict[str, str]:
        h = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if self.session_id:
            h["Mcp-Session-Id"] = self.session_id
        if self.consumer:
            h["X-Mse-Consumer"] = self.consumer
        if request_id:
            # 服务端原值回显该头，是把客户端日志与网关/服务端日志对上的唯一线索。
            h["X-DashScope-Request-ID"] = request_id
        return h

    def _rpc(
        self,
        method: str,
        params: Optional[Dict[str, Any]] = None,
        notify: bool = False,
        request_id: Optional[str] = None,
    ) -> Any:
        payload: Dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            payload["params"] = params
        if not notify:
            payload["id"] = self._next_id
            self._next_id += 1
        resp = self._post(payload, self._headers(request_id))
        status = int(getattr(resp, "status_code", 0))
        text = _decode_body(resp)
        where = f" [request-id {request_id}]" if request_id else ""
        if status == 401:
            raise McpAuthError(f"HTTP 401: {text.strip()[:200] or 'unauthorized'}{where}")
        if status == 404 and self.session_id:
            # Streamable HTTP：会话过期时服务端回 404，须重新 initialize。
            self.session_id = None
            raise McpError("HTTP 404: MCP session expired")
        if status == 429:
            raise McpRateLimited(f"HTTP 429: {text.strip()[:200]}{where}")
        if status >= 400:
            raise McpError(f"HTTP {status}: {text.strip()[:200]}{where}")
        if notify:
            return None
        msg = _parse_sse_or_json(text)
        if msg is None:
            raise McpError(f"{method}: empty or unparsable response body{where}")
        if "error" in msg:
            err = msg["error"] or {}
            raise McpError(f"{method}: JSON-RPC error {err.get('code')}: {err.get('message')}{where}")
        return msg.get("result"), getattr(resp, "headers", {}) or {}

    # -------------------------------------------------------------- session
    def _ensure_session(self) -> None:
        if self.session_id:
            return
        _, headers = self._rpc(
            "initialize",
            {"protocolVersion": PROTOCOL_VERSION, "capabilities": {}, "clientInfo": CLIENT_INFO},
        )
        sid = next((v for k, v in headers.items() if k.lower() == "mcp-session-id"), None)
        if not sid:
            raise McpError("initialize succeeded but no Mcp-Session-Id header was returned")
        self.session_id = str(sid).strip()
        self._rpc("notifications/initialized", notify=True)

    # ----------------------------------------------------------------- tools
    @staticmethod
    def _unwrap_tool_result(result: Any) -> tuple[Dict[str, Any], bool]:
        content = (result or {}).get("content") or []
        text = next((c.get("text") for c in content if c.get("type") == "text"), None)
        if text is None:
            raise McpError("tools/call returned no text content")
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise McpError(f"tools/call text is not JSON: {exc}") from exc
        return data, bool((result or {}).get("isError"))

    @staticmethod
    def _agent_error(data: Dict[str, Any]) -> Optional[str]:
        """后端曾把 deep_search 的失败报成 ``isError=false`` + ``onAgentError`` 事件
        （2026-09-20 实测，v0.1 已修）。留着这道检查：这种"成功外壳裹着失败"再回来
        时，静默返回零论文比报错更难查。
        """
        for ev in data.get("events") or []:
            if ev.get("event") == "onAgentError":
                err = (ev.get("data") or {}).get("error")
                return str(err or "agent error")
        return None

    def call_tool(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        last_exc: Optional[Exception] = None
        for attempt in range(self.max_retries):
            request_id = f"wis-mcp-{uuid.uuid4().hex[:16]}"
            self.last_request_id = request_id
            try:
                self._ensure_session()
                result, _ = self._rpc(
                    "tools/call", {"name": name, "arguments": arguments}, request_id=request_id
                )
            except McpRateLimited as exc:
                last_exc = exc
                time.sleep(BACKOFF_BASE_SECONDS * (2**attempt))
                continue
            except McpError as exc:
                if "session expired" in str(exc) and attempt + 1 < self.max_retries:
                    last_exc = exc
                    continue
                raise
            data, is_error = self._unwrap_tool_result(result)
            if is_error:
                code = str(data.get("code") or "")
                message = f"{name}: error {code}: {data.get('message')} [request-id {request_id}]"
                if code == CODE_AUTH:
                    raise McpAuthError(message)
                if code == CODE_RATE_LIMIT:
                    last_exc = McpRateLimited(message)
                    time.sleep(BACKOFF_BASE_SECONDS * (2**attempt))
                    continue
                # 40001/40002/50001：重试同一请求只会得到同一个错误，直接抛。
                raise McpError(message)
            if agent_err := self._agent_error(data):
                raise McpError(f"{name}: backend agent failed: {agent_err} [request-id {request_id}]")
            return data
        raise last_exc or McpError(f"{name}: retries exhausted")


# ------------------------------------------------------------------- search
def persist_raw(scope: str, query: str, payload: Any, debug_dir: Path) -> Path:
    debug_dir.mkdir(parents=True, exist_ok=True)
    digest = hashlib.md5(query.encode("utf-8")).hexdigest()[:10]
    path = debug_dir / f"{scope}_{digest}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def client_from_env() -> McpClient:
    url = os.environ.get("WIS_MCP_URL", "").strip()
    token = os.environ.get("WIS_MCP_TOKEN", "").strip()
    missing = [n for n, v in (("WIS_MCP_URL", url), ("WIS_MCP_TOKEN", token)) if not v]
    if missing:
        raise McpAuthError("缺少 " + " 和 ".join(missing))
    return McpClient(url=url, token=token, consumer=os.environ.get("WIS_MCP_CONSUMER"))


def search(
    query: str,
    topn: Optional[int] = None,
    tool: str = TOOL_QUICK,
    debug_dir: Optional[Path] = None,
    client: Optional[McpClient] = None,
) -> Dict[str, Any]:
    """检索并返回 ``{"papers": [...], "stats": {...}, "raw_path": ...}``。

    ``papers`` 原样来自服务端（v0.1 已按本 schema 返回），只丢掉没有标题的残记录。
    错误一律抛出（``McpAuthError`` / ``McpError``），绝不吞成空 ``papers``——调用方
    才能区分"没搜到"与"没搜成"。
    """
    top_n = clamp_top_n(topn)
    cli = client or client_from_env()
    data = cli.call_tool(tool, {"query": query, "top_n": top_n})
    raw_path = persist_raw(tool, query, data, debug_dir) if debug_dir else None

    raw_papers = [p for p in (data.get("papers") or []) if isinstance(p, dict)]
    papers = [p for p in raw_papers if str(p.get("title") or "").strip()]

    stats: Dict[str, Any] = dict(data.get("stats") or {})
    stats.update(
        {
            "returned": len(papers),
            "dropped_untitled": len(raw_papers) - len(papers),
            "top_n": top_n,
            "top_n_requested": topn,
            "backend": f"wis-mcp/{tool}",
            "request_id": cli.last_request_id,
        }
    )
    return {
        "papers": papers,
        "stats": stats,
        "raw_path": str(raw_path) if raw_path else data.get("raw_path"),
    }


# ---------------------------------------------------------------------- CLI
def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Wispaper search over MCP (wis-scholar-search)")
    parser.add_argument("query", nargs="?", default="machine learning", help="搜索查询（自然语言）")
    parser.add_argument("--topn", type=int, default=None, metavar="N",
                        help=f"返回至多 N 篇（{MIN_TOP_N}~{MAX_TOP_N}，默认 {DEFAULT_TOP_N}）")
    parser.add_argument("--tool", choices=[TOOL_QUICK, TOOL_DEEP], default=TOOL_QUICK,
                        help="quick_search（默认，快）或 deep_search（慢，只回 perfect/partial）")
    parser.add_argument("--debug-dir", type=Path, default=None, help="保存原始 MCP 响应的目录")
    parser.add_argument("-q", "--quiet", action="store_true", help="仅输出 JSON，不打印日志")
    args = parser.parse_args()
    if args.quiet:
        logging.disable(logging.CRITICAL)

    try:
        client = client_from_env()
    except McpAuthError as exc:
        sys.stderr.write(f"ERROR: {exc}：当前用户可能未授权 wis-scholar-search MCP，"
                         "或本地未在环境变量 / .env 中提供 WIS_MCP_URL 与 WIS_MCP_TOKEN。无法发起搜索。\n")
        sys.exit(2)
    try:
        result = search(args.query, topn=args.topn, tool=args.tool,
                        debug_dir=args.debug_dir, client=client)
    except McpAuthError as exc:
        sys.stderr.write(f"ERROR: MCP 鉴权失败（token 无效/过期，或实例已停用）：{exc}\n")
        sys.exit(3)
    except (McpError, requests.RequestException) as exc:
        sys.stderr.write(f"ERROR: MCP 检索失败：{exc}\n")
        sys.exit(1)

    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
