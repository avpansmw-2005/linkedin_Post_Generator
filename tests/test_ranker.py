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
