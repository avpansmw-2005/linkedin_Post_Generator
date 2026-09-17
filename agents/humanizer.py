"""Humanizer agent refining voice, eliminating AI clichés, and applying user feedback."""

from __future__ import annotations

import logging
from pydantic import BaseModel, Field

from agents import llm_client

logger = logging.getLogger(__name__)


class HumanizedPost(BaseModel):
    refined_text: str = Field(
        description="The polished, highly authentic, humanized LinkedIn post with formatting intact."
    )
    summary_of_changes: str = Field(
        description="A brief 1-sentence note explaining what was refined or how user feedback was incorporated."
    )


HUMANIZER_SYSTEM_PROMPT = """You are an authentic software developer known for clear, practical, and high-signal engineering communication.

Your task is to rewrite or refine a LinkedIn post draft so that it sounds like an actual developer sharing a genuine lesson or discovery, rather than an AI or corporate account.

Strict Guidelines:
1. Banned Clichés: Never use "In today's fast-paced world", "Game changer", "Dive deep", "Delve", "Tapestry", "Harness the power", "It's worth noting", "Beacon of innovation", or "Exciting times ahead".
2. Voice: A curious, knowledgeable software engineer sharing something they learned. Pragmatic, direct, conversational, and technically grounded.
3. Structure: Generous line breaks between short paragraphs for comfortable mobile reading.
4. Faithfulness to Feedback: If user edit notes are provided, follow their explicit instructions precisely.
5. Preserved Elements: Keep any source URLs and relevant hashtags at the bottom."""


def rewrite(
    base_text: str,
    edit_notes: str | None = None,
    story: dict | None = None,
) -> str:
    """Refines the voice of the draft post and applies user edit notes if present."""
    if not base_text:
        return ""

    user_instructions = [f"Original Draft:\n{base_text}\n"]
    if story:
        user_instructions.append(f"Context Story Title: {story.get('title', '')}")
    if edit_notes:
        user_instructions.append(f"User Edit Feedback to Incorporate:\n\"{edit_notes}\"")
    else:
        user_instructions.append("Instruction: Polish this post into an authentic, human engineering voice. Strip all AI fluff.")

    user_prompt = "\n\n".join(user_instructions)

    try:
        result = llm_client.complete(
            system=HUMANIZER_SYSTEM_PROMPT,
            user=user_prompt,
            schema=HumanizedPost,
            temperature=0.5,
        )
        logger.info("Post refined: %s", result.summary_of_changes)
        return result.refined_text

    except Exception as e:
        logger.warning("LLM humanizer failed, returning base text with edit notes appended: %s", e)
        if edit_notes:
            return f"{base_text}\n\n[Note: {edit_notes}]"
        return base_text
