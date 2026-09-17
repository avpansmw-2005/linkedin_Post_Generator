"""Ranker agent scoring news items and picking the top 5 with reasons."""

from __future__ import annotations

import logging
from pydantic import BaseModel, Field

from state import NewsItem, RankedItem
from agents import llm_client

logger = logging.getLogger(__name__)


class ScoredNewsItem(BaseModel):
    index: int = Field(description="1-based index from the candidate list")
    title: str = Field(description="Article title")
    url: str = Field(description="Source URL")
    source: str = Field(description="Publisher/Source")
    summary: str = Field(description="Brief summary")
    score: float = Field(description="Score between 1.0 and 10.0 based on developer learning value and technical substance")
    reason: str = Field(description="Punchy one-sentence developer takeaway: what a developer learns or can apply from this")


class TopFiveRanking(BaseModel):
    top_items: list[ScoredNewsItem] = Field(
        description="List of exactly 5 top-ranked developer stories sorted by score descending"
    )


RANKER_SYSTEM_PROMPT = """You are a Principal AI Systems Architect and technical thought leader.
Your goal is to evaluate technical articles and select the highest-signal stories that an ambitious software engineer can share on LinkedIn to:
1. Demonstrate deep, hands-on mastery of modern AI development (agent security, MCP protocols, sandboxing, inference optimization, RAG architectures, and production reliability).
2. Position the author as an elite technical practitioner that high-growth tech companies, CTOs, and recruiters actively seek out and respect.
3. Highlight actionable architecture insights, code execution boundaries, and system design patterns.

Strictly Reject & Penalize:
- Non-technical articles, buyer's guides, spam, promotional listicles, corporate PR, pricing/account services, and shallow fluff.

Return the top stories sorted by score descending. For each story, provide a sharp, technically rigorous 1-sentence developer takeaway explaining the architectural insight."""


def rank(items: list[NewsItem], top_k: int = 5) -> list[RankedItem]:
    """Evaluates raw news items using the LLM client and returns the top ranked items."""
    if not items:
        logger.warning("No news items provided to ranker.")
        return []

    # Format items for prompt
    candidates_text = []
    for idx, it in enumerate(items[:30], start=1):
        candidates_text.append(
            f"[{idx}] Title: {it.get('title', '')}\n"
            f"Source: {it.get('source', '')}\n"
            f"URL: {it.get('url', '')}\n"
            f"Summary: {it.get('summary', '')}\n"
        )
    user_prompt = "Here are the candidate AI stories from the latest scan:\n\n" + "\n".join(candidates_text)

    try:
        ranking_result = llm_client.complete(
            system=RANKER_SYSTEM_PROMPT,
            user=user_prompt,
            schema=TopFiveRanking,
            temperature=0.3,
        )

        ranked: list[RankedItem] = []
        for scored in ranking_result.top_items[:top_k]:
            ranked.append({
                "title": scored.title,
                "url": scored.url,
                "source": scored.source,
                "summary": scored.summary,
                "published": "",
                "score": scored.score,
                "reason": scored.reason,
            })
        return ranked

    except Exception as e:
        logger.error("LLM ranking failed, falling back to top candidates: %s", e)
        # Fallback to first top_k
        return [
            {
                **item,
                "score": 7.0,
                "reason": f"Selected from {item.get('source', 'news stream')}.",
            }
            for item in items[:top_k]
        ]
