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


WRITER_SYSTEM_PROMPT = """You are a hands-on software developer sharing an authentic technical discovery or lesson learned on LinkedIn.

Persona & Voice:
1. First-Person Perspective: Write like a developer talking to fellow developers ("Something interesting I learned today...", "I was digging into how X works...", "As developers, we often run into...").
2. Core Technical Insight: Clearly explain:
   - What the challenge or status quo was.
   - How this tool, architecture, or technique solves it under the hood.
   - What practical lesson engineers can take away.
3. No Influencer Fluff: Zero generic marketing speak, no "In today's fast-paced landscape", no over-the-top hype. Keep it grounded, curious, and technically sharp.
4. Formatting: Short readable paragraphs (1-2 sentences), clean bullet points, code or pattern mentions where helpful.
5. Closing: Ask a genuine technical question inviting discussion with other developers.
6. Hashtags: 3 to 5 developer-focused tags (e.g. #SoftwareEngineering, #Python, #SystemDesign, #DeveloperTools)."""


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
