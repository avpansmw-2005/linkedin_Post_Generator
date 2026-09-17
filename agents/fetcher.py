"""News fetcher integrating developer-focused sources: Hacker News, GitHub/Dev blogs, Dev.to, and arXiv."""

from __future__ import annotations

import os
import re
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
    "sqlite", "postgres", "postgresql", "redis", "docker", "kubernetes", "linux", "git", "github",
    "database", "databases", "indexing", "query", "sql", "nosql", "btree",
    "llm", "agent", "agents", "rag", "embeddings", "vllm", "ollama", "langchain", "langgraph",
    "architecture", "system design", "benchmark", "benchmarks", "optimization", "optimizing", "performance",
    "tutorial", "guide", "how-to", "how to", "deep dive", "postmortem", "debugging",
    "open source", "open-source", "library", "sdk", "api", "framework", "release", "releases",
    "deepseek", "mistral", "claude", "openai", "speculative decoding", "transformer", "fine-tuning",
    "prompt engineering", "context caching", "show hn", "developer", "engineering", "backend",
    "security", "sandbox", "mcp", "firewall", "tokens", "inference", "evals"
}

# Negative keywords to filter out business/finance/drama and spam affiliate noise
EXCLUDE_KEYWORDS = {
    "funding", "valuation", "raised $", "seed round", "series a", "series b", "series c",
    "layoffs", "laid off", "lawsuit", "sued", "antitrust", "crypto", "bitcoin",
    "quarterly earnings", "revenue", "stocks", "shares jump", "ceo steps down",
    "ipo", "acquisition", "acquires", "billion acquisition",
    "buyer's guide", "buyers guide", "cheap", "stripe account", "stripe accounts",
    "defence systems", "defense systems", "discount", "affiliate", "sites for cheap",
    "best sites for", "buy cheap", "coupon", "voucher", "account 2026", "usa & uk accounts",
    "price in", "buy online", "cheap and secure", "seo", "casino"
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


RANDOM_DEV_TOPICS = [
    "PostgreSQL performance and indexing",
    "Docker optimization and container internals",
    "Distributed systems and consensus protocols",
    "Linux kernel and eBPF observability",
    "Async Python and high-concurrency event loops",
    "Rust systems programming and memory safety",
    "LLM quantization and local model inference",
    "LangGraph and autonomous agent architecture",
    "Vector databases and hybrid semantic retrieval",
    "Redis caching patterns and memory efficiency",
    "WebAssembly in production and edge computing",
    "TypeScript advanced type gymnastics",
    "FastAPI architecture and async IO benchmarks",
    "Kafka and event streaming reliability",
    "System design and high-scale architecture postmortems",
]


def get_random_topic() -> str:
    """Selects a random high-signal technical developer topic."""
    import random
    return random.choice(RANDOM_DEV_TOPICS)


STOPWORDS = {
    "how", "can", "we", "i", "you", "they", "our", "my", "your", "as", "a", "an",
    "the", "is", "are", "was", "were", "to", "for", "in", "on", "at", "by", "from",
    "with", "about", "what", "why", "when", "where", "which", "who", "do", "does",
    "did", "should", "would", "could", "developer", "developers", "engineering",
    "give", "me", "show", "find", "search", "best", "practices", "ways", "tell"
}


def _extract_search_keywords(topic: str) -> str:
    """Strips timestamps, conversational phrases and stopwords to extract high-signal search terms."""
    # Remove timestamps like '00:45 AM', '12:30 PM', '10:00', or trailing digits attached to words
    clean = re.sub(r'\d+:\d+.*', '', topic)
    clean = re.sub(r'[^a-zA-Z\s]', ' ', clean).lower()
    words = clean.split()
    filtered = [w for w in words if w not in STOPWORDS and len(w) > 1]
    if filtered:
        return " ".join(filtered)
    return topic.strip()


def fetch_by_topic(topic: str, limit: int = 30) -> list[NewsItem]:
    """Fetches high-signal developer articles and discussions matching a specific topic.
    Handles conversational natural-language queries and strictly excludes all promotional/buyer spam.
    """
    items: list[NewsItem] = []
    clean_topic = topic.strip()
    search_query = _extract_search_keywords(clean_topic)
    logger.info("Searching developer stories for topic: '%s' (cleaned query: '%s')...", clean_topic, search_query)

    # 1. Hacker News Algolia Search (Relevance search on real-world engineering discussions)
    try:
        import urllib.parse
        encoded = urllib.parse.quote(search_query)
        hn_url = f"https://hn.algolia.com/api/v1/search?query={encoded}&tags=story&hitsPerPage=30"
        with httpx.Client(timeout=DEFAULT_TIMEOUT) as client:
            resp = client.get(hn_url)
            if resp.status_code == 200:
                hits = resp.json().get("hits", [])
                for h in hits:
                    title = h.get("title", "")
                    if not title:
                        continue
                    # Block spam/buyer/affiliate junk
                    if any(sp in title.lower() for sp in EXCLUDE_KEYWORDS):
                        continue
                    url = h.get("url") or f"https://news.ycombinator.com/item?id={h.get('objectID')}"
                    points = h.get("points", 0)
                    comments = h.get("num_comments", 0)
                    items.append({
                        "title": title,
                        "url": url,
                        "source": "Hacker News",
                        "summary": f"Technical discussion on Hacker News ({points} points, {comments} comments) exploring {search_query}.",
                        "published": h.get("created_at", ""),
                    })
    except Exception as e:
        logger.warning("Algolia HN search failed for '%s': %s", search_query, e)

    # 2. arXiv Search (Applied AI and Security papers)
    try:
        encoded_arxiv = search_query.replace(" ", "+")
        arxiv_url = f"http://export.arxiv.org/api/query?search_query=all:{encoded_arxiv}&sortBy=relevance&max_results=8"
        arxiv_items = fetch_rss_feed(arxiv_url, f"arXiv ({search_query})", max_items=8)
        items.extend(arxiv_items)
    except Exception as e:
        logger.warning("arXiv search failed for '%s': %s", search_query, e)

    # 3. Premier Engineering Feeds match (Hugging Face, GitHub Engineering, Simon Willison)
    try:
        topic_words = set(search_query.lower().split())
        curated_sources = [
            ("https://simonwillison.net/atom/everything/", "Simon Willison Weblog"),
            ("https://huggingface.co/blog/feed.xml", "Hugging Face Blog"),
            ("https://github.blog/category/engineering/feed/", "GitHub Engineering"),
            ("https://blog.cloudflare.com/rss/", "Cloudflare Engineering"),
        ]
        for feed_url, source_name in curated_sources:
            feed_items = fetch_rss_feed(feed_url, source_name, max_items=10)
            for it in feed_items:
                title_words = set(it["title"].lower().split())
                if topic_words.intersection(title_words):
                    items.append(it)
    except Exception as e:
        logger.warning("Curated feed match failed: %s", e)

    # 4. If search returned nothing, fallback to general high-signal feeds so user is never stranded
    if not items:
        logger.info("Specific search for '%s' returned 0 items; falling back to curated feeds.", search_query)
        items = fetch_all(topic=None, deduplicate=False)

    return items[:limit]


def fetch_all(topic: str | None = None, db_path: str = SEEN_DB_PATH, deduplicate: bool = True) -> list[NewsItem]:
    """Runs developer-centric source fetchers, combines results, and dedupes."""
    if topic:
        all_items = fetch_by_topic(topic)
    else:
        all_items = []
        # 1. Developer Engineering Blogs (High Quality Learning)
        all_items.extend(fetch_rss_feed("https://simonwillison.net/atom/everything/", "Simon Willison Weblog"))
        all_items.extend(fetch_rss_feed("https://huggingface.co/blog/feed.xml", "Hugging Face Blog"))
        all_items.extend(fetch_rss_feed("https://github.blog/category/engineering/feed/", "GitHub Engineering"))
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

    # If deduplication filtered too heavily during rapid testing, return fresh candidates
    if len(unique_items) < 5 and all_items:
        logger.info("Deduplication left only %d items; returning fresh candidates.", len(unique_items))
        return all_items[:15]

    logger.info("Total developer items after deduplication: %d", len(unique_items))
    return unique_items
