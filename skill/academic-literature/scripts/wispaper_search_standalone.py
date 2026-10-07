#!/usr/bin/env python3
"""
Wispaper 学术搜索（从 wispaper_client 抽离，无 OAuth / rich / 项目 logger）。

依赖：pip install requests

配置：填写 TOKEN、BASE_URL。请求地址固定为 ``{BASE_URL}/api/v1/search/completions``。
环境变量：WISPAPER_BASE_URL；令牌可用 WISPAPER_TOKEN 或 WISPAPER_SEARCH_TOKEN。
脚本启动时会尝试加载同目录或当前工作目录下的 ``.env``（不覆盖已在环境中的变量）。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional

import requests

logger = logging.getLogger(__name__)


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
            if not s or s.startswith("#"):
                continue
            if "=" not in s:
                continue
            key, _, val = s.partition("=")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = val
        break


_load_dotenv()

# --- 凭证与网关地址全部从环境读取，脚本内绝不硬编码（AutoRepro 运行时铁律：不 hardcode host）---
# 运行时由 AutoRepro 注入当前用户的 token 和与 (env, region) 匹配的网关地址：
#   - WISPAPER_TOKEN（或 WISPAPER_SEARCH_TOKEN）：raw token，不带 Bearer 前缀，下游自行拼接。
#   - WISPAPER_BASE_URL：与当前环境/区域匹配的网关地址（区域差异由注入方处理，本脚本不做分支）。
# 本地调试时可经同目录 / 当前工作目录下的 .env 提供这两个变量。
# 两者缺失即 fail-fast（见 main / search），不把空 token 或空 host 传给上游。
TOKEN: str = os.environ.get("WISPAPER_TOKEN") or os.environ.get("WISPAPER_SEARCH_TOKEN", "")
BASE_URL: str = os.environ.get("WISPAPER_BASE_URL", "").rstrip("/")

# 流式 SSE 可能长时间无新字节，读超时放宽
REQUEST_TIMEOUT: tuple[int, int] = (30, 600)

SEARCH_COMPLETIONS_PATH = "/api/v1/search/completions"


def _effective_token(token: Optional[str] = None) -> str:
    return (token if token is not None else TOKEN) or ""


def _effective_base_url(base_url: Optional[str] = None) -> str:
    return (base_url if base_url is not None else BASE_URL).strip().rstrip("/")


def _search_endpoint(base_url: Optional[str] = None) -> str:
    """POST 地址固定为 ``{base}/api/v1/search/completions``。"""
    base = _effective_base_url(base_url)
    return f"{base}{SEARCH_COMPLETIONS_PATH}"


class SSEReader:
    """解析搜索接口返回的 SSE；无 rich 进度条，逻辑对齐原 SSEReader。"""

    def __init__(self, response: requests.Response, task_id: str = "Task") -> None:
        # 网关返回 ``text/event-stream`` 且不带 charset。HTTP 规范对 ``text/*`` 的默认
        # 字符集是 ISO-8859-1，requests 会据此把 UTF-8 正文按单字节 latin-1 解码；被拆散
        # 的多字节序列里会冒出虚假换行，把一条 SSE 事件切成多行，JSON 无法闭合而被整条
        # 丢弃。实测同一条查询：英文丢约 21% 的结果，中文丢近 100%（106 个 verification
        # 事件一个都没解析出来）。必须在 iter_lines 之前把编码定死。
        try:
            response.encoding = "utf-8"
        except AttributeError:  # 测试替身可能没有该属性
            pass
        self.response = response
        self.task_id = task_id

    @staticmethod
    def _strip_data_payload(s: str) -> str:
        """去掉 ``data:`` 行内载荷上的 PENDING/DONE 等前缀。"""
        t = (s or "").strip()
        t = t.removeprefix("[PENDING]:").strip()
        t = t.removeprefix("[DONE]").strip().strip(":")
        return t

    @staticmethod
    def _try_parse_parts(parts: List[str]) -> Optional[Dict[str, Any]]:
        """``parts`` 用换行拼接成一条 JSON；成功则清空 ``parts`` 并返回 dict。"""
        if not parts:
            return None
        try:
            data = json.loads("\n".join(parts))
        except json.JSONDecodeError:
            return None
        parts.clear()
        return data if isinstance(data, dict) else None

    def events(self) -> Iterator[Dict[str, Any]]:
        for data in self._gen_complete_json():
            if data.get("event") == "onAgentEnd" and data.get("name") == "verification":
                yield self._transform(data)

    def _gen_complete_json(self) -> Iterator[Dict[str, Any]]:
        """按 SSE 语义拼 JSON：同事件内多行 ``data:`` 用 ``\\n`` 拼接；空行结束事件。

        不带 ``data:`` 的行视为正在组装的 JSON 的续行（多行对象）。若上一轮尚未闭合，
        又来了新的 ``data:`` 且载荷以 ``{`` / ``[`` 开头，则丢弃上一轮（截断，从新对象起拼）。
        """
        parts: List[str] = []
        try:
            for line in self.response.iter_lines(decode_unicode=True):
                logger.info("SSE line: %s", line)
                if line is None:
                    continue
                if line.startswith(":"):
                    continue

                if line == "" or not line.strip():
                    parsed = self._try_parse_parts(parts)
                    if parsed is not None:
                        yield parsed
                    parts.clear()
                    continue

                if line.startswith("data:"):
                    payload = self._strip_data_payload(line[len("data:") :].lstrip())
                    if parts:
                        try:
                            json.loads("\n".join(parts))
                        except json.JSONDecodeError:
                            head = payload.lstrip()
                            if head.startswith("{") or head.startswith("["):
                                parts.clear()
                    if payload:
                        parts.append(payload)
                elif parts:
                    parts.append(line)

                parsed = self._try_parse_parts(parts) if parts else None
                if parsed is not None:
                    yield parsed

            parsed = self._try_parse_parts(parts)
            if parsed is not None:
                yield parsed
        except (requests.exceptions.ChunkedEncodingError, ConnectionError) as e:
            logger.warning("SSE read error [%s]: %s", self.task_id, e)

    def _transform(self, event: Dict[str, Any]) -> Dict[str, Any]:
        payload = event.get("data", {})
        md = payload.get("metadata", {}).copy()
        content = payload.get("content")
        if isinstance(content, str):
            try:
                md["_verdict"] = json.loads(content)
            except json.JSONDecodeError:
                md["_verdict"] = None
        elif isinstance(content, dict):
            md["_verdict"] = content
        return md


def map_item(md: Dict[str, Any], verdict: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """将原始 metadata 规范化为论文字典（原 _map_item）。"""
    try:
        title = (md.get("title") or "").strip()
        if not title:
            return None

        url = md.get("url") or md.get("source_url") or None
        pdf_url = md.get("pdf_url") or None
        abstract = (md.get("abstract") or "").strip()
        authors_field = md.get("authors") or ""
        if isinstance(authors_field, list):
            authors = [str(a).strip() for a in authors_field if str(a).strip()]
        else:
            parts = re.split(r"[,;]|\band\b", str(authors_field))
            authors = [p.strip() for p in parts if p and p.strip()]

        venue = md.get("venue") or md.get("conference_journal") or None
        year = md.get("year")
        try:
            year = int(year) if year is not None else None
        except Exception:
            year = None

        citations = md.get("citations") or md.get("cites") or 0
        try:
            if isinstance(citations, dict):
                citations = citations.get("count") or 0
            citations = int(citations)
        except Exception:
            citations = 0

        doi = md.get("doi")
        research_field = md.get("research_field")
        relevance = md.get("final_score") or md.get("relevance_score") or 0.0

        arxiv_id = None
        id_src = md.get("id") or md.get("url")
        if isinstance(id_src, str) and "arxiv" in id_src:
            m = re.search(r"arxiv\.org/(abs|pdf)/([\w.\-]+)", id_src)
            if m:
                arxiv_id = m.group(2)

        flags: Dict[str, Any] = {"perfect": False}
        if verdict and isinstance(verdict.get("criteria_assessment"), list):
            criteria = [a for a in verdict["criteria_assessment"] if isinstance(a, dict)]
            assessments = [a.get("assessment") for a in criteria]
            if assessments and all(a == "support" for a in assessments):
                flags = {"perfect": True, "partial": False, "no": False}
            elif len(criteria) == 1:
                if assessments[0] == "somewhat_support":
                    flags = {"perfect": False, "partial": True, "no": False}
                else:
                    flags = {"perfect": False, "partial": False, "no": True}
            elif any(
                a.get("assessment") in ("support", "somewhat_support") and a.get("type") != "time"
                for a in criteria
            ):
                flags = {"perfect": False, "partial": True, "no": False}
            else:
                flags = {"perfect": False, "partial": False, "no": True}

        return {
            "paper_id": None,
            "title": title,
            "authors": authors,
            "abstract": abstract,
            "url": url,
            "pdf_url": pdf_url,
            "venue": venue,
            "year": year,
            "citations": citations,
            "doi": doi,
            "arxiv_id": arxiv_id,
            "relevance_score": float(relevance) if isinstance(relevance, (int, float)) else 0.0,
            "research_field": research_field,
            "source_url": url,
            "flags": flags,
            "raw_metadata": md,
        }
    except Exception as e:
        logger.warning("Failed to map paper item: %s", e)
        return None


def _filter_sort_topn_perfect_partial(
    papers: List[Dict[str, Any]],
    topn: int,
) -> tuple[List[Dict[str, Any]], int]:
    """
    去掉 flags.no，仅保留 flags.perfect 或 flags.partial；
    排序：perfect 优先于 partial，同档按 relevance_score 从高到低；
    再取前 min(topn, 条数) 条。
    返回 (papers_slice, eligible_count)。
    """
    eligible: List[Dict[str, Any]] = []
    for p in papers:
        f = p.get("flags") or {}
        if f.get("no"):
            continue
        if not (f.get("perfect") or f.get("partial")):
            continue
        eligible.append(p)

    def sort_key(item: Dict[str, Any]) -> tuple:
        fl = item.get("flags") or {}
        perf = bool(fl.get("perfect"))
        part = bool(fl.get("partial"))
        rel = item.get("relevance_score") or 0.0
        try:
            rel_f = float(rel)
        except (TypeError, ValueError):
            rel_f = 0.0
        return (-int(perf), -int(part), -rel_f)

    eligible.sort(key=sort_key)
    cap = max(0, topn)
    return eligible[:cap], len(eligible)


def persist_raw(scope: str, query: str, payload: Any, debug_dir: Path) -> Path:
    """持久化原始 SSE 结果列表（原 _persist_raw）。"""
    debug_dir.mkdir(parents=True, exist_ok=True)
    qhash = hashlib.md5(query.encode("utf-8")).hexdigest()[:16]
    path = debug_dir / f"raw_{scope}_{qhash}.json"
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    except TypeError:
        with open(path, "w", encoding="utf-8") as f:
            f.write(str(payload))
    return path


def search(
    query: str,
    *,
    token: Optional[str] = None,
    base_url: Optional[str] = None,
    topn: Optional[int] = None,
    scope: str = "generic",
    debug_dir: Optional[Path] = None,
    session: Optional[requests.Session] = None,
) -> Dict[str, Any]:
    """
    执行学术搜索，返回与 search_structured 一致的结构：
    papers, stats{total, kept, dropped_parse, ...}, raw_path。

    topn：若给定正整数，则 papers 仅保留非 no 且（perfect 或 partial）的条目，
    先 perfect 再 partial，再按 relevance_score 降序，最后取 min(topn,  eligible 条数) 条。
    stats 在启用 topn 时会增加 eligible_perfect_or_partial、returned、topn。
    """
    tok = _effective_token(token)
    bu = _effective_base_url(base_url)
    endpoint = _search_endpoint(base_url)
    if not tok:
        logger.error("Missing token: set TOKEN or WISPAPER_TOKEN or pass token=")
        return {"papers": [], "stats": {"total": 0, "kept": 0, "dropped_parse": 0}, "raw_path": None}
    if not bu:
        logger.error("Missing base URL: set BASE_URL or WISPAPER_BASE_URL or pass base_url=")
        return {"papers": [], "stats": {"total": 0, "kept": 0, "dropped_parse": 0}, "raw_path": None}

    search_data = {
        "intention": "knowledge_qa",
        "message": query,
        "search_kb": False,
        "search_web": False,
        "slow_search": True,
        "search_scholar": True,
        "stream": False,
    }

    papers_raw: List[Dict[str, Any]] = []
    sess = session or requests.Session()
    headers = {
        "Authorization": f"Bearer {tok}",
        "Content-Type": "application/json",
    }

    try:
        logger.info("Searching: %s", query[:80])
        response = sess.post(
            endpoint,
            json=search_data,
            headers=headers,
            timeout=REQUEST_TIMEOUT,
            stream=True,
        )
        response.raise_for_status()
        papers_raw = list(SSEReader(response, task_id=query[:30]).events())
    except Exception as e:
        logger.error("Search failed: %s: %s", type(e).__name__, e)
        return {"papers": [], "stats": {"total": 0, "kept": 0, "dropped_parse": 0}, "raw_path": None}

    normalized: List[Dict[str, Any]] = []
    dropped_parse = 0
    for item in papers_raw:
        verdict_json = None
        if isinstance(item, dict) and isinstance(item.get("_verdict"), dict):
            verdict_json = item.get("_verdict")
        mapped = map_item(item, verdict_json)
        if mapped is not None:
            normalized.append(mapped)
        else:
            dropped_parse += 1

    raw_path: Optional[str] = None
    if debug_dir:
        try:
            raw_path = str(persist_raw(scope, query, papers_raw, Path(debug_dir)))
        except Exception as e:
            logger.debug("Failed to persist raw payload: %s", e)

    papers_out = normalized
    stats: Dict[str, Any] = {
        "total": len(papers_raw),
        "kept": len(normalized),
        "dropped_parse": dropped_parse,
    }
    if topn is not None:
        papers_out, elig = _filter_sort_topn_perfect_partial(normalized, topn)
        stats["topn"] = topn
        stats["eligible_perfect_or_partial"] = elig
        stats["returned"] = len(papers_out)

    return {
        "papers": papers_out,
        "stats": stats,
        "raw_path": raw_path,
    }


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Wispaper standalone search")
    parser.add_argument("query", nargs="?", default="machine learning", help="搜索查询")
    parser.add_argument("--debug-dir", type=Path, default=None, help="保存原始 SSE 解析结果目录")
    parser.add_argument(
        "--topn",
        type=int,
        default=None,
        metavar="N",
        help="只返回至多 N 条：去掉 no，仅 perfect/partial，perfect 优先，不足 N 则全返回",
    )
    parser.add_argument("-q", "--quiet", action="store_true", help="仅输出 JSON，不打印日志")
    parser.add_argument(
        "--raw",
        action="store_true",
        help="保留每篇的完整 raw_metadata（默认剔除，因为它占输出约 80%% 体积，"
        "会让结果动辄数十~上百 KB 而难以内联解析；完整原始数据也可用 --debug-dir 单独落盘）",
    )
    args = parser.parse_args()
    if args.quiet:
        logging.disable(logging.CRITICAL)

    # Fail-fast：缺凭证 / 网关时明确报错并以非零码退出，即便加了 -q 也照报到 stderr，
    # 避免上游把「未授权」误当成「没有搜到论文」。绝不把空 token / 空 host 发给上游。
    missing = []
    if not TOKEN:
        missing.append("WISPAPER_TOKEN（或 WISPAPER_SEARCH_TOKEN）")
    if not BASE_URL:
        missing.append("WISPAPER_BASE_URL")
    if missing:
        sys.stderr.write(
            "ERROR: 缺少 " + " 和 ".join(missing) + "：当前用户可能未授权 wispaper，"
            "或本地未在环境变量 / .env 中提供。无法发起搜索。\n"
        )
        sys.exit(2)

    result = search(args.query, debug_dir=args.debug_dir, topn=args.topn)
    # 默认剔除 raw_metadata：它是逐篇的完整 SSE 元数据，占输出约 80% 体积，
    # 调用方几乎用不到，却会把结果撑到数十~上百 KB、超出内联读取上限。
    # 需要时用 --raw 保留，或用 --debug-dir 把完整原始数据另存到文件。
    if not args.raw:
        for paper in result.get("papers", []):
            paper.pop("raw_metadata", None)
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
