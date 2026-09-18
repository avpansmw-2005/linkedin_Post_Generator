"""Tests for the ranker agent schemas and ranking logic."""

import json
import pytest
from agents.ranker import TopFiveRanking, ScoredNewsItem, rank


def test_top_five_ranking_schema():
    raw_payload = {
        "top_items": [
            {
                "index": 1,
                "title": "DeepSeek Releases MLA Architecture",
                "url": "https://news.ycombinator.com/item?id=40010001",
                "source": "Hacker News",
                "summary": "Novel Multi-Head Latent Attention significantly slashes KV cache memory.",
                "score": 9.7,
                "reason": "Dramatic KV cache optimization crucial for real-time serving infrastructure.",
            }
        ]
    }
    parsed = TopFiveRanking.model_validate(raw_payload)
    assert len(parsed.top_items) == 1
    assert parsed.top_items[0].score == 9.7
    assert "KV cache" in parsed.top_items[0].reason


def test_ranker_short_list_fallback():
    items = [
        {"title": "Item 1", "url": "https://example.com/1", "source": "HN", "summary": "Sum 1", "published": ""},
        {"title": "Item 2", "url": "https://example.com/2", "source": "Dev.to", "summary": "Sum 2", "published": ""},
    ]
    # Candidate count <= 5 triggers direct score assignment without calling external LLM
    result = rank(items, top_k=5)
    assert len(result) == 2
    assert 1.0 <= result[0]["score"] <= 10.0
    assert "reason" in result[0]


def test_ranker_category_priority_scores():
    items = [
        {"title": "MCP Architecture", "url": "https://example.com/1", "category": "ai_learning"},
        {"title": "Prisma Bug Postmortem", "url": "https://example.com/2", "category": "developer_mistake"},
        {"title": "New Model Release", "url": "https://example.com/3", "category": "latest_news"},
    ]
    result = rank(items, top_k=5)
    assert len(result) == 3
    # AI Learning (9.5) > Developer Mistake (8.8) > Latest News (7.8)
    assert result[0]["score"] > result[1]["score"]
    assert result[1]["score"] > result[2]["score"]
    assert result[0]["category"] == "ai_learning"
    assert result[1]["category"] == "developer_mistake"
    assert result[2]["category"] == "latest_news"


def test_top_ten_ranking_schema_and_variety():
    from agents.ranker import TopTenRanking
    raw_payload = {
        "top_items": [
            {
                "index": i,
                "title": f"Story {i}",
                "url": f"https://example.com/{i}",
                "source": "HN",
                "summary": f"Summary {i}",
                "category": "ai_learning" if i <= 4 else ("developer_mistake" if i <= 7 else "latest_news"),
                "score": 9.5 - i * 0.1,
                "reason": f"Takeaway {i}",
            }
            for i in range(1, 11)
        ]
    }
    parsed = TopTenRanking.model_validate(raw_payload)
    assert len(parsed.top_items) == 10
    categories = {it.category for it in parsed.top_items}
    assert "ai_learning" in categories
    assert "developer_mistake" in categories
    assert "latest_news" in categories


def test_ranker_returns_ten_items_fallback():
    items = [
        {"title": f"Story {i}", "url": f"https://example.com/{i}", "category": "ai_learning" if i % 2 == 0 else "developer_mistake"}
        for i in range(1, 15)
    ]
    result = rank(items, top_k=10)
    assert len(result) == 10
    assert result[0]["score"] >= result[-1]["score"]

