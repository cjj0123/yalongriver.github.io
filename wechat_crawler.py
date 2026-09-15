#!/usr/bin/env python3
"""Safe adapter for crawling one public WeChat article.

The browser settings follow the public gxcsoccer/wechat-article-crawler
implementation: a MicroMessenger user agent, the WeChat referrer, dynamic
waiting for ``#js_content``, and lazy-image repair.  This module deliberately
does not attempt to solve CAPTCHA, login, or anti-bot interstitials.
"""

from __future__ import annotations

import json
import re
from typing import Any


WECHAT_USER_AGENT = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) "
    "Mobile/15E148 MicroMessenger/8.0.43"
)

WECHAT_SCHEMA = {
    "name": "wechat_article",
    "baseSelector": "#js_article",
    "fields": [
        {"name": "title", "selector": "#activity-name, h1.rich_media_title", "type": "text"},
        {"name": "author", "selector": "#js_name", "type": "text"},
        {"name": "publish_time", "selector": "#publish_time", "type": "text"},
        {"name": "content_html", "selector": "#js_content", "type": "html"},
        {"name": "account_desc", "selector": "#js_profile_desc", "type": "text"},
    ],
}

BLOCK_MARKERS = (
    "验证码",
    "安全验证",
    "访问过于频繁",
    "操作频繁",
    "环境异常",
    "请在微信客户端打开",
    "登录后查看",
    "page not found",
)


class WeChatCrawlerError(RuntimeError):
    """Raised when a page cannot be safely treated as an article."""


def _load_crawl4ai() -> tuple[Any, Any, Any, Any, Any]:
    try:
        from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig
        from crawl4ai.extraction_strategy import JsonCssExtractionStrategy
        from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator
    except ImportError as exc:
        raise WeChatCrawlerError(
            "缺少 crawl4ai；请先执行 python3.11 -m pip install crawl4ai "
            "并按其文档完成浏览器初始化。"
        ) from exc
    return (
        AsyncWebCrawler,
        BrowserConfig,
        CrawlerRunConfig,
        JsonCssExtractionStrategy,
        DefaultMarkdownGenerator,
    )


def _article_from_result(result: Any) -> dict[str, str]:
    extracted_content = getattr(result, "extracted_content", "") or "[]"
    try:
        metadata = json.loads(extracted_content)
    except (TypeError, ValueError) as exc:
        raise WeChatCrawlerError("公众号页面返回内容不是可解析的结构化文章。") from exc

    article = metadata[0] if isinstance(metadata, list) and metadata else {}
    markdown_result = getattr(result, "markdown", None)
    markdown = getattr(markdown_result, "raw_markdown", "") if markdown_result else ""
    html = article.get("content_html", "") or ""
    combined = "\n".join(
        str(article.get(key, "") or "") for key in ("title", "author", "publish_time")
    )
    combined = f"{combined}\n{html}\n{markdown}"
    if any(marker in combined for marker in BLOCK_MARKERS):
        raise WeChatCrawlerError("公众号页面出现验证码、登录或反爬提示，已安全跳过。")

    title = str(article.get("title", "") or "").strip()
    author = str(article.get("author", "") or "").strip()
    publish_time = str(article.get("publish_time", "") or "").strip()
    if not title or not html.strip() or not markdown.strip():
        raise WeChatCrawlerError("公众号页面内容不完整，未识别到可用正文。")

    return {
        "title": title,
        "author": author,
        "publish_time": publish_time,
        "html": html,
        "markdown": markdown,
        "url": str(getattr(result, "url", "") or "").strip(),
    }


async def crawl_wechat_article(url: str) -> dict[str, str]:
    """Fetch one direct ``mp.weixin.qq.com/s/...`` article.

    The caller must perform source/account/completeness validation before
    writing the article into the project's cache or database.
    """
    if not re.match(r"^https://mp\.weixin\.qq\.com/s(?:/|\?)", url):
        raise WeChatCrawlerError("只接受 https://mp.weixin.qq.com/s... 原始文章链接。")

    (
        AsyncWebCrawler,
        BrowserConfig,
        CrawlerRunConfig,
        JsonCssExtractionStrategy,
        DefaultMarkdownGenerator,
    ) = _load_crawl4ai()

    browser_config = BrowserConfig(
        user_agent=WECHAT_USER_AGENT,
        headers={
            "Referer": "https://mp.weixin.qq.com/",
            "Accept-Language": "zh-CN,zh;q=0.9",
        },
    )
    js_fix_lazy_images = """
    document.querySelectorAll('img[data-src]').forEach(img => {
        if (!img.src || img.src.startsWith('data:')) {
            img.src = img.getAttribute('data-src');
        }
    });
    """
    config = CrawlerRunConfig(
        wait_for="css:#js_content",
        js_code=js_fix_lazy_images,
        extraction_strategy=JsonCssExtractionStrategy(WECHAT_SCHEMA),
        markdown_generator=DefaultMarkdownGenerator(
            options={"ignore_links": False},
        ),
        word_count_threshold=10,
        remove_overlay_elements=True,
    )

    async with AsyncWebCrawler(config=browser_config) as crawler:
        result = await crawler.arun(url, config=config)
    return _article_from_result(result)
