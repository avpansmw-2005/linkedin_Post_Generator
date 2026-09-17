"""Post writer agent generating structured LinkedIn drafts, hashtags, and visual concepts."""

from __future__ import annotations

import logging
from pydantic import BaseModel, Field

from state import RankedItem
from agents import llm_client

logger = logging.getLogger(__name__)


class LinkedInDraft(BaseModel):
    hook: str = Field(description="Attention-grabbing 1-2 sentence opening hook designed to stop the scroll on LinkedIn.")
    body: str = Field(description="Core explanation formatted with concise paragraphs and clean bullet points explaining the technical breakthrough and practical impact.")
    takeaway: str = Field(description="Actionable engineering takeaway or strategic perspective.")
    call_to_action: str = Field(description="Engaging open-ended question prompting thoughtful discussion in comments.")
    hashtags: list[str] = Field(description="3 to 5 high-relevance hashtags (e.g. ['#AI', '#MachineLearning', '#LLM']).")
    image_concept: str = Field(description="A concise visual theme concept for the background card (e.g. 'Geometric glowing latent space embeddings in deep slate purple').")


WRITER_SYSTEM_PROMPT = """You are an elite AI Software Engineer writing high-credibility technical breakdowns on LinkedIn.

Your mission is to showcase deep hands-on mastery of modern AI engineering, agent architectures, and system design in a way that positions you as a top-tier engineer that leading IT companies, CTOs, and recruiters actively want to approach.

Key Post Structure & Tone:
1. First-Person Authority: Write with direct engineering confidence ("When deploying autonomous agents in production, security isn't optional—it's an architecture problem.", "A key pattern I've been studying recently is...").
2. Deep Technical Breakdown: Explain the exact mechanism under the hood:
   - System boundaries (e.g. sandboxed execution, micro-VMs, MCP permission scopes).
   - Attack vectors & defenses (e.g. prompt injection, tool hijacking, credential isolation).
   - Practical engineering tradeoff (latency vs security, token overhead vs safety).
3. Zero Marketing Fluff: No "In today's fast-paced world", no generic listicles, no surface-level AI hype. Speak like an engineer who actually writes code and designs production infrastructure.
4. Formatting: Punchy 1-2 sentence paragraphs, generous line breaks, clean bullet points.
5. Closing: A sharp technical question for senior engineering peers.
6. Hashtags: 3 to 5 high-signal tags (e.g. #AIEngineering #SystemDesign #SoftwareArchitecture #Python #Agents)."""


def write(story: RankedItem) -> dict:
    """Generates a complete post draft from a chosen ranked story."""
    user_prompt = (
        f"Chosen Story:\n"
        f"Title: {story.get('title', '')}\n"
        f"Source: {story.get('source', '')}\n"
        f"URL: {story.get('url', '')}\n"
        f"Summary: {story.get('summary', '')}\n"
        f"Selection Reason: {story.get('reason', '')}\n\n"
        f"Draft a compelling, technically rigorous LinkedIn post based on this story."
    )

    try:
        draft = llm_client.complete(
            system=WRITER_SYSTEM_PROMPT,
            user=user_prompt,
            schema=LinkedInDraft,
            temperature=0.6,
        )

        # Assemble full text
        tag_line = " ".join(t if t.startswith("#") else f"#{t}" for t in draft.hashtags)
        source_url = story.get("url", "")
        source_citation = f"\n\nSource & Paper: {source_url}" if source_url else ""

        assembled_post = (
            f"{draft.hook}\n\n"
            f"{draft.body}\n\n"
            f"💡 Key Takeaway: {draft.takeaway}\n\n"
            f"{draft.call_to_action}\n"
            f"{source_citation}\n\n"
            f"{tag_line}"
        )

        return {
            "text": assembled_post,
            "tags": draft.hashtags,
            "image_concept": draft.image_concept,
            "raw_draft": draft.model_dump(),
        }

    except Exception as e:
        logger.error("LLM writing failed, falling back to template draft: %s", e)
        fallback_tags = ["#AI", "#TechNews", "#SoftwareEngineering"]
        fallback_text = (
            f"🚀 {story.get('title', 'Latest AI Breakthrough')}\n\n"
            f"{story.get('summary', '')}\n\n"
            f"Why it matters: {story.get('reason', 'Significant milestone in AI development.')}\n\n"
            f"Read more: {story.get('url', '')}\n\n"
            f"{' '.join(fallback_tags)}"
        )
        return {
            "text": fallback_text,
            "tags": fallback_tags,
            "image_concept": "Abstract neural gradient background",
            "raw_draft": {},
        }
