"""Tests for expanded sources, Google News search, constraint enforcement (e.g. hyphen removal), and humor mode."""

import pytest
from agents import fetcher, humanizer, writer, ranker
from state import RankedItem


def test_fetch_google_news_search_jev():
    """Verify that Google News search fetches stories for Jev from premier publications."""
    items = fetcher.fetch_google_news_search("Jev", max_items=10)
    assert len(items) > 0
    sources = [it.get("source") for it in items]
    # Verify presence of diverse sources
    assert any(s for s in sources if s and s != "Hacker News")


def test_fetch_by_topic_jev():
    """Verify that fetch_by_topic gathers multi-source stories for Jev."""
    items = fetcher.fetch_by_topic("Jev", limit=20)
    assert len(items) > 0
    sources = set(it.get("source") for it in items)
    assert len(sources) >= 2


def test_enforce_user_constraints_hyphens():
    """Verify that enforce_user_constraints deterministically strips hyphens and dashes."""
    sample_text = (
        "Here is a draft post:\n"
        "- First bullet point\n"
        "- Second bullet point - with mid-sentence dash\n"
        "This is an end-to-end test—with an em-dash.\n"
        "How do you do it?\n"
        "#AI #Tech"
    )
    result = humanizer.enforce_user_constraints(sample_text, "remove all hyphens and dashes")
    assert "-" not in result
    assert "—" not in result
    assert "–" not in result
    assert "First bullet point" in result
    assert "Second bullet point" in result


def test_enforce_user_constraints_hashtags():
    """Verify hashtag removal constraint."""
    sample_text = "Awesome engineering article! #AI #Tech #Python"
    result = humanizer.enforce_user_constraints(sample_text, "remove hashtags")
    assert "#AI" not in result
    assert "#Tech" not in result
    assert "#Python" not in result


def test_humanizer_hyphen_removal_e2e():
    """Verify that humanizer.rewrite strictly obeys 'remove hyphens'."""
    sample_draft = (
        "Senior architects know this rule:\n\n"
        "- Always benchmark your KV cache\n"
        "- Never deploy unchecked models - they fail\n\n"
        "What is your production setup?\n\n"
        "👇 Check the source in the comments!\n\n"
        "#AI #Dev"
    )
    story: RankedItem = {
        "title": "KV Cache Benchmarks",
        "url": "https://example.com/kv",
        "source": "Tech Blog",
        "category": "ai_learning",
        "summary": "Benchmarking KV cache memory usage under heavy LLM concurrency.",
        "score": 9.5,
        "reason": "Direct benchmark insight",
    }
    result = humanizer.rewrite(sample_draft, edit_notes="remove hyphens and dashes", story=story)
    assert "-" not in result
    assert "—" not in result
    assert len(result) > 20


def test_humanizer_humor_detection():
    """Verify that humor mode triggers when requested."""
    sample_draft = (
        "We deployed an AI agent pipeline.\n\n"
        "It reduced latency by 40%.\n\n"
        "How do you monitor your agents?\n\n"
        "👇 Check the source in the comments!\n\n"
        "#AI"
    )
    result = humanizer.rewrite(sample_draft, edit_notes="add humor and make it funny", humor=True)
    assert len(result) > 20


def test_strip_all_hyphens_comprehensive():
    """Verify that strip_all_hyphens eliminates all forms of hyphens and dashes while preserving URLs."""
    raw = (
        "Here is an end-to-end pipeline with real-world token-aware caching.\n"
        "- First bullet item\n"
        "- Second bullet item - with an inline dash\n"
        "Stat: -68% latency drop.\n"
        "Thought—with an em-dash and range 10–20 with en-dash.\n"
        "Check code: https://github.com/vllm-project/vllm-v2"
    )
    cleaned = humanizer.strip_all_hyphens(raw)
    # Check that no hyphens or dashes exist outside of URLs
    text_without_urls = cleaned.replace("https://github.com/vllm-project/vllm-v2", "")
    assert "-" not in text_without_urls
    assert "—" not in text_without_urls
    assert "–" not in text_without_urls
    # URL is preserved intact
    assert "https://github.com/vllm-project/vllm-v2" in cleaned
    # Content is preserved
    assert "end to end" in cleaned
    assert "real world" in cleaned
    assert "token aware" in cleaned
    assert "68% latency drop" in cleaned


def test_humanizer_unconditional_zero_hyphens_no_notes():
    """Verify that humanizer.enforce_user_constraints strips hyphens even when edit_notes is None."""
    sample = "A battle-tested model with -40% memory usage.\n- Fast response"
    result = humanizer.enforce_user_constraints(sample, None)
    assert "-" not in result
    assert "battle tested" in result
    assert "40% memory usage" in result


def test_writer_fallback_zero_hyphens():
    """Verify that writer fallback draft produces zero hyphens."""
    story: RankedItem = {
        "title": "Low-Latency Token-Aware Inference",
        "url": "https://example.com/test",
        "source": "Tech Blog",
        "category": "ai_learning",
        "summary": "State-of-the-art benchmarks for inference.",
        "score": 9.0,
        "reason": "Direct benchmark insight",
    }
    # Test fallback by passing invalid story or provoking exception handling
    from agents.writer import write
    # The normal LLM call might succeed or fail; either way, output text and pillars must have zero hyphens
    draft = write(story)
    assert "-" not in draft["text"]
    assert "—" not in draft["text"]
    assert "–" not in draft["text"]
    assert "-" not in draft["card_title"]
    for pillar in draft["card_pillars"]:
        assert "-" not in pillar
    if draft.get("benchmark_stat"):
        assert "-" not in draft["benchmark_stat"]

