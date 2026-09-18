"""News fetcher integrating developer-focused sources: Hacker News, GitHub/Dev blogs, Dev.to, and arXiv.

Prioritizes:
1. New topics related to AI that a developer can learn (architecture, MCP, RAG, local LLMs, hands-on tutorials).
2. Mistakes that most developers make (pitfalls, anti-patterns, postmortems, production debugging lessons).
3. Latest AI news & model breakthroughs (new releases, open-source launches).

Strictly enforces publication recency (filtering out stale content older than 7 days).
"""

from __future__ import annotations

import os
import re
import time
import hashlib
import sqlite3
import logging
from datetime import datetime, timezone
from typing import Any
import httpx
import feedparser

from state import NewsItem

logger = logging.getLogger(__name__)

SEEN_DB_PATH = "data/seen_stories.db"
DEFAULT_TIMEOUT = 10.0

# Categories for content prioritization
CATEGORY_AI_LEARNING = "ai_learning"
CATEGORY_DEVELOPER_MISTAKE = "developer_mistake"
CATEGORY_LATEST_NEWS = "latest_news"

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
    "security", "sandbox", "mcp", "firewall", "tokens", "inference", "evals",
    "mistake", "pitfall", "antipattern", "anti-pattern", "outage", "incident", "lessons learned"
}

# Keywords specifically indicating developer mistakes, anti-patterns, or postmortems
MISTAKE_KEYWORDS = {
    "mistake", "mistakes", "pitfall", "pitfalls", "anti-pattern", "antipattern", "anti-patterns",
    "postmortem", "post-mortem", "outage", "incident", "debugging", "gotcha", "gotchas",
    "bug", "bugs", "lessons learned", "what went wrong", "avoid", "don't do", "failure",
    "silent fail", "memory leak", "deadlock", "injection", "vulnerability"
}

# Keywords specifically indicating AI learning and hands-on skills
AI_LEARNING_KEYWORDS = {
    "agent", "agents", "mcp", "rag", "vllm", "ollama", "local llm", "fine-tuning",
    "structured outputs", "speculative decoding", "context caching", "prompt engineering",
    "evals", "vector", "embeddings", "transformer", "architecture", "system design",
    "tutorial", "guide", "how-to", "how we built", "deep dive"
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


# ==============================================================================
# Date Parsing & Strict Recency Enforcement
# ==============================================================================

def parse_datetime(val: Any) -> datetime | None:
    """Attempts to parse a datetime string, unix timestamp, or struct_time into a UTC datetime."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        try:
            return datetime.fromtimestamp(val, timezone.utc)
        except Exception:
            return None
    if hasattr(val, "tm_year"):  # feedparser struct_time
        try:
            return datetime(*val[:6], tzinfo=timezone.utc)
        except Exception:
            return None
    if isinstance(val, str):
        s = val.strip()
        if not s:
            return None
        # Try ISO 8601
        try:
            clean_iso = s.replace("Z", "+00:00")
            dt = datetime.fromisoformat(clean_iso)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except Exception:
            pass
        # Try RFC 2822 / HTTP format (e.g., 'Tue, 15 Sep 2026 16:00:44 GMT')
        try:
            import email.utils
            dt = email.utils.parsedate_to_datetime(s)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except Exception:
            pass
    return None


def is_recent(date_val: Any, max_days: float = 7.0) -> bool:
    """Checks whether a publication date is within max_days of current UTC time."""
    dt = parse_datetime(date_val)
    if dt is None:
        return True  # If publication date cannot be extracted, don't drop blindly
    now = datetime.now(timezone.utc)
    age_seconds = (now - dt).total_seconds()
    # Guard against distant future timestamps or stories older than max_days
    if age_seconds < -86400:  # > 24 hours in the future
        return False
    return age_seconds <= (max_days * 86400)


def get_relative_time_str(date_val: Any) -> str:
    """Computes a human-friendly relative time string (e.g. '3h ago', 'yesterday', '2d ago')."""
    dt = parse_datetime(date_val)
    if dt is None:
        return ""
    now = datetime.now(timezone.utc)
    diff_sec = (now - dt).total_seconds()
    if diff_sec < 0:
        return "just now"
    hours = int(diff_sec // 3600)
    if hours < 1:
        mins = max(1, int(diff_sec // 60))
        return f"{mins}m ago"
    if hours < 24:
        return f"{hours}h ago"
    days = int(hours // 24)
    if days == 1:
        return "yesterday"
    return f"{days}d ago"


# ==============================================================================
# Seen Stories SQLite Deduplication
# ==============================================================================

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


# ==============================================================================
# Filtering & Keyword Detection
# ==============================================================================

def _is_relevant_developer_story(text: str) -> bool:
    """Checks if text contains developer/engineering learning concepts and excludes corporate fluff."""
    lower_text = text.lower()

    # Reject if it matches business/drama noise
    if any(ex in lower_text for ex in EXCLUDE_KEYWORDS):
        return False

    # Check for developer keywords
    words = set(lower_text.replace("-", " ").replace(":", " ").replace("/", " ").replace("?", " ").split())
    if words.intersection(DEV_KEYWORDS):
        return True

    return any(kw in lower_text for kw in [
        "system design", "how it works", "under the hood", "best practice", "open source",
        "speculative decoding", "context caching", "show hn", "prompt engineering",
        "lessons learned", "what went wrong", "anti pattern"
    ])


def _contains_ai_keywords(text: str) -> bool:
    """Backwards-compatible helper for tests."""
    return _is_relevant_developer_story(text)


def _classify_story(title: str, summary: str = "") -> str:
    """Automatically assigns a primary category based on headline content."""
    combined = (title + " " + summary).lower()
    words = set(combined.replace("-", " ").replace(":", " ").replace("/", " ").replace("?", " ").split())

    if words.intersection(MISTAKE_KEYWORDS) or any(m in combined for m in ["what went wrong", "lessons learned", "anti-pattern", "anti pattern"]):
        return CATEGORY_DEVELOPER_MISTAKE
    if words.intersection(AI_LEARNING_KEYWORDS) or any(a in combined for a in ["how to", "tutorial", "architecture", "deep dive", "guide", "system design"]):
        return CATEGORY_AI_LEARNING
    return CATEGORY_LATEST_NEWS


# ==============================================================================
# Hacker News Algolia Real-Time Search (Chronological Recency Guaranteed)
# ==============================================================================

def search_hn_recent(
    query: str,
    category: str,
    max_days: int = 7,
    hits_per_page: int = 15,
) -> list[NewsItem]:
    """Searches Hacker News via Algolia search_by_date, guaranteeing chronological recency."""
    items: list[NewsItem] = []
    cutoff_ts = int(time.time()) - (max_days * 86400)
    try:
        import urllib.parse
        encoded_query = urllib.parse.quote(query)
        hn_url = (
            f"https://hn.algolia.com/api/v1/search_by_date?"
            f"query={encoded_query}&tags=story&numericFilters=created_at_i>{cutoff_ts}&hitsPerPage={hits_per_page}"
        )
        with httpx.Client(timeout=DEFAULT_TIMEOUT) as client:
            resp = client.get(hn_url)
            if resp.status_code == 200:
                hits = resp.json().get("hits", [])
                for h in hits:
                    title = h.get("title", "")
                    if not title or not _is_relevant_developer_story(title):
                        continue
                    if any(sp in title.lower() for sp in EXCLUDE_KEYWORDS):
                        continue
                    url = h.get("url") or f"https://news.ycombinator.com/item?id={h.get('objectID')}"
                    points = h.get("points", 0) or 0
                    comments = h.get("num_comments", 0) or 0
                    created_at = h.get("created_at", "")
                    items.append({
                        "title": title,
                        "url": url,
                        "source": "Hacker News",
                        "summary": f"Discussion on Hacker News ({points} points, {comments} comments) exploring {title}.",
                        "published": created_at,
                        "category": category,
                        "relative_time": get_relative_time_str(created_at),
                    })
    except Exception as e:
        logger.warning("Algolia HN search_by_date failed for '%s': %s", query, e)

    return items


def fetch_hacker_news(limit: int = 40, max_days: int = 5) -> list[NewsItem]:
    """Fetches top Hacker News stories strictly filtered for developer learnings and recency."""
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

                    story_time = data.get("time", 0)
                    # Discard if older than max_days
                    if not is_recent(story_time, max_days=max_days):
                        continue

                    title = data.get("title", "")
                    url = data.get("url") or f"https://news.ycombinator.com/item?id={story_id}"
                    if _is_relevant_developer_story(title):
                        iso_published = datetime.fromtimestamp(story_time, timezone.utc).isoformat()
                        cat = _classify_story(title)
                        items.append({
                            "title": title,
                            "url": url,
                            "source": "Hacker News",
                            "summary": f"Technical discussion on Hacker News (score: {data.get('score', 0)}, comments: {data.get('descendants', 0)}).",
                            "published": iso_published,
                            "category": cat,
                            "relative_time": get_relative_time_str(story_time),
                        })
                except Exception as e:
                    logger.debug("Error fetching HN item %s: %s", story_id, e)
    except Exception as e:
        logger.warning("Failed to fetch Hacker News: %s", e)

    return items


# ==============================================================================
# Dev.to Real-Time Tutorials & Pitfalls
# ==============================================================================

def fetch_dev_to(per_page: int = 12, max_days: int = 7) -> list[NewsItem]:
    """Fetches latest practical engineering tutorials and debugging guides from Dev.to."""
    items: list[NewsItem] = []
    # Query high-signal tags for both AI learning and developer mistakes
    tag_configs = [
        ("ai", CATEGORY_AI_LEARNING),
        ("machinelearning", CATEGORY_AI_LEARNING),
        ("debugging", CATEGORY_DEVELOPER_MISTAKE),
        ("programming", CATEGORY_AI_LEARNING),
    ]
    try:
        with httpx.Client(timeout=DEFAULT_TIMEOUT) as client:
            for tag, default_cat in tag_configs:
                resp = client.get(f"https://dev.to/api/articles?tag={tag}&per_page={per_page}")
                if resp.status_code != 200:
                    continue
                for art in resp.json():
                    published_at = art.get("published_at", "")
                    if not is_recent(published_at, max_days=max_days):
                        continue

                    title = art.get("title", "")
                    desc = art.get("description", "") or ""
                    if _is_relevant_developer_story(title + " " + desc):
                        cat = _classify_story(title, desc) or default_cat
                        items.append({
                            "title": title,
                            "url": art.get("url", ""),
                            "source": "Dev.to",
                            "summary": desc[:300] or "Practical developer guide and learnings.",
                            "published": published_at,
                            "category": cat,
                            "relative_time": get_relative_time_str(published_at),
                        })
    except Exception as e:
        logger.warning("Failed to fetch Dev.to: %s", e)

    return items


# ==============================================================================
# Curated RSS Feeds (Simon Willison, Hugging Face, Engineering Blogs)
# ==============================================================================

def fetch_rss_feed(
    feed_url: str,
    source_name: str,
    default_category: str = CATEGORY_AI_LEARNING,
    max_items: int = 8,
    max_days: int = 7,
) -> list[NewsItem]:
    """Fetches and normalizes an RSS feed, enforcing strict recency validation."""
    items: list[NewsItem] = []
    try:
        parsed = feedparser.parse(feed_url)
        for entry in parsed.entries[:max_items]:
            # Recency check: ignore entries older than max_days
            published_dt = getattr(entry, "published_parsed", None) or getattr(entry, "updated_parsed", None)
            if not is_recent(published_dt, max_days=max_days):
                continue

            title = getattr(entry, "title", "")
            link = getattr(entry, "link", "")
            summary = getattr(entry, "summary", "") or getattr(entry, "description", "")
            clean_summary = summary.replace("<p>", "").replace("</p>", "").strip()
            raw_published = getattr(entry, "published", "") or getattr(entry, "updated", "")
            if title and link and _is_relevant_developer_story(title + " " + clean_summary[:200]):
                cat = _classify_story(title, clean_summary) or default_category
                items.append({
                    "title": title,
                    "url": link,
                    "source": source_name,
                    "summary": clean_summary[:400],
                    "published": raw_published,
                    "category": cat,
                    "relative_time": get_relative_time_str(published_dt or raw_published),
                })
    except Exception as e:
        logger.warning("Failed to fetch RSS %s (%s): %s", source_name, feed_url, e)

    return items


def fetch_arxiv(max_results: int = 6, max_days: int = 7) -> list[NewsItem]:
    """Fetches latest applied AI/NLP engineering papers from arXiv (submitted recently)."""
    url = (
        f"http://export.arxiv.org/api/query?search_query=cat:cs.AI+OR+cat:cs.CL"
        f"&sortBy=submittedDate&sortOrder=descending&max_results={max_results}"
    )
    return fetch_rss_feed(url, "arXiv Engineering", default_category=CATEGORY_AI_LEARNING, max_items=max_results, max_days=max_days)


# ==============================================================================
# Topic-Specific Search (AI Learning, Mistakes, and News)
# ==============================================================================

RANDOM_DEV_TOPICS = [
    "AI agent loops and runaway token execution mistakes",
    "Model Context Protocol (MCP) server implementation and security",
    "RAG semantic chunking traps and retrieval failures",
    "Local LLM quantization with GGUF vs AWQ vs FP8",
    "Prompt injection vulnerabilities and microVM sandboxing",
    "Structured LLM outputs and strict JSON schema enforcement",
    "Vector index tuning in pgvector and Qdrant under high concurrency",
    "FastAPI connection pool exhaustion during LLM streaming",
    "Evaluating LLMs in production: synthetic benchmarks vs real evals",
    "Async Python event loop bottlenecks and blocking IO mistakes",
    "PostgreSQL indexing anti-patterns and query planner surprises",
    "Docker container security and privilege escalation pitfalls",
    "vLLM and TensorRT-LLM inference latency optimization",
    "Distributed consensus and raft leader election edge cases",
    "TypeScript type system mistakes and compile-time performance",
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
    clean = re.sub(r'\d+:\d+.*', '', topic)
    clean = re.sub(r'[^a-zA-Z\s]', ' ', clean).lower()
    words = clean.split()
    filtered = [w for w in words if w not in STOPWORDS and len(w) > 1]
    if filtered:
        return " ".join(filtered)
    return topic.strip()


def fetch_by_topic(topic: str, mode: str | None = None, limit: int = 30) -> list[NewsItem]:
    """Fetches high-signal developer articles and discussions matching a specific topic.
    Guarantees recent results via search_by_date and prioritizes AI Learning and Dev Mistakes.
    """
    clean_topic = topic.strip()
    search_query = _extract_search_keywords(clean_topic)
    logger.info("Searching developer stories for topic: '%s' (cleaned query: '%s')...", clean_topic, search_query)

    learning_items: list[NewsItem] = []
    mistake_items: list[NewsItem] = []
    news_items: list[NewsItem] = []

    # 1. Targeted HN Algolia searches (search_by_date with 14-day cutoff for topic relevance)
    # 1a. Mistakes & Pitfalls on this topic
    mistake_queries = [f"{search_query} mistake", f"{search_query} pitfall", f"{search_query} postmortem"]
    for mq in mistake_queries[:2]:
        mistake_items.extend(search_hn_recent(mq, CATEGORY_DEVELOPER_MISTAKE, max_days=14, hits_per_page=8))

    # 1b. Learning & Architecture on this topic
    learning_queries = [f"{search_query} architecture", f"{search_query} guide", f"{search_query} agent"]
    for lq in learning_queries[:2]:
        learning_items.extend(search_hn_recent(lq, CATEGORY_AI_LEARNING, max_days=14, hits_per_page=8))

    # 1c. Direct Topic search on HN
    direct_hn = search_hn_recent(search_query, CATEGORY_LATEST_NEWS, max_days=14, hits_per_page=12)
    for it in direct_hn:
        cat = _classify_story(it["title"])
        it["category"] = cat
        if cat == CATEGORY_DEVELOPER_MISTAKE:
            mistake_items.append(it)
        elif cat == CATEGORY_AI_LEARNING:
            learning_items.append(it)
        else:
            news_items.append(it)

    # 2. arXiv Search for cutting-edge technical papers (sorted by date descending)
    try:
        encoded_arxiv = search_query.replace(" ", "+")
        arxiv_url = f"http://export.arxiv.org/api/query?search_query=all:{encoded_arxiv}&sortBy=submittedDate&sortOrder=descending&max_results=6"
        arxiv_items = fetch_rss_feed(arxiv_url, f"arXiv ({search_query})", default_category=CATEGORY_AI_LEARNING, max_items=6, max_days=14)
        learning_items.extend(arxiv_items)
    except Exception as e:
        logger.warning("arXiv search failed for '%s': %s", search_query, e)

    # 3. Curated Engineering Feeds match
    try:
        topic_words = set(search_query.lower().split())
        curated_sources = [
            ("https://simonwillison.net/atom/everything/", "Simon Willison Weblog"),
            ("https://huggingface.co/blog/feed.xml", "Hugging Face Blog"),
            ("https://blog.cloudflare.com/rss/", "Cloudflare Engineering"),
            ("https://github.blog/category/engineering/feed/", "GitHub Engineering"),
        ]
        for feed_url, source_name in curated_sources:
            feed_items = fetch_rss_feed(feed_url, source_name, max_items=10, max_days=14)
            for it in feed_items:
                title_words = set(it["title"].lower().split())
                if topic_words.intersection(title_words):
                    if it.get("category") == CATEGORY_DEVELOPER_MISTAKE:
                        mistake_items.append(it)
                    else:
                        learning_items.append(it)
    except Exception as e:
        logger.warning("Curated feed match failed: %s", e)

    # Assemble in user's strict priority hierarchy:
    # 1. AI Learning > 2. Developer Mistakes > 3. Latest News
    combined: list[NewsItem] = []
    seen_urls: set[str] = set()

    def add_unique(lst: list[NewsItem]):
        for it in lst:
            u = it.get("url")
            if u and u not in seen_urls:
                seen_urls.add(u)
                combined.append(it)

    if mode == "mistakes":
        add_unique(mistake_items)
        add_unique(learning_items)
    elif mode == "news":
        add_unique(news_items)
        add_unique(learning_items)
    else:
        # Default prioritized hierarchy: Learning first, then Mistakes, then News
        add_unique(learning_items)
        add_unique(mistake_items)
        add_unique(news_items)

    # If specific search returned nothing, fall back to general scan so user is never stranded
    if not combined:
        logger.info("Specific search for '%s' returned 0 items; falling back to curated feeds.", search_query)
        combined = fetch_all(topic=None, mode=mode, deduplicate=False)

    return combined[:limit]


# ==============================================================================
# Unified Fetcher Pipeline
# ==============================================================================

def fetch_all(
    topic: str | None = None,
    mode: str | None = None,
    db_path: str = SEEN_DB_PATH,
    deduplicate: bool = True,
) -> list[NewsItem]:
    """Runs developer-centric source fetchers, strictly prioritizing:
    1. AI Developer Learning (architectures, agent protocols, tutorials)
    2. Developer Mistakes & Pitfalls (postmortems, anti-patterns, debugging)
    3. Latest News & Model Releases (fresh announcements)
    """
    if topic:
        all_items = fetch_by_topic(topic, mode=mode)
    else:
        learning_items: list[NewsItem] = []
        mistake_items: list[NewsItem] = []
        news_items: list[NewsItem] = []

        # -------------------------------------------------------------
        # 1. AI DEVELOPER LEARNING (TOP PRIORITY)
        # -------------------------------------------------------------
        logger.info("Scanning for AI Developer Learning topics (Priority 1)...")
        # Hacker News targeted AI learning queries
        for q in ["agent", "mcp", "rag", "local llm", "vllm", "structured outputs"]:
            learning_items.extend(search_hn_recent(q, CATEGORY_AI_LEARNING, max_days=5, hits_per_page=6))

        # Dev.to practical AI tutorials
        learning_items.extend(fetch_dev_to(per_page=8, max_days=5))

        # Curated engineering weblogs & arXiv
        learning_items.extend(fetch_rss_feed("https://simonwillison.net/atom/everything/", "Simon Willison Weblog", default_category=CATEGORY_AI_LEARNING, max_days=5))
        learning_items.extend(fetch_rss_feed("https://huggingface.co/blog/feed.xml", "Hugging Face Blog", default_category=CATEGORY_AI_LEARNING, max_days=7))
        learning_items.extend(fetch_arxiv(max_results=5, max_days=5))

        # -------------------------------------------------------------
        # 2. DEVELOPER MISTAKES, PITFALLS & POSTMORTEMS (HIGH PRIORITY)
        # -------------------------------------------------------------
        logger.info("Scanning for Developer Mistakes & Pitfalls (Priority 2)...")
        for q in ["mistake", "pitfall", "anti-pattern", "postmortem", "debugging"]:
            mistake_items.extend(search_hn_recent(q, CATEGORY_DEVELOPER_MISTAKE, max_days=7, hits_per_page=6))

        # -------------------------------------------------------------
        # 3. LATEST NEWS & MODEL RELEASES (MODERATE PRIORITY)
        # -------------------------------------------------------------
        logger.info("Scanning for Latest AI News & Releases (Priority 3)...")
        for q in ["deepseek", "claude", "mistral", "openai"]:
            news_items.extend(search_hn_recent(q, CATEGORY_LATEST_NEWS, max_days=4, hits_per_page=4))

        news_items.extend(fetch_hacker_news(limit=30, max_days=3))
        news_items.extend(fetch_rss_feed("https://blog.cloudflare.com/rss/", "Cloudflare Engineering", default_category=CATEGORY_LATEST_NEWS, max_days=7))
        news_items.extend(fetch_rss_feed("https://github.blog/category/engineering/feed/", "GitHub Engineering", default_category=CATEGORY_LATEST_NEWS, max_days=7))

        # Combine strictly according to preference hierarchy
        all_items = []
        seen_urls: set[str] = set()

        def add_batch(items: list[NewsItem]):
            for it in items:
                u = it.get("url")
                if u and u not in seen_urls:
                    seen_urls.add(u)
                    all_items.append(it)

        if mode == "mistakes":
            add_batch(mistake_items)
            add_batch(learning_items)
            add_batch(news_items)
        elif mode == "news":
            add_batch(news_items)
            add_batch(learning_items)
            add_batch(mistake_items)
        else:
            # Hierarchy: 1) AI Learning, 2) Developer Mistakes, 3) Latest News
            add_batch(learning_items)
            add_batch(mistake_items)
            add_batch(news_items)

    logger.info("Total developer items gathered: %d", len(all_items))

    if not deduplicate:
        return all_items

    # Filter out previously seen stories
    unique_items: list[NewsItem] = []
    for item in all_items:
        url = item.get("url")
        if not url:
            continue
        if not is_seen(url, db_path=db_path):
            unique_items.append(item)

    # Fallback to fresh candidates if deduplication was too aggressive
    if len(unique_items) < 5 and all_items:
        logger.info("Deduplication left only %d items; returning fresh candidates.", len(unique_items))
        return all_items[:20]

    logger.info("Total developer items after deduplication: %d", len(unique_items))
    return unique_items
