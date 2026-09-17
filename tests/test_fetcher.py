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
