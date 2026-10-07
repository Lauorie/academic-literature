#!/usr/bin/env python3
"""Standalone WisDoc PDF-to-Markdown MCP server and CLI.

This file is intentionally self-contained so a Cursor skill can copy it as-is.

Usage:
  python wisdoc_mcp_standalone.py serve
  python wisdoc_mcp_standalone.py parse --pdf-url https://example.com/paper.pdf
  python wisdoc_mcp_standalone.py parse --pdf-path ./paper.pdf --output-dir ./wisdoc_pdf_parse_result

Environment:
  WISDOCRS_BASE_URL       WisDoc service base URL. REQUIRED — injected at runtime
                          per (env, region), or set locally via env / a .env next
                          to the script or in the cwd. No host is hardcoded; the
                          tool fails fast if this is missing (AutoRepro spec §2).
  WISDOC_CANARY_HEADER    X-Canary header value, defaults to "grey".
  WISDOC_POLL_INTERVAL    Poll interval seconds, defaults to 5.
  WISDOC_POLL_TIMEOUT     Poll timeout seconds, defaults to 1200.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import mimetypes
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any

# No host/IP/port is hardcoded (AutoRepro spec §2): WISDOCRS_BASE_URL must come
# from the environment (runtime-injected per (env, region), or a local .env).
DEFAULT_CANARY_HEADER = "grey"
DEFAULT_OUTPUT_DIR = "wisdoc_pdf_parse_result"
MARKDOWN_PREVIEW_CHARS = 1500
INLINE_THRESHOLD_CHARS = 6000
MAX_ERROR_TEXT_LEN = 400
IMAGE_REF_RE = re.compile(r"!\[[^\]]*]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
HTML_IMG_RE = re.compile(r"(<img\b[^>]*\bsrc=[\"'])([^\"']+)([\"'][^>]*>)", re.IGNORECASE)

logger = logging.getLogger("wisdoc-standalone")


def _load_dotenv() -> None:
    """Inject vars from a ``.env`` next to the script or in the cwd (no override).

    Lets local runs supply WISDOCRS_BASE_URL without exporting it; the AutoRepro
    runtime injects the same var directly. No python-dotenv dependency.
    """
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


class WisDocError(RuntimeError):
    """Raised when WisDoc returns an invalid or failed response."""


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError as err:
        raise WisDocError(f"{name} must be a number, got {raw!r}") from err


def _base_url() -> str:
    base = (os.getenv("WISDOCRS_BASE_URL") or "").strip().rstrip("/")
    if not base:
        raise WisDocError(
            "WISDOCRS_BASE_URL missing — no host is hardcoded (AutoRepro spec §2). "
            "It is injected at runtime per (env, region); for local runs export it "
            "or put it in a .env next to the script or in the current directory."
        )
    return base


def _headers(extra: dict[str, str] | None = None) -> dict[str, str]:
    headers = {"X-Canary": os.getenv("WISDOC_CANARY_HEADER") or DEFAULT_CANARY_HEADER}
    if extra:
        headers.update(extra)
    return headers


def _compact_error_text(raw_text: str) -> str:
    text = " ".join(str(raw_text or "").split())
    if not text:
        return "unknown error"
    try:
        payload = json.loads(text)
        if isinstance(payload, dict):
            error_obj = payload.get("error")
            if isinstance(error_obj, dict):
                message = str(error_obj.get("message") or "").strip()
                if message:
                    text = message
    except Exception:
        pass
    if len(text) <= MAX_ERROR_TEXT_LEN:
        return text
    return text[:MAX_ERROR_TEXT_LEN].rstrip() + "..."


def _normalize_inputs(pdf_url: str | None, pdf_path: str | None) -> tuple[str | None, str | None]:
    url = (pdf_url or "").strip()
    path = (pdf_path or "").strip()
    if bool(url) == bool(path):
        raise ValueError("Provide exactly one of pdf_url or pdf_path.")
    if url and _looks_like_local_path(url):
        raise ValueError("pdf_url looks like a local path. Use pdf_path instead.")
    if path and _looks_like_remote_uri(path):
        raise ValueError("pdf_path looks like a remote URI. Use pdf_url instead.")
    return url or None, path or None


def _looks_like_local_path(value: str) -> bool:
    text = value.strip()
    lower = text.lower()
    return (
        lower.startswith("file://")
        or text.startswith(("~", "./", "../", ".\\", "..\\"))
        or (len(text) >= 3 and text[0].isalpha() and text[1] == ":" and text[2] in "\\/")
        or text.startswith("\\\\")
        or (text.startswith("/") and not text.startswith("//"))
    )


def _looks_like_remote_uri(value: str) -> bool:
    text = value.strip()
    lower = text.lower()
    return lower.startswith(
        ("file://", "http://", "https://", "s3://", "s3a://", "s3n://", "gs://", "ftp://", "sftp://")
    ) or text.startswith("//")


def _multipart_body(
    fields: dict[str, str],
    files: dict[str, tuple[str, bytes, str]],
) -> tuple[bytes, str]:
    boundary = f"----wisdoc-{uuid.uuid4().hex}"
    chunks: list[bytes] = []
    for name, value in fields.items():
        chunks.extend([
            f"--{boundary}\r\n".encode(),
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
            value.encode("utf-8"),
            b"\r\n",
        ])
    for name, (filename, content, content_type) in files.items():
        chunks.extend([
            f"--{boundary}\r\n".encode(),
            (
                f'Content-Disposition: form-data; name="{name}"; '
                f'filename="{filename}"\r\n'
            ).encode(),
            f"Content-Type: {content_type}\r\n\r\n".encode(),
            content,
            b"\r\n",
        ])
    chunks.append(f"--{boundary}--\r\n".encode())
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def _request_json(method: str, url: str, *, body: bytes | None = None, headers: dict[str, str] | None = None) -> Any:
    request = urllib.request.Request(url, data=body, headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as err:
        text = err.read().decode("utf-8", errors="replace")
        raise WisDocError(f"HTTP {err.code}: {_compact_error_text(text)}") from err


def _request_text(url: str) -> str:
    request = urllib.request.Request(url, headers=_headers(), method="GET")
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.read().decode("utf-8")
    except urllib.error.HTTPError as err:
        text = err.read().decode("utf-8", errors="replace")
        raise WisDocError(f"HTTP {err.code}: {_compact_error_text(text)}") from err


def _request_bytes(url: str) -> tuple[bytes, str]:
    request = urllib.request.Request(url, headers=_headers(), method="GET")
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            content_type = response.headers.get_content_type() or "application/octet-stream"
            return response.read(), content_type
    except urllib.error.HTTPError as err:
        text = err.read().decode("utf-8", errors="replace")
        raise WisDocError(f"HTTP {err.code}: {_compact_error_text(text)}") from err


def _submit_pdf_url(pdf_url: str, *, no_cache: bool) -> str:
    fields = {"oss_path": pdf_url}
    if no_cache:
        fields["no_cache"] = "true"
    body, content_type = _multipart_body(fields, {})
    response = _request_json(
        "POST",
        f"{_base_url()}/api/v2/documents",
        body=body,
        headers=_headers({"Content-Type": content_type}),
    )
    return _extract_job_id(response)


def _submit_pdf_path(pdf_path: str, *, no_cache: bool) -> str:
    path = Path(pdf_path).expanduser().resolve(strict=True)
    if path.suffix.lower() != ".pdf":
        raise ValueError(f"pdf_path must end with .pdf, got {path.name!r}")
    content_type = mimetypes.guess_type(path.name)[0] or "application/pdf"
    fields = {"no_cache": "true"} if no_cache else {}
    body, multipart_type = _multipart_body(
        fields,
        {"file": (path.name, path.read_bytes(), content_type)},
    )
    response = _request_json(
        "POST",
        f"{_base_url()}/api/v2/documents",
        body=body,
        headers=_headers({"Content-Type": multipart_type}),
    )
    return _extract_job_id(response)


def _extract_job_id(response: Any) -> str:
    if not isinstance(response, dict):
        raise WisDocError(f"WisDoc submit returned non-object body: {response!r}")
    job_id = str(response.get("job_id") or "").strip()
    if not job_id:
        raise WisDocError(f"WisDoc submit returned no job_id: {response}")
    logger.info("submitted job_id=%s", job_id)
    return job_id


def _poll_until_done(job_id: str) -> dict[str, Any]:
    interval = _env_float("WISDOC_POLL_INTERVAL", 5.0)
    timeout = _env_float("WISDOC_POLL_TIMEOUT", 20 * 60.0)
    endpoint = f"{_base_url()}/api/v2/documents/{job_id}"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        body = _request_json("GET", endpoint, headers=_headers())
        task_status = body.get("task_status") if isinstance(body, dict) else None
        if isinstance(task_status, dict) and task_status.get("ready"):
            if not task_status.get("successful"):
                raise WisDocError(
                    f"WisDoc job failed job_id={job_id} "
                    f"status={task_status.get('status')!r} info={task_status.get('info')!r}"
                )
            return body
        logger.info("polling job_id=%s status=%s", job_id, task_status)
        time.sleep(interval)
    raise TimeoutError(f"WisDoc job timed out after {int(timeout)}s job_id={job_id}")


def _persist_markdown(output_dir: str | Path, job_id: str, markdown: str) -> tuple[Path, Path]:
    target_dir = Path(output_dir).expanduser().resolve(strict=False)
    target_dir.mkdir(parents=True, exist_ok=True)
    assets_dir = target_dir / f"{job_id}_assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    final_path = target_dir / f"{job_id}.md"
    tmp_path = target_dir / f"{job_id}.md.tmp"
    tmp_path.write_text(markdown, encoding="utf-8")
    os.replace(tmp_path, final_path)
    return final_path, assets_dir


def _is_downloadable_asset_url(url: str) -> bool:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme in ("http", "https"):
        return True
    return not parsed.scheme and not url.startswith(("#", "data:"))


def _asset_filename(url: str, index: int, content_type: str = "") -> str:
    parsed = urllib.parse.urlparse(url)
    raw_name = Path(urllib.parse.unquote(parsed.path)).name
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", raw_name).strip("._")
    if not name:
        guessed_ext = mimetypes.guess_extension(content_type.split(";")[0].strip()) or ".bin"
        name = f"asset_{index}{guessed_ext}"
    if "." not in name:
        guessed_ext = mimetypes.guess_extension(content_type.split(";")[0].strip())
        if guessed_ext:
            name += guessed_ext
    return f"{index:03d}_{name}"


def _download_markdown_assets(markdown: str, markdown_url: str, assets_dir: Path) -> tuple[str, list[Path]]:
    assets_dir.mkdir(parents=True, exist_ok=True)
    downloaded: list[Path] = []
    url_to_local: dict[str, str] = {}

    def localize_url(raw_url: str) -> str:
        url = raw_url.strip()
        if not _is_downloadable_asset_url(url):
            return raw_url
        absolute_url = urllib.parse.urljoin(markdown_url, url)
        if absolute_url not in url_to_local:
            try:
                content, content_type = _request_bytes(absolute_url)
            except Exception as err:
                logger.warning("failed to download markdown asset url=%s error=%s", absolute_url, err)
                return raw_url
            filename = _asset_filename(absolute_url, len(url_to_local) + 1, content_type)
            target_path = assets_dir / filename
            target_path.write_bytes(content)
            downloaded.append(target_path)
            url_to_local[absolute_url] = f"{assets_dir.name}/{filename}"
        return url_to_local[absolute_url]

    def replace_markdown_image(match: re.Match[str]) -> str:
        original = match.group(0)
        original_url = match.group(1)
        return original.replace(original_url, localize_url(original_url), 1)

    def replace_html_image(match: re.Match[str]) -> str:
        return f"{match.group(1)}{localize_url(match.group(2))}{match.group(3)}"

    markdown = IMAGE_REF_RE.sub(replace_markdown_image, markdown)
    markdown = HTML_IMG_RE.sub(replace_html_image, markdown)
    return markdown, downloaded


def _build_payload(
    job_id: str,
    markdown_url: str,
    markdown: str,
    markdown_path: Path,
    assets_dir: Path,
    assets: list[Path],
) -> dict[str, Any]:
    digest = hashlib.sha256(markdown.encode("utf-8")).hexdigest()
    preview = markdown[:MARKDOWN_PREVIEW_CHARS]
    if len(markdown) > MARKDOWN_PREVIEW_CHARS:
        preview += "\n...[truncated]"
    payload: dict[str, Any] = {
        "job_id": job_id,
        "markdown_url": markdown_url,
        "markdown_path": str(markdown_path),
        "assets_dir": str(assets_dir),
        "assets": [str(path) for path in assets],
        "asset_count": len(assets),
        "markdown_len": len(markdown),
        "markdown_sha256": digest,
        "preview": preview,
        "inlined": len(markdown) <= INLINE_THRESHOLD_CHARS,
    }
    if payload["inlined"]:
        payload["markdown"] = markdown
    return payload


def parse_pdf_to_markdown(
    *,
    pdf_url: str | None = None,
    pdf_path: str | None = None,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    no_cache: bool = False,
) -> dict[str, Any]:
    """Parse one PDF through WisDoc and persist the Markdown to output_dir."""
    normalized_url, normalized_path = _normalize_inputs(pdf_url, pdf_path)
    job_id = (
        _submit_pdf_url(normalized_url, no_cache=no_cache)
        if normalized_url
        else _submit_pdf_path(normalized_path or "", no_cache=no_cache)
    )
    result = _poll_until_done(job_id)
    metadata = result.get("metadata") if isinstance(result, dict) else None
    markdown_url = str((metadata or {}).get("markdown_url") or "").strip()
    if not markdown_url:
        raise WisDocError(f"WisDoc job completed but no markdown_url in metadata: {metadata}")
    markdown = _request_text(markdown_url)
    target_dir = Path(output_dir).expanduser().resolve(strict=False)
    assets_dir = target_dir / f"{job_id}_assets"
    markdown, assets = _download_markdown_assets(markdown, markdown_url, assets_dir)
    markdown_path, assets_dir = _persist_markdown(output_dir, job_id, markdown)
    return _build_payload(job_id, markdown_url, markdown, markdown_path, assets_dir, assets)


def _run_mcp_server() -> None:
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as err:
        raise SystemExit("The 'mcp' package is required for serve mode. Install with: pip install mcp") from err

    server = FastMCP("wisdoc-parse")

    @server.tool()
    async def pdf_to_markdown(
        pdf_url: str = "",
        pdf_path: str = "",
        output_dir: str = DEFAULT_OUTPUT_DIR,
        no_cache: bool = False,
    ) -> str:
        """Parse a PDF with WisDoc and return a JSON envelope pointing at the Markdown file."""
        payload = await asyncio.to_thread(
            parse_pdf_to_markdown,
            pdf_url=pdf_url,
            pdf_path=pdf_path,
            output_dir=output_dir,
            no_cache=no_cache,
        )
        return json.dumps(payload, ensure_ascii=False)

    server.run()


def _parse_cli(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Standalone WisDoc MCP server and CLI")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("serve", help="Run stdio MCP server")

    parse_cmd = subparsers.add_parser("parse", help="Parse one PDF and print JSON result")
    parse_cmd.add_argument("--pdf-url", default="", help="Public PDF URL or WisDoc oss_path")
    parse_cmd.add_argument("--pdf-path", default="", help="Local .pdf path")
    parse_cmd.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR, help="Markdown output directory")
    parse_cmd.add_argument("--no-cache", action="store_true", help="Force WisDoc to re-parse")
    parse_cmd.add_argument("--pretty", action="store_true", help="Pretty-print JSON")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=os.getenv("WISDOC_LOG_LEVEL", "INFO"))
    args = _parse_cli(argv)
    if args.command in (None, "serve"):
        _run_mcp_server()
        return 0
    payload = parse_pdf_to_markdown(
        pdf_url=args.pdf_url,
        pdf_path=args.pdf_path,
        output_dir=args.output_dir,
        no_cache=args.no_cache,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2 if args.pretty else None))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
