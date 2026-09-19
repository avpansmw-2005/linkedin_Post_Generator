"""Ranker agent scoring news items and picking the top 10 with reasons."""

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
    category: str = Field(
        default="ai_learning",
        description="Category: 'ai_learning' (Priority 1), 'developer_mistake' (Priority 2), or 'latest_news' (Priority 3)",
    )
    score: float = Field(
        description="Score between 1.0 and 10.0 following the preference hierarchy (AI learning: 9.0-10.0, Mistakes: 8.0-8.9, News: 7.0-7.9)"
    )
    reason: str = Field(description="Punchy 1-sentence takeaway: what a developer learns or the pitfall to avoid")


class TopTenRanking(BaseModel):
    top_items: list[ScoredNewsItem] = Field(
        description="List of exactly 10 top-ranked developer stories sorted by score descending, with rich category variety"
    )


# Alias for backwards compatibility with tests and callers
TopFiveRanking = TopTenRanking


RANKER_SYSTEM_PROMPT = """You are a Principal AI Systems Architect and technical thought leader.
Your goal is to evaluate candidate technical articles and pick the top 10 highest-signal, diverse stories to share on LinkedIn.

CONTENT PREFERENCE & VARIETY MANDATE:
You MUST select 10 stories with rich category and topic variety across:
1. 🎓 AI Developer Learning (Target: 4-5 stories, Target Score: 9.0 - 10.0)
   - Hands-on AI system design, autonomous agent workflows, Model Context Protocol (MCP), tool sandboxing.
   - Retrieval-Augmented Generation (RAG) architecture, semantic embeddings, chunking, reranking.
   - Local model inference (vLLM, Ollama, llama.cpp), quantization (GGUF, AWQ, FP8), fine-tuning (LoRA).
   - Structured outputs, prompt engineering, speculative decoding, context caching, evals.
   - Actionable tutorials, architecture benchmarks, and practical engineering skills.

2. ⚠️ Developer Mistakes That Most Developers Do, Pitfalls & Postmortems (Target: 3-4 stories, Target Score: 8.0 - 8.9)
   - Real-world mistakes developers make, anti-patterns, and what NOT to do in production.
   - AI traps: prompt injection vulnerabilities, naive RAG retrieval traps, runaway agent loops, token explosions.
   - Systems traps: connection pool exhaustion, leaky abstractions, indexing errors, concurrency deadlocks.
   - Production postmortems, outage analyses, debugging lessons, and hard-earned engineering takeaways.

3. 🚀 Latest AI News & Model Breakthroughs (Target: 2-3 stories, Target Score: 7.0 - 7.9)
   - Major new model and open-source releases (DeepSeek, Claude, Mistral, OpenAI, Meta Llama).
   - Major framework versions and breakthrough research papers.

VARIETY & DIVERSITY ENFORCEMENT:
- Avoid clustering multiple stories on the exact same model or tool (e.g. do not select 3 DeepSeek posts or 3 Docker posts). Ensure broad, rich variety across different AI domains.
- Freshness & Recency: Stories MUST be latest and current. Stories published within the last 24-48 hours get top preference.
- High Substance: Must contain concrete technical takeaways, not marketing fluff or PR.
- Category Tagging: Assign each item its exact category: 'ai_learning', 'developer_mistake', or 'latest_news'.

STRICTLY REJECT & PENALIZE (Score: 0.0 - 3.0):
- Stale/old stories, buyer's guides, non-technical listicles, corporate drama, funding rounds, spam, or basic fluff.

Return the top 10 stories sorted by score descending. For each story, provide a sharp, technically rigorous 1-sentence developer takeaway explaining what a developer learns or the pitfall to avoid."""


def rank(items: list[NewsItem], top_k: int = 10, mode: str | None = None) -> list[RankedItem]:
    """Evaluates raw news items using the LLM client and returns the top ranked items."""
    if not items:
        logger.warning("No news items provided to ranker.")
        return []

    # If already a small set, directly assign scores without an external LLM roundtrip
    if len(items) <= top_k:
        ranked_fallback: list[RankedItem] = []
        for it in items:
            cat = it.get("category", "ai_learning")
            if mode == "mistakes":
                base_score = 9.5 if cat == "developer_mistake" else (8.5 if cat == "ai_learning" else 7.5)
            elif mode == "news":
                base_score = 9.5 if cat == "latest_news" else (8.5 if cat == "ai_learning" else 7.5)
            else:
                base_score = 9.5 if cat == "ai_learning" else (8.8 if cat == "developer_mistake" else 7.8)
            ranked_fallback.append({
                **it,
                "score": base_score,
                "category": cat,
                "reason": f"High-signal {cat.replace('_', ' ')} story from {it.get('source', 'stream')}.",
            })
        return ranked_fallback

    # Format items for prompt (allow up to 50 candidates for comprehensive variety)
    candidates_text = []
    for idx, it in enumerate(items[:50], start=1):
        cat = it.get("category", "ai_learning")
        rel = it.get("relative_time", "recent")
        candidates_text.append(
            f"[{idx}] Category: {cat} | Published: {rel}\n"
            f"Title: {it.get('title', '')}\n"
            f"Source: {it.get('source', '')}\n"
            f"URL: {it.get('url', '')}\n"
            f"Summary: {it.get('summary', '')}\n"
        )

    mode_instruction = ""
    if mode == "mistakes":
        mode_instruction = "\nSPECIAL DIRECTIVE: The user explicitly requested DEVELOPER MISTAKES, PITFALLS, AND POSTMORTEMS. Prioritize and rank developer mistake/postmortem stories at the very top (scores 9.0-10.0)!\n\n"
    elif mode == "learning":
        mode_instruction = "\nSPECIAL DIRECTIVE: The user explicitly requested AI DEVELOPER LEARNING TOPICS. Prioritize and rank actionable AI learning and architecture stories at the very top (scores 9.0-10.0)!\n\n"
    elif mode == "news":
        mode_instruction = "\nSPECIAL DIRECTIVE: The user explicitly requested LATEST AI NEWS AND MODEL RELEASES. Prioritize and rank fresh model and framework releases at the top!\n\n"

    user_prompt = f"Here are the candidate stories from the latest scan:{mode_instruction}\n" + "\n".join(candidates_text)

    try:
        ranking_result = llm_client.complete(
            system=RANKER_SYSTEM_PROMPT,
            user=user_prompt,
            schema=TopTenRanking,
            temperature=0.3,
        )

        ranked: list[RankedItem] = []
        for scored in ranking_result.top_items[:top_k]:
            orig = next((it for it in items if it.get("url") == scored.url), {})
            ranked.append({
                "title": scored.title,
                "url": scored.url,
                "source": scored.source,
                "summary": scored.summary,
                "published": orig.get("published", ""),
                "category": scored.category or orig.get("category", "ai_learning"),
                "relative_time": orig.get("relative_time", ""),
                "score": scored.score,
                "reason": scored.reason,
            })
        return ranked

    except Exception as e:
        logger.error("LLM ranking failed, falling back to top candidates: %s", e)
        # Fallback to first top_k
        ranked_fallback = []
        for item in items[:top_k]:
            cat = item.get("category", "ai_learning")
            base_score = 9.5 if cat == "ai_learning" else (8.8 if cat == "developer_mistake" else 7.8)
            ranked_fallback.append({
                **item,
                "score": base_score,
                "category": cat,
                "reason": f"High-signal {cat.replace('_', ' ')} story from {item.get('source', 'news stream')}.",
            })
        ranked_fallback.sort(key=lambda x: x["score"], reverse=True)
        return ranked_fallback
