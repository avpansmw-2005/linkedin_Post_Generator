"""Tests for imagegen card rendering with varying headline lengths."""

import os
import pytest
from PIL import Image
from agents.imagegen import render_card, CARD_WIDTH, CARD_HEIGHT


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
    assert os.path.getsize(result_path) > 15000  # Non-empty valid image
    with Image.open(result_path) as img:
        assert img.size == (CARD_WIDTH, CARD_HEIGHT)
