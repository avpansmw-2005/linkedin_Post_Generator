"""Humanizer agent refining voice, eliminating AI clichés, and applying user feedback."""

from __future__ import annotations

import re
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
   - Preserve the conversation starter question (CTA) and comment pointer ('👇 Check the source in the comments!'), along with hashtags at the bottom.
6. ABSOLUTE SUPREMACY OF USER EDIT DIRECTIVES:
   - When User Edit Feedback / Directives are passed, they are MANDATORY EXECUTIVE ORDERS that OVERRIDE all default formatting and styling rules.
   - If the user commands to remove hyphens, dashes, or bullet points: You MUST NEVER output '-' or '—' anywhere in the post! Use natural flowing narrative sentences, numbered lists (1., 2.), unicode dots (•), or paragraph breaks instead.
   - If the user commands to add humor / wit: You MUST inject hilarious developer satire, witty analogies, and relatable engineering comedy.
   - If the user commands to remove hashtags, emojis, or change specific sentences: You MUST do so immediately.
   - Disobeying an explicit user edit command is strictly forbidden."""


def enforce_user_constraints(text: str, edit_notes: str | None) -> str:
    """Deterministically validates and enforces user editorial constraints on the generated text.
    Guarantees 100% compliance with explicit user commands (e.g. removing hyphens, emojis, hashtags).
    """
    if not edit_notes or not text:
        return text

    notes_lower = edit_notes.lower()

    # 1. Hyphen & Dash Removal Constraint
    if any(k in notes_lower for k in [
        "remove hyphen", "no hyphen", "delete hyphen", "strip hyphen", "without hyphen",
        "remove dash", "no dash", "remove all hyphen", "get rid of hyphen", "eliminate hyphen",
        "drop hyphen", "without any hyphen", "don't use hyphen", "dont use hyphen"
    ]):
        logger.info("Deterministic gate: Enforcing zero-hyphen constraint per user directive")
        # Replace em-dashes and en-dashes
        text = text.replace("—", ", ").replace("–", ", ")

        # Replace bullet points starting with hyphens
        lines = []
        for line in text.split("\n"):
            stripped = line.strip()
            if stripped.startswith("- "):
                line = re.sub(r'^\s*-\s*', '', line)
            elif stripped.startswith("-"):
                line = re.sub(r'^\s*-\s*', '', line)
            # Replace inline parenthetical hyphens " - " with ", "
            line = re.sub(r'\s+-\s+', ', ', line)
            lines.append(line)
        text = "\n".join(lines)

        # Replace compound word hyphens with spaces (e.g. "real-world" -> "real world", "high-signal" -> "high signal")
        text = re.sub(r'([a-zA-Z0-9])-([a-zA-Z0-9])', r'\1 \2', text)
        # Eliminate any remaining stray '-'
        text = text.replace("-", "")

    # 2. Hashtag Removal Constraint
    if any(k in notes_lower for k in ["remove hashtag", "no hashtag", "delete hashtag", "strip hashtag", "without hashtag"]):
        logger.info("Deterministic gate: Enforcing zero-hashtag constraint per user directive")
        text = re.sub(r'#\w+', '', text).strip()

    # 3. Emoji Removal Constraint
    if any(k in notes_lower for k in ["remove emoji", "no emoji", "delete emoji", "strip emoji", "without emoji"]):
        logger.info("Deterministic gate: Enforcing zero-emoji constraint per user directive")
        try:
            import emoji
            text = emoji.replace_emoji(text, replace='')
        except Exception:
            text = re.sub(r'[\U00010000-\U0010ffff]', '', text)

    return text


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
    humor: bool = False,
) -> str:
    """Refines the voice of the draft post, strictly applies user edit notes,
    and optionally injects developer humor and satire.
    If aggressive=True, utilizes rewrite_with_feedback_loop to iteratively reduce AI detection.
    """
    if not base_text:
        return ""

    # Detect humor requested in edit notes
    is_humor_requested = humor or (
        bool(edit_notes) and any(
            h in edit_notes.lower()
            for h in ["humor", "funny", "wit", "witty", "joke", "jokes", "comedy", "satire", "sarcastic"]
        )
    )

    if aggressive:
        best_text, _, _ = rewrite_with_feedback_loop(
            base_text=base_text,
            story=story,
            edit_notes=edit_notes,
            max_iterations=3,
            target_ai_score=20,
        )
        return enforce_user_constraints(best_text, edit_notes)

    user_instructions = [f"Original Draft:\n{base_text}\n"]
    if story:
        user_instructions.append(f"Context Story Title: {story.get('title', '')}")

    if edit_notes:
        user_instructions.append(
            f"🚨 CRITICAL USER EDIT DIRECTIVE (MANDATORY EXECUTIVE OVERRIDE):\n"
            f"The user has reviewed the draft and issued this specific instruction:\n"
            f">>> \"{edit_notes}\" <<<\n\n"
            f"MANDATORY COMPLIANCE RULES:\n"
            f"1. You MUST obey the user's instruction with 100% precision. It overrides any default style rule.\n"
            f"2. If the user asks to remove hyphens, dashes, or bullet points: DO NOT use ANY '-' or '—' characters anywhere in the post. Use flowing narrative sentences, numbered lists (1., 2.), unicode dots (•), or clean line breaks instead.\n"
            f"3. If the user asks to add or remove anything, execute it completely.\n"
            f"4. If the user asks for humor or tone changes, apply them fully.\n"
            f"5. Maintain all technical accuracy and keep outbound URLs out of the body."
        )
    else:
        user_instructions.append("Instruction: Polish this post into an authentic, human engineering voice. Strip all AI fluff. Keep outbound URLs out of the body.")

    if is_humor_requested:
        user_instructions.append(
            "🎭 HUMOR & SATIRE DIRECTIVE: Make this post hilarious, witty, and rich in relatable developer satire! "
            "Joke about production realities, terminal misery, and engineering hype while maintaining technical accuracy."
        )

    user_prompt = "\n\n".join(user_instructions)
    temp = 0.7 if is_humor_requested else 0.5

    try:
        result = llm_client.complete(
            system=HUMANIZER_SYSTEM_PROMPT,
            user=user_prompt,
            schema=HumanizedPost,
            temperature=temp,
        )
        logger.info("Post refined: %s", result.summary_of_changes)
        from integrations.linkedin import strip_urls_from_text
        clean_refined, _ = strip_urls_from_text(result.refined_text)

        # Deterministically verify and enforce user constraints
        constrained = enforce_user_constraints(clean_refined, edit_notes)
        return constrained

    except Exception as e:
        logger.warning("LLM humanizer failed, returning base text with edit notes applied: %s", e)
        fallback = enforce_user_constraints(base_text, edit_notes)
        if edit_notes:
            return f"{fallback}\n\n[Note: {edit_notes}]"
        return fallback
