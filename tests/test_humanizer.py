"""Unit tests for the Humanizer agent and iterative self-correction loop."""

from unittest.mock import patch, MagicMock
import pytest
from agents import humanizer
from agents.humanizer import HumanizedPost


def test_rewrite_with_feedback_loop_empty():
    text, score_info, iterations = humanizer.rewrite_with_feedback_loop("")
    assert text == ""
    assert iterations == 0
    assert score_info["ai_score"] == 0


def test_rewrite_with_feedback_loop_terminates_on_good_score():
    human_sample = (
        "If you give an autonomous agent bash access on raw metal, you're one hallucinated rm command away from a postmortem.\n\n"
        "Don't do it.\n\n"
        "We run each agent in an ephemeral rootless Docker container with a read-only tmpfs and capped memory cgroups. "
        "Network egress is locked down with strict iptables rules. Total silence.\n\n"
        "Startup latency added 180ms per task, but the blast radius dropped to zero.\n\n"
        "Are you isolating agent execution at the namespace boundary yet?"
    )

    mock_llm_response = MagicMock()
    mock_llm_response.refined_text = human_sample
    mock_llm_response.summary_of_changes = "Refined voice"

    with patch("agents.llm_client.complete", return_value=mock_llm_response):
        best_text, score_info, iterations = humanizer.rewrite_with_feedback_loop(
            "Draft that needs humanizing",
            max_iterations=3,
            target_ai_score=25,
        )
        assert iterations == 1
        assert score_info["ai_score"] <= 25
        assert score_info["status"] == "Likely Human"
        assert best_text == human_sample


def test_rewrite_with_feedback_loop_iterates_on_high_score():
    # Pass 1 produces robotic text with hallmark phrase
    robotic_sample = (
        "The benefits are pretty straightforward: isolation and security. "
        "Of course, there are some trade-offs in terms of memory overhead. "
        "Curious to hear how others are balancing this in today's fast-paced world!"
    )
    # Pass 2 produces punchy human text
    human_sample = (
        "Don't trust LLMs on bare metal.\n\n"
        "When our background agent ran an unconstrained file operation, it wiped our cache directory in 40ms. Total disaster.\n\n"
        "We rebuilt the sandbox using rootless microVMs and read-only tmpfs. Zero incidents since."
    )

    resp1 = MagicMock(refined_text=robotic_sample, summary_of_changes="First pass")
    resp2 = MagicMock(refined_text=human_sample, summary_of_changes="Second pass with critique")

    with patch("agents.llm_client.complete", side_effect=[resp1, resp2]):
        best_text, score_info, iterations = humanizer.rewrite_with_feedback_loop(
            robotic_sample,
            max_iterations=3,
            target_ai_score=25,
        )
        assert iterations == 2
        assert score_info["ai_score"] <= 25
        assert "Total disaster" in best_text
        assert "The benefits are pretty straightforward" not in best_text
