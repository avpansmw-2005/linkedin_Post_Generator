"""Tests for the news fetcher and SQLite deduplication."""

import os
import json
import pytest
from agents import fetcher


@pytest.fixture
def temp_db(tmp_path):
    return str(tmp_path / "test_seen.db")


def test_url_hash_consistency():
    url1 = "https://techcrunch.com/article/ai-release/"
    url2 = "https://techcrunch.com/article/ai-release"
    url3 = "  HTTPS://TECHCRUNCH.COM/ARTICLE/AI-RELEASE/  "
    assert fetcher.hash_url(url1) == fetcher.hash_url(url2)
    assert fetcher.hash_url(url1) == fetcher.hash_url(url3)


def test_deduplication_lifecycle(temp_db):
    test_url = "https://news.ycombinator.com/item?id=99999"
    test_title = "Claude 3.7 Hybrid Reasoning Breakthrough"

    # Initially not seen
    assert not fetcher.is_seen(test_url, db_path=temp_db)

    # Mark seen
    fetcher.mark_seen(test_url, test_title, db_path=temp_db)

    # Now must be seen
    assert fetcher.is_seen(test_url, db_path=temp_db)


def test_ai_keyword_filtering():
    assert fetcher._contains_ai_keywords("DeepSeek Releases Open-Source MoE Architecture")
    assert fetcher._contains_ai_keywords("New speculative decoding paper accelerates transformer inference")
    assert fetcher._contains_ai_keywords("Anthropic announces Claude updates")
    assert not fetcher._contains_ai_keywords("Best coffee shops in Seattle for morning remote work")


def test_sample_fixtures_loaded():
    fixture_path = os.path.join("tests", "fixtures", "sample_news.json")
    assert os.path.exists(fixture_path)
    with open(fixture_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert len(data) == 10
    for item in data:
        assert "title" in item
        assert "url" in item
        assert "source" in item


def test_get_random_topic():
    topic = fetcher.get_random_topic()
    assert isinstance(topic, str)
    assert len(topic) > 5


def test_exclude_corporate_fluff():
    assert not fetcher._is_relevant_developer_story("Startup raises $50M in seed funding round")
    assert not fetcher._is_relevant_developer_story("BigTech CEO steps down after antitrust lawsuit")
    assert fetcher._is_relevant_developer_story("Optimizing PostgreSQL query plans with indexing and btree")


def test_parse_datetime_and_is_recent():
    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone.utc)

    # 1. Fresh date (2 hours ago)
    fresh_dt = (now - timedelta(hours=2)).isoformat()
    parsed_fresh = fetcher.parse_datetime(fresh_dt)
    assert parsed_fresh is not None
    assert fetcher.is_recent(fresh_dt, max_days=7) is True

    # 2. Stale date (30 days ago)
    stale_dt = (now - timedelta(days=30)).isoformat()
    assert fetcher.is_recent(stale_dt, max_days=7) is False

    # 3. Unix timestamp
    ts_now = now.timestamp()
    assert fetcher.is_recent(ts_now, max_days=7) is True
    assert fetcher.is_recent(ts_now - 86400 * 15, max_days=7) is False


def test_get_relative_time_str():
    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone.utc)

    two_hours_ago = (now - timedelta(hours=2)).isoformat()
    assert "2h ago" in fetcher.get_relative_time_str(two_hours_ago)

    yesterday = (now - timedelta(hours=26)).isoformat()
    assert "yesterday" in fetcher.get_relative_time_str(yesterday)


def test_classify_story():
    assert fetcher._classify_story("Prisma pgbouncer bug postmortem") == fetcher.CATEGORY_DEVELOPER_MISTAKE
    assert fetcher._classify_story("Top 5 mistakes developers make with RAG") == fetcher.CATEGORY_DEVELOPER_MISTAKE
    assert fetcher._classify_story("Model Context Protocol (MCP) Tutorial and Architecture") == fetcher.CATEGORY_AI_LEARNING
    assert fetcher._classify_story("DeepSeek v3 Foundation Model Release") == fetcher.CATEGORY_LATEST_NEWS

