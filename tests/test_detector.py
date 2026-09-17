"""Unit tests for the statistical AI Detection Engine."""

import pytest
from agents import detector


def test_split_sentences():
    text = (
        "Running containers in production is tricky! https://example.com/blog "
        "We saw latency jump by 40ms. #DevOps #Docker "
        "Root cause? A misconfigured cgroup limit."
    )
    sentences = detector.split_sentences(text)
    assert len(sentences) == 4
    assert "https://" not in sentences[0]
    assert "#DevOps" not in sentences[1]


def test_calculate_burstiness():
    # Uniform sentence lengths (all ~5 words)
    uniform = ["This is the first sentence.", "This is the second one.", "This is the third one."]
    burst_low = detector.calculate_burstiness(uniform)
    assert burst_low < 2.0

    # Highly varied sentence lengths (2 words vs 20 words)
    varied = [
        "Don't do it.",
        "When we stress-tested the microVM isolation layer under a sustained 10,000 req/sec load, the Linux kernel namespace collapsed completely.",
        "Zero exceptions.",
    ]
    burst_high = detector.calculate_burstiness(varied)
    assert burst_high > 7.0


def test_scan_ai_hallmarks():
    ai_text = (
        "The benefits are pretty straightforward: isolation and security. "
        "Of course, there are some trade-offs in terms of memory overhead. "
        "Curious to hear how others are balancing this!"
    )
    found = detector.scan_ai_hallmarks(ai_text)
    assert len(found) >= 3


def test_analyze_ai_probability_robotic_sample():
    robotic_text = (
        "I've been working with AI agents lately, and one thing that's become clear is the importance of keeping them isolated. "
        "That's where Docker sandboxes come in handy. Using Docker for containerization, each AI agent runs in its own environment. "
        "This means every agent has its own file system, network interfaces, and process space, which keeps them completely separate from each other. "
        "The benefits are pretty straightforward: "
        "- Isolation: Each container is a self-contained unit, so agents don't interfere with one another. "
        "- Security: Docker's security model helps us enforce access controls, minimizing the risk of unauthorized access. "
        "- Scalability: Containers are lightweight and can be quickly scaled up or down, making them perfect for managing resources efficiently. "
        "Of course, there are some trade-offs. Containers do have a bit of overhead in terms of startup time and resource usage, which might affect applications that need to be super responsive. "
        "Curious to hear how others are handling agent isolation!"
    )
    result = detector.analyze_ai_probability(robotic_text)
    assert result["ai_score"] >= 70
    assert result["human_score"] <= 30
    assert result["badge"] == "🚨"
    assert len(result["flagged_phrases"]) >= 2


def test_analyze_ai_probability_humanized_sample():
    human_text = (
        "If you give an autonomous agent bash access on raw metal, you're one hallucinated rm command away from a postmortem.\n\n"
        "Don't do it.\n\n"
        "We run each agent in an ephemeral rootless Docker container with a read-only tmpfs and capped memory cgroups. "
        "Network egress is locked down with strict iptables rules. Total silence.\n\n"
        "Startup latency added 180ms per task, but the blast radius dropped to zero.\n\n"
        "Are you isolating agent execution at the namespace boundary yet?"
    )
    result = detector.analyze_ai_probability(human_text)
    assert result["ai_score"] <= 25
    assert result["human_score"] >= 75
    assert result["badge"] == "✅"
    assert result["status"] == "Likely Human"
    assert result["flagged_phrases"] == []


def test_analyze_ai_probability_empty_or_short():
    short_result = detector.analyze_ai_probability("Too short")
    assert short_result["ai_score"] == 0
    assert short_result["human_score"] == 100
    assert short_result["badge"] == "✅"
