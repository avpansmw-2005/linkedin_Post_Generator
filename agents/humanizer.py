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


HUMANIZER_SYSTEM_PROMPT = """You are a battle-tested Principal Software Engineer refining a LinkedIn post draft.
Your job is to rewrite the text so it reads 100% human, eliminating robotic AI signatures and completely defeating AI detectors (ZeroGPT, CopyLeaks, GPTZero).

CRITICAL ANTI-DETECTION HEURISTICS:
1. High Burstiness & Asymmetric Rhythm:
   - Mix ultra-short 2-to-4 word sentences ("Don't do it.", "It failed.", "Zero exceptions.") with dense, highly specific 20-word technical explanations.
   - Never write three sentences of uniform length in a row.
   - Break monotony with natural developer cadence, contractions (we've, doesn't, isn't), and occasional sentence fragments.
2. ZERO High-School Textbook Definitions:
   - NEVER explain what basic tools are ("Docker is a containerization platform", "Containers are lightweight units"). Senior engineers already know.
   - Jump straight into the architectural decision, the kernel boundary, the benchmark latency, or the edge-case failure mode.
3. BANNED AI Transition Tropes (Instant 100% AI flags):
   - NEVER use: "The benefits are pretty straightforward:"
   - NEVER use: "Of course, there are some trade-offs."
   - NEVER use: "Curious to hear how others are balancing..."
   - NEVER use: "In today's fast-paced world..."
   - NEVER use: "When it comes to..."
   - NEVER use: "Harness the power", "Game changer", "Dive deep", "Delve", "Tapestry", "Beacon of innovation".
   - NEVER use cheesy marketer slang ("Boom!", "Like a pro", "Instant fortress").
4. Authentic Engineering Substance:
   - Speak with first-person technical authority ("When we benchmarked...", "A hard lesson we learned...", "If you give an LLM bash access...").
   - Mention concrete technical levers: p99 latency, kernel namespaces, read-only tmpfs, memory footprints, CVEs, eBPF, gVisor vs microVMs.
5. Formatting & Layout:
   - Short, punchy paragraphs with double line breaks.
   - Preserve any source URLs and hashtags at the bottom."""


def rewrite(
    base_text: str,
    edit_notes: str | None = None,
    story: dict | None = None,
    aggressive: bool = False,
) -> str:
    """Refines the voice of the draft post and applies user edit notes if present.
    If aggressive=True, aggressively rewrites to maximize burstiness and drive AI score to 0%.
    """
    if not base_text:
        return ""

    user_instructions = [f"Original Draft:\n{base_text}\n"]
    if story:
        user_instructions.append(f"Context Story Title: {story.get('title', '')}")
    if edit_notes:
        user_instructions.append(f"User Edit Feedback to Incorporate:\n\"{edit_notes}\"")
    elif aggressive:
        user_instructions.append(
            "🔥 ULTRA-AGGRESSIVE ANTI-AI REWRITE DIRECTIVE:\n"
            "- Defeat GPTZero and ZeroGPT AI detectors completely (target: < 10% AI score).\n"
            "- Radically break rhythmic uniformity. Inject extreme burstiness: alternate punchy 2-4 word sentences ('Don't do it.', 'Total silence.', 'Zero exceptions.') right next to 25-word technical explanations.\n"
            "- Eliminate ALL high-school textbook definitions and generic transitions like 'The benefits are straightforward' or 'Of course, there are trade-offs'.\n"
            "- Frame everything with gritty developer realism and firsthand architectural conviction.\n"
            "- Keep all technical facts, source links, and hashtags intact."
        )
    else:
        user_instructions.append("Instruction: Polish this post into an authentic, human engineering voice. Strip all AI fluff.")

    user_prompt = "\n\n".join(user_instructions)
    temp = 0.75 if aggressive else 0.5

    try:
        result = llm_client.complete(
            system=HUMANIZER_SYSTEM_PROMPT,
            user=user_prompt,
            schema=HumanizedPost,
            temperature=temp,
        )
        logger.info("Post refined (aggressive=%s): %s", aggressive, result.summary_of_changes)
        return result.refined_text

    except Exception as e:
        logger.warning("LLM humanizer failed, returning base text with edit notes appended: %s", e)
        if edit_notes:
            return f"{base_text}\n\n[Note: {edit_notes}]"
        return base_text
