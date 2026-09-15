#!/usr/bin/env python3
"""Discover WeChat article URLs through the Sogou Weixin MCP server.

The upstream project exposes one stdio MCP tool, so this module speaks the
small JSON-RPC subset needed by the scheduled scraper.  It deliberately uses
the search result only as URL metadata; article content is still fetched and
validated by :mod:`wechat_crawler` before anything reaches the database.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
from typing import Any


SOGOU_REPOSITORY = (
    "git+https://github.com/ptbsare/sogou-weixin-mcp-server.git"
    "@27b3df626b772ecb752a8b2f11de2f73aa10cf01"
)
SOGOU_ENTRYPOINT = "sogou-weixin-mcp-server"
DEFAULT_QUERY = "纬班长 雅砻江"
DEFAULT_TOP_NUM = 18
WECHAT_URL_RE = re.compile(r"^https://mp\.weixin\.qq\.com/s(?:/|\?)")


class SogouDiscoveryError(RuntimeError):
    """Raised when the Sogou MCP server cannot be queried safely."""


def _uvx_path() -> str:
    configured = os.environ.get("SOGOU_MCP_UVX", "").strip()
    if configured:
        return configured
    return shutil.which("uvx") or "/Users/jijunchen/.local/bin/uvx"


def _cache_dir() -> str:
    configured = os.environ.get("UV_CACHE_DIR", "").strip()
    if configured:
        return configured
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), ".cache", "uv")


async def _read_json_message(reader: asyncio.StreamReader, timeout: float) -> dict[str, Any]:
    while True:
        try:
            line = await asyncio.wait_for(reader.readline(), timeout=timeout)
        except asyncio.TimeoutError as exc:
            raise SogouDiscoveryError("Sogou MCP 响应超时") from exc
        if not line:
            raise SogouDiscoveryError("Sogou MCP 进程提前退出")
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            # The MCP server should write JSON to stdout. Ignore a stray
            # diagnostic line rather than treating it as article content.
            continue
        if isinstance(message, dict):
            return message


async def _send_json_message(writer: asyncio.StreamWriter, message: dict[str, Any]) -> None:
    writer.write((json.dumps(message, ensure_ascii=False) + "\n").encode("utf-8"))
    await writer.drain()


async def _request(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    request_id: int,
    method: str,
    params: dict[str, Any],
    timeout: float,
) -> dict[str, Any]:
    await _send_json_message(
        writer,
        {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params},
    )
    while True:
        message = await _read_json_message(reader, timeout)
        if message.get("id") != request_id:
            continue
        if "error" in message:
            raise SogouDiscoveryError(f"Sogou MCP {method} 失败: {message['error']}")
        result = message.get("result")
        if not isinstance(result, dict):
            raise SogouDiscoveryError(f"Sogou MCP {method} 返回格式异常")
        return result


def _articles_from_result(result: dict[str, Any]) -> list[dict[str, str]]:
    """Decode both MCP structuredContent and the server's text blocks."""
    candidates: list[Any] = []
    structured = result.get("structuredContent")
    if isinstance(structured, dict) and isinstance(structured.get("result"), list):
        candidates.extend(structured["result"])

    for block in result.get("content", []):
        if not isinstance(block, dict) or block.get("type") != "text":
            continue
        try:
            decoded = json.loads(block.get("text", ""))
        except (TypeError, json.JSONDecodeError):
            continue
        if isinstance(decoded, dict):
            candidates.append(decoded)
        elif isinstance(decoded, list):
            candidates.extend(decoded)

    articles: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for item in candidates:
        if not isinstance(item, dict):
            continue
        article = {
            key: str(item.get(key, "") or "").strip()
            for key in ("title", "snippet", "url", "source", "date")
        }
        if not WECHAT_URL_RE.match(article["url"]):
            continue
        if "纬班长" not in article["source"]:
            continue
        if "雅砻江" not in f"{article['title']} {article['snippet']}":
            continue
        fingerprint = (article["title"], article["date"], article["url"])
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        articles.append(article)
    return articles


async def _search(query: str, top_num: int, timeout: float) -> list[dict[str, str]]:
    env = os.environ.copy()
    env["UV_CACHE_DIR"] = _cache_dir()
    process = await asyncio.create_subprocess_exec(
        _uvx_path(),
        "--from",
        SOGOU_REPOSITORY,
        "--with",
        "mcp<2",
        SOGOU_ENTRYPOINT,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )
    try:
        if process.stdin is None or process.stdout is None:
            raise SogouDiscoveryError("Sogou MCP stdio 管道初始化失败")
        await _request(
            process.stdout,
            process.stdin,
            1,
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "yalongriver-scraper", "version": "1.0"},
            },
            timeout,
        )
        await _send_json_message(
            process.stdin,
            {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
        )
        result = await _request(
            process.stdout,
            process.stdin,
            2,
            "tools/call",
            {
                "name": "search_wechat_articles",
                "arguments": {"query": query, "top_num": top_num},
            },
            timeout,
        )
        return _articles_from_result(result)
    finally:
        if process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=5)
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
        if process.stderr is not None:
            await process.stderr.read()


def search_wechat_articles(
    query: str | None = None,
    top_num: int | None = None,
    timeout: float = 45,
) -> list[dict[str, str]]:
    """Search and return only validated 纬班长 Yalong WeChat URL results."""
    query = (query or os.environ.get("WECHAT_DISCOVERY_QUERY", DEFAULT_QUERY)).strip()
    if not query:
        return []
    if top_num is None:
        top_num = int(os.environ.get("WECHAT_DISCOVERY_TOP_NUM", str(DEFAULT_TOP_NUM)))
    top_num = max(1, min(top_num, 50))
    return asyncio.run(_search(query, top_num, timeout))


def discover_wechat_articles() -> list[dict[str, str]]:
    """Return fresh validated article metadata, or an empty list when disabled."""
    enabled = os.environ.get("WECHAT_AUTO_DISCOVER", "1").strip().lower()
    if enabled in {"0", "false", "no", "off"}:
        return []
    return search_wechat_articles()


def discover_wechat_article_urls() -> list[str]:
    """Return fresh original URLs, or an empty list when discovery is disabled."""
    articles = discover_wechat_articles()
    urls: list[str] = []
    seen: set[str] = set()
    for article in articles:
        url = article["url"]
        if url not in seen:
            seen.add(url)
            urls.append(url)
    return urls
