"""Tests for imagegen card rendering with architectural pillars and mode switching."""

import os
import pytest
from PIL import Image
from agents.imagegen import (
    render_card,
    render_architecture_card,
    render,
    CARD_WIDTH,
    CARD_HEIGHT,
)


def test_render_short_headline(tmp_path):
    output_file = str(tmp_path / "card_short.png")
    result_path = render_card(
        headline="Claude 3.7 Released",
        source="Anthropic",
        tag="AI MODEL",
        output_path=output_file,
    )
    assert os.path.exists(result_path)
    with Image.open(result_path) as img:
        assert img.size == (CARD_WIDTH, CARD_HEIGHT)
        assert img.format == "PNG"


def test_render_very_long_headline(tmp_path):
    output_file = str(tmp_path / "card_long.png")
    long_headline = (
        "DeepSeek Releases Open-Source Mixture-of-Experts Architecture Featuring "
        "Multi-Head Latent Attention With Breakthrough KV Cache Compression and "
        "Near-Zero Perplexity Degradation on Massive Scale Foundation Models"
    )
    result_path = render_card(
        headline=long_headline,
        source="Hacker News",
        tag="BREAKTHROUGH",
        output_path=output_file,
    )
    assert os.path.exists(result_path)
    assert os.path.getsize(result_path) > 15000
    with Image.open(result_path) as img:
        assert img.size == (CARD_WIDTH, CARD_HEIGHT)


def test_render_architecture_card_with_pillars(tmp_path):
    output_file = str(tmp_path / "arch_pillars.png")
    result_path = render_architecture_card(
        card_title="MicroVM Sandboxing Architecture for Autonomous Agents",
        card_pillars=[
            "1. Kernel Isolation: Boots minimal guest kernel in <15ms",
            "2. Ephemeral Lifecycles: Destroys microVM instantly upon exit",
            "3. Egress Control: Hard socket quotas block prompt injection",
        ],
        takeaway="Sandboxing arbitrary agent code execution is Day 0 infrastructure.",
        source="Hacker News",
        tag="SECURITY",
        output_path=output_file,
    )
    assert os.path.exists(result_path)
    assert os.path.getsize(result_path) > 15000
    with Image.open(result_path) as img:
        assert img.size == (CARD_WIDTH, CARD_HEIGHT)
        assert img.format == "PNG"


def test_render_unified_hook(tmp_path):
    story = {
        "title": "BunkerVM Runtime",
        "source": "Hacker News",
        "reason": "MicroVM sandboxing for agents.",
    }
    draft = {
        "card_title": "BunkerVM Agent Sandboxing",
        "card_pillars": [
            "Kernel Isolation: Guest kernel boot",
            "Snapshotting: Ephemeral CoW layers",
            "Zero Trust: Hard egress limits",
        ],
        "takeaway": "Essential production pattern.",
        "tags": ["#Security", "#Agents"],
    }
    result_path = render(story, draft, mode="card")
    assert os.path.exists(result_path)
    with Image.open(result_path) as img:
        assert img.size == (CARD_WIDTH, CARD_HEIGHT)
