"""News fetcher integrating developer-focused sources: Hacker News, GitHub/Dev blogs, Dev.to, and arXiv."""

from __future__ import annotations

import os
import hashlib
import sqlite3
import logging
from datetime import datetime, timezone
import httpx
import feedparser

from state import NewsItem

logger = logging.getLogger(__name__)

SEEN_DB_PATH = "data/seen_stories.db"
DEFAULT_TIMEOUT = 10.0

# Developer learning & technical keywords
DEV_KEYWORDS = {
    "python", "typescript", "javascript", "react", "nextjs", "fastapi", "golang", "rust",
    "sqlite", "postgres", "redis", "docker", "kubernetes", "linux", "git", "github",
    "llm", "agent", "agents", "rag", "embeddings", "vllm", "ollama", "langchain", "langgraph",
    "architecture", "system design", "benchmark", "benchmarks", "optimization", "performance",
    "tutorial", "guide", "how-to", "how to", "deep dive", "postmortem", "debugging",
    "open source", "open-source", "library", "sdk", "api", "framework", "release", "releases",
    "deepseek", "mistral", "claude", "openai", "speculative decoding", "transformer", "fine-tuning",
    "prompt engineering", "context caching", "show hn", "developer", "engineering"
}

# Negative keywords to filter out business/finance/drama noise
EXCLUDE_KEYWORDS = {
    "funding", "valuation", "raised $", "seed round", "series a", "series b", "series c",
    "layoffs", "laid off", "lawsuit", "sued", "antitrust", "crypto", "bitcoin",
    "quarterly earnings", "revenue", "stocks", "shares jump", "ceo steps down",
    "ipo", "acquisition", "acquires", "billion acquisition"
}


def init_seen_db(db_path: str = SEEN_DB_PATH) -> None:
    """Initializes the SQLite deduplication database and table."""
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS seen_stories (
                url_hash TEXT PRIMARY KEY,
                url TEXT,
                title TEXT,
                seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.commit()


def hash_url(url: str) -> str:
    """Computes a SHA-256 hash of a normalized URL."""
    clean_url = url.strip().lower().rstrip("/")
    return hashlib.sha256(clean_url.encode("utf-8")).hexdigest()


def is_seen(url: str, db_path: str = SEEN_DB_PATH) -> bool:
    """Checks if a URL has already been processed in a prior run."""
    try:
        init_seen_db(db_path)
        url_h = hash_url(url)
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM seen_stories WHERE url_hash = ?", (url_h,))
            return cursor.fetchone() is not None
    except Exception as e:
        logger.warning("Error checking seen_stories database: %s", e)
        return False


def mark_seen(url: str, title: str, db_path: str = SEEN_DB_PATH) -> None:
    """Records a URL in the seen stories database."""
    try:
        init_seen_db(db_path)
        url_h = hash_url(url)
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                "INSERT OR IGNORE INTO seen_stories (url_hash, url, title) VALUES (?, ?, ?)",
                (url_h, url, title),
            )
            conn.commit()
    except Exception as e:
        logger.warning("Error saving to seen_stories database: %s", e)


def _is_relevant_developer_story(text: str) -> bool:
    """Checks if text contains developer/engineering learning concepts and excludes corporate fluff."""
    lower_text = text.lower()

    # Reject if it matches business/drama noise
    if any(ex in lower_text for ex in EXCLUDE_KEYWORDS):
        return False

    # Check for developer keywords
    words = set(lower_text.replace("-", " ").replace(":", " ").replace("/", " ").split())
    if words.intersection(DEV_KEYWORDS):
        return True

    return any(kw in lower_text for kw in [
        "system design", "how it works", "under the hood", "best practice", "open source",
        "speculative decoding", "context caching", "show hn", "prompt engineering"
    ])


def _contains_ai_keywords(text: str) -> bool:
    """Backwards-compatible helper for tests."""
    return _is_relevant_developer_story(text)


def fetch_hacker_news(limit: int = 50) -> list[NewsItem]:
    """Fetches top Hacker News stories filtered for developer learnings and tooling."""
    items: list[NewsItem] = []
    try:
        with httpx.Client(timeout=DEFAULT_TIMEOUT) as client:
            resp = client.get("https://hacker-news.firebaseio.com/v0/topstories.json")
            if resp.status_code != 200:
                logger.warning("HN API returned %d", resp.status_code)
                return []
            story_ids = resp.json()[:limit]

            for story_id in story_ids:
                try:
                    item_resp = client.get(f"https://hacker-news.firebaseio.com/v0/item/{story_id}.json")
                    if item_resp.status_code != 200:
                        continue
                    data = item_resp.json()
                    if not data or data.get("type") != "story":
                        continue

                    title = data.get("title", "")
                    url = data.get("url") or f"https://news.ycombinator.com/item?id={story_id}"
                    if _is_relevant_developer_story(title):
                        items.append({
                            "title": title,
                            "url": url,
                            "source": "Hacker News",
                            "summary": f"Technical discussion on Hacker News (score: {data.get('score', 0)}, comments: {data.get('descendants', 0)}).",
                            "published": datetime.fromtimestamp(data.get("time", 0), timezone.utc).isoformat(),
                        })
                except Exception as e:
                    logger.debug("Error fetching HN item %s: %s", story_id, e)
    except Exception as e:
        logger.warning("Failed to fetch Hacker News: %s", e)

    return items


def fetch_dev_to(per_page: int = 15) -> list[NewsItem]:
    """Fetches top practical engineering and AI tutorials from Dev.to."""
    items: list[NewsItem] = []
    tags = ["ai", "programming", "webdev", "architecture"]
    try:
        with httpx.Client(timeout=DEFAULT_TIMEOUT) as client:
            for tag in tags[:2]:
                resp = client.get(f"https://dev.to/api/articles?tag={tag}&top=1&per_page={per_page}")
                if resp.status_code != 200:
                    continue
                for art in resp.json():
                    title = art.get("title", "")
                    if _is_relevant_developer_story(title):
                        items.append({
                            "title": title,
                            "url": art.get("url", ""),
                            "source": "Dev.to",
                            "summary": art.get("description", "") or "Practical developer guide and learnings.",
                            "published": art.get("published_at", ""),
                        })
    except Exception as e:
        logger.warning("Failed to fetch Dev.to: %s", e)

    return items


def fetch_rss_feed(feed_url: str, source_name: str, max_items: int = 8) -> list[NewsItem]:
    """Fetches and normalizes an RSS feed filtered for developer relevance."""
    items: list[NewsItem] = []
    try:
        parsed = feedparser.parse(feed_url)
        for entry in parsed.entries[:max_items]:
            title = getattr(entry, "title", "")
            link = getattr(entry, "link", "")
            summary = getattr(entry, "summary", "") or getattr(entry, "description", "")
            clean_summary = summary.replace("<p>", "").replace("</p>", "").strip()
            published = getattr(entry, "published", "") or getattr(entry, "updated", "")
            if title and link and _is_relevant_developer_story(title + " " + clean_summary[:200]):
                items.append({
                    "title": title,
                    "url": link,
                    "source": source_name,
                    "summary": clean_summary[:400],
                    "published": published,
                })
    except Exception as e:
        logger.warning("Failed to fetch RSS %s (%s): %s", source_name, feed_url, e)

    return items


def fetch_arxiv(max_results: int = 6) -> list[NewsItem]:
    """Fetches practical AI/NLP engineering papers from arXiv."""
    url = (
        f"http://export.arxiv.org/api/query?search_query=cat:cs.AI+OR+cat:cs.CL"
        f"&sortBy=submittedDate&sortOrder=descending&max_results={max_results}"
    )
    return fetch_rss_feed(url, "arXiv Engineering", max_items=max_results)


def fetch_all(db_path: str = SEEN_DB_PATH, deduplicate: bool = True) -> list[NewsItem]:
    """Runs developer-centric source fetchers, combines results, and dedupes."""
    all_items: list[NewsItem] = []

    # 1. Developer Engineering Blogs (High Quality Learning)
    # Simon Willison (LLMs, Python, SQLite, Engineering experiments)
    all_items.extend(fetch_rss_feed("https://simonwillison.net/atom/everything/", "Simon Willison Weblog"))

    # Hugging Face Engineering & Open Models
    all_items.extend(fetch_rss_feed("https://huggingface.co/blog/feed.xml", "Hugging Face Blog"))

    # GitHub Engineering
    all_items.extend(fetch_rss_feed("https://github.blog/category/engineering/feed/", "GitHub Engineering"))

    # Cloudflare Developer Blog
    all_items.extend(fetch_rss_feed("https://blog.cloudflare.com/rss/", "Cloudflare Engineering"))

    # 2. Hacker News (Filtered for Show HN, libraries, technical benchmarks)
    all_items.extend(fetch_hacker_news())

    # 3. Dev.to (Practical coding and architecture guides)
    all_items.extend(fetch_dev_to())

    # 4. arXiv (Applied ML engineering papers)
    all_items.extend(fetch_arxiv())

    logger.info("Total developer items before deduplication: %d", len(all_items))

    if not deduplicate:
        return all_items

    # Filter out seen stories
    unique_items: list[NewsItem] = []
    for item in all_items:
        url = item.get("url")
        if not url:
            continue
        if not is_seen(url, db_path=db_path):
            unique_items.append(item)

    logger.info("Total developer items after deduplication: %d", len(unique_items))
    return unique_items
