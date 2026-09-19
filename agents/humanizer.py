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
   - ZERO Outbound Links: NEVER insert external URLs or http/https links in the body. All links belong in the 1st comment.
   - Preserve the conversation starter question (CTA) and comment pointer ('👇 Check the source in the comments!'), along with hashtags at the bottom."""


def rewrite_with_feedback_loop(
    base_text: str,
    story: dict | None = None,
    edit_notes: str | None = None,
    max_iterations: int = 3,
    target_ai_score: int = 20,
) -> tuple[str, dict, int]:
    """Iterative reflection self-loop that refines the post, analyzes it with detector,
    and if needed, feeds diagnostic feedback (flagged phrases, low burstiness) back to the LLM
    until the score drops <= target_ai_score or max_iterations is reached.

    Returns:
        (best_text, best_score_info, iterations_completed)
    """
    from agents import detector

    if not base_text:
        return "", detector.analyze_ai_probability(""), 0

    current_draft = base_text
    best_text = base_text
    best_score_info = detector.analyze_ai_probability(base_text)
    iterations_run = 0
    critique_feedback = None

    for iteration in range(1, max_iterations + 1):
        iterations_run = iteration
        user_instructions = [f"Original Draft:\n{current_draft}\n"]
        if story:
            user_instructions.append(f"Context Story Title: {story.get('title', '')}")
        if edit_notes and iteration == 1:
            user_instructions.append(f"User Edit Feedback to Incorporate:\n\"{edit_notes}\"")

        if critique_feedback:
            user_instructions.append(critique_feedback)
        else:
            user_instructions.append(
                "🔥 ULTRA-AGGRESSIVE ANTI-AI REWRITE DIRECTIVE:\n"
                "- Defeat GPTZero and ZeroGPT AI detectors completely (target: < 15% AI score / > 85% Human).\n"
                "- Radically break rhythmic uniformity. Inject extreme burstiness: alternate punchy 2-4 word sentences ('Don't do it.', 'Total silence.', 'Zero exceptions.', 'It failed.') right next to 20-25 word technical explanations.\n"
                "- MANDATORY ASYMMETRY: Do NOT make every sentence short. Write at least two deep, multi-clause technical sentences (20-28 words) directly adjacent to 2-4 word punchy sentences.\n"
                "- Eliminate ALL high-school textbook definitions and generic transitions like 'The benefits are straightforward' or 'Of course, there are trade-offs'.\n"
                "- Frame everything with gritty developer realism and firsthand architectural conviction.\n"
                "- ZERO Outbound URLs: Do NOT include raw links or paper URLs in the body. Keep the debate CTA, comment pointer, and hashtags intact."
            )

        user_prompt = "\n\n".join(user_instructions)
        temp = 0.8  # Higher creativity to shatter formulaic sentence patterns

        try:
            result = llm_client.complete(
                system=HUMANIZER_SYSTEM_PROMPT,
                user=user_prompt,
                schema=HumanizedPost,
                temperature=temp,
            )
            from integrations.linkedin import strip_urls_from_text
            candidate_text, _ = strip_urls_from_text(result.refined_text.strip())
            score_info = detector.analyze_ai_probability(candidate_text)
            logger.info(
                "Humanizer Self-Loop Pass %d/%d: Score=%d%% AI (%d%% Human), Burstiness=%.2f, Flagged=%s",
                iteration,
                max_iterations,
                score_info["ai_score"],
                score_info["human_score"],
                score_info["burstiness"],
                score_info["flagged_phrases"],
            )

            # Update best candidate if better AI score
            if score_info["ai_score"] < best_score_info["ai_score"] or best_text == base_text:
                best_text = candidate_text
                best_score_info = score_info

            # Success condition: AI score <= target_ai_score and no flagged phrases
            if score_info["ai_score"] <= target_ai_score and not score_info["flagged_phrases"]:
                logger.info(
                    "Humanizer Self-Loop succeeded in %d iteration(s) with score %d%% AI.",
                    iteration,
                    score_info["ai_score"],
                )
                return best_text, best_score_info, iteration

            # Prepare critique feedback for next iteration
            flagged_str = ", ".join(f'"{p}"' for p in score_info["flagged_phrases"]) if score_info["flagged_phrases"] else "None"
            critique_lines = [
                f"🚨 DETECTOR CRITIQUE (Pass {iteration} Result: {score_info['ai_score']}% AI score / {score_info['human_score']}% Human):",
                f"- Flagged Stereotypical AI Tropes: {flagged_str} (MANDATORY: Delete completely, do NOT use these words).",
                f"- Sentence Length Variance (Burstiness): {score_info['burstiness']:.2f} (Target: > 7.0).",
                "MANDATORY FIX FOR THIS PASS:",
                "1. Break sentence length uniformity aggressively! Place 2-to-3 word sentences ('Zero exceptions.', 'It failed.', 'Don't do it.') immediately before or after 20-word technical sentences.",
                "2. Remove all textbook definitions and AI transition phrases.",
                "3. Speak like an experienced staff engineer writing directly from terminal experience.",
                "4. Retain technical accuracy, debate question CTA, comment pointer, and hashtags. NO outbound URLs.",
            ]
            critique_feedback = "\n".join(critique_lines)
            current_draft = candidate_text

        except Exception as e:
            logger.warning("LLM humanizer pass %d failed: %s", iteration, e)
            break

    return best_text, best_score_info, iterations_run


def rewrite(
    base_text: str,
    edit_notes: str | None = None,
    story: dict | None = None,
    aggressive: bool = False,
) -> str:
    """Refines the voice of the draft post and applies user edit notes if present.
    If aggressive=True, utilizes rewrite_with_feedback_loop to iteratively reduce AI detection.
    """
    if not base_text:
        return ""

    if aggressive:
        best_text, _, _ = rewrite_with_feedback_loop(
            base_text=base_text,
            story=story,
            edit_notes=edit_notes,
            max_iterations=3,
            target_ai_score=20,
        )
        return best_text

    user_instructions = [f"Original Draft:\n{base_text}\n"]
    if story:
        user_instructions.append(f"Context Story Title: {story.get('title', '')}")
    if edit_notes:
        user_instructions.append(f"User Edit Feedback to Incorporate:\n\"{edit_notes}\"")
    else:
        user_instructions.append("Instruction: Polish this post into an authentic, human engineering voice. Strip all AI fluff. Keep outbound URLs out of the body.")

    user_prompt = "\n\n".join(user_instructions)

    try:
        result = llm_client.complete(
            system=HUMANIZER_SYSTEM_PROMPT,
            user=user_prompt,
            schema=HumanizedPost,
            temperature=0.5,
        )
        logger.info("Post refined: %s", result.summary_of_changes)
        from integrations.linkedin import strip_urls_from_text
        clean_refined, _ = strip_urls_from_text(result.refined_text)
        return clean_refined

    except Exception as e:
        logger.warning("LLM humanizer failed, returning base text with edit notes appended: %s", e)
        if edit_notes:
            return f"{base_text}\n\n[Note: {edit_notes}]"
        return base_text
