import json
import logging
from typing import Any

import httpx
from bs4 import BeautifulSoup

from src.config import settings

log = logging.getLogger("job-hunter")


FIRECRAWL_API_URL = "https://api.firecrawl.dev/v1/scrape"
DUCKDUCKGO_HTML_URL = "https://html.duckduckgo.com/html/"


def web_search(query: str, max_results: int = 5) -> dict[str, Any]:
    """Search DuckDuckGo for *query* and return normalised results.

    Args:
        query: The search query.
        max_results: Maximum number of results to return (default 5).

    Returns:
        A dict with keys ``query``, ``results`` (list of dicts with
        ``title``, ``link``, ``snippet``), and optionally ``error``.
    """
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-GB,en;q=0.9",
        "Referer": "https://duckduckgo.com/",
    }

    try:
        resp = httpx.post(
            DUCKDUCKGO_HTML_URL,
            data={"q": query, "kl": "uk-en"},
            headers=headers,
            timeout=30,
            follow_redirects=True,
        )
        resp.raise_for_status()
    except Exception as exc:
        log.warning("web_search failed for %r: %s", query, exc)
        return {"query": query, "results": [], "error": str(exc)}

    soup = BeautifulSoup(resp.text, "html.parser")
    results: list[dict[str, str]] = []

    for item in soup.select(".result"):
        title_tag = item.select_one(".result__a")
        snippet_tag = item.select_one(".result__snippet")
        if not title_tag:
            continue

        link = title_tag.get("href", "")
        if link.startswith("/"):
            link = f"https://duckduckgo.com{link}"

        results.append(
            {
                "title": title_tag.get_text(strip=True),
                "link": link,
                "snippet": snippet_tag.get_text(strip=True) if snippet_tag else "",
            }
        )

    log.info("web_search returned %d result(s) for %r", len(results), query)
    return {"query": query, "results": results[:max_results]}


def deep_scrape(url: str, max_length: int = 8000) -> dict[str, Any]:
    """Extract clean markdown from *url*.

    Uses Firecrawl when ``FIRECRAWL_API_KEY`` is configured; otherwise
    falls back to a simple HTTP fetch and plain-text extraction so the
    pipeline never hard-crashes.

    Args:
        url: The webpage to scrape.
        max_length: Maximum characters of markdown to retain (default 8000).

    Returns:
        A dict with keys ``url``, ``markdown``, ``source`` (``firecrawl`` or
        ``http_fallback``), and optionally ``metadata`` or ``error``.
    """
    if settings.firecrawl_api_key:
        try:
            return _firecrawl_scrape(url, max_length)
        except Exception as exc:
            log.warning("Firecrawl scrape failed for %s: %s — falling back to HTTP", url, exc)

    try:
        return _http_fallback_scrape(url, max_length)
    except Exception as exc:
        log.warning("HTTP fallback scrape failed for %s: %s", url, exc)
        return {"url": url, "markdown": "", "source": "failed", "error": str(exc)}


def _firecrawl_scrape(url: str, max_length: int) -> dict[str, Any]:
    """Call the Firecrawl v1 scrape endpoint."""
    resp = httpx.post(
        FIRECRAWL_API_URL,
        headers={
            "Authorization": f"Bearer {settings.firecrawl_api_key}",
            "Content-Type": "application/json",
        },
        json={"url": url, "formats": ["markdown"]},
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()

    if not data.get("success"):
        error = data.get("error", "Unknown Firecrawl error")
        raise RuntimeError(error)

    markdown = data.get("data", {}).get("markdown", "")[:max_length]
    return {
        "url": url,
        "markdown": markdown,
        "metadata": data.get("data", {}).get("metadata", {}),
        "source": "firecrawl",
    }


def _http_fallback_scrape(url: str, max_length: int) -> dict[str, Any]:
    """Lightweight fallback that fetches the page and extracts text."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-GB,en;q=0.9",
    }

    resp = httpx.get(url, headers=headers, timeout=30, follow_redirects=True)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    for tag_name in ("script", "style", "nav", "footer", "header", "aside", "form"):
        for tag in soup.find_all(tag_name):
            tag.decompose()

    content = soup.find("article") or soup.find("main") or soup.find("body") or soup
    text = content.get_text(separator="\n", strip=True)
    lines = [line for line in text.splitlines() if line.strip()]
    markdown = "\n\n".join(lines)[:max_length]

    return {"url": url, "markdown": markdown, "source": "http_fallback"}
