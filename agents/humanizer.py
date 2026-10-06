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


HUMANIZER_SYSTEM_PROMPT = """You are a thoughtful senior software engineer refining a LinkedIn post draft.
Your job is to rewrite the text in clear, normal English that sounds 100% human, eliminating robotic AI signatures while keeping the post engaging, natural, and credible.

CRITICAL TONE & VOCABULARY GUIDELINES:
1. PRESERVE TECHNICAL TERMS (MANDATORY):
   - Keep all concrete technical words, tools, metrics, and architecture terms intact (e.g. latency, KV cache, RAG retrieval, token usage, PostgreSQL, Docker, APIs, GPU memory, concurrency, query plans).
   - Senior engineers and developers care about real engineering mechanisms; never remove or dumb down technical accuracy.
2. USE NORMAL ENGLISH & BAN HARD VOCABULARY:
   - Use simple, everyday, conversational English. Write like a smart engineer chatting with a colleague over coffee.
   - BANNED HARD / PRETENTIOUS VOCABULARY: NEVER use fancy, academic, or obscure words such as:
     ephemeral, paradigm, esoteric, concomitant, heterogeneous, ubiquitous, tapestry, dichotomy, behemoth, delve, harness.
   - Keep sentence structures clean, direct, and easy to read. Avoid convoluted, multi-clause run-ons.
3. STRICT ZERO-HYPHEN RULE:
   - You MUST NOT use ANY hyphens or dashes anywhere in your text! Zero hyphens allowed.
   - NEVER use '-' (hyphen), '—' (em-dash), or '–' (en-dash).
   - Write compound words without hyphens (e.g. write 'real world', 'high signal', 'open source', 'end to end', 'state of the art', 'up to date', 'token aware').
   - For lists, use unicode dots (•), numbers (1., 2.), or clean paragraph line breaks. Never start a bullet with '-'.
   - For pauses, use commas or separate sentences instead of dashes.
   - In benchmark stats, write '68% lower latency' or 'down 40%', never '-68%'.
4. BANNED AI Transition Tropes (Instant 100% AI flags):
   - NEVER use: "The benefits are pretty straightforward:"
   - NEVER use: "Of course, there are some trade-offs."
   - NEVER use: "Curious to hear how others are balancing..."
   - NEVER use: "In today's fast-paced world..."
   - NEVER use: "When it comes to..."
   - NEVER use: "Harness the power", "Game changer", "Dive deep", "Delve", "Tapestry", "Beacon of innovation".
   - NEVER use cheesy marketer slang ("Boom!", "Like a pro", "Instant fortress").
5. Natural Cadence & Authentic Substance:
   - Mix punchy short sentences with clear explanations. Avoid monotonous sentence lengths.
   - Speak with firsthand developer conviction ("When we benchmarked this...", "A hard lesson we learned...", "If you give an LLM shell access...").
   - ZERO High-School Textbook Definitions: Senior engineers already know what basic tools are ("Docker is a container tool"). Jump straight into how the system works or breaks.
6. Formatting & Layout:
   - Short, readable paragraphs with double line breaks.
   - ZERO Outbound Links: NEVER insert external URLs or http/https links in the body. All links belong in the 1st comment.
   - Preserve the conversation starter question (CTA) and comment pointer ('👇 Check the source in the comments!'), along with hashtags at the bottom.
7. ABSOLUTE SUPREMACY OF USER EDIT DIRECTIVES:
   - When User Edit Feedback is provided, it is a MANDATORY EXECUTIVE ORDER that overrides defaults.
   - If the user commands humor / wit: Inject funny developer satire and relatable engineering comedy (e.g. deploying on Friday, runaway cloud bills, broken pipelines, YAML indentation) using simple, everyday words. Keep vocabulary normal and technical concepts accurate."""


def strip_all_hyphens(text: str) -> str:
    """Deterministically removes and replaces all hyphens, en-dashes, and em-dashes
    from the text, ensuring zero hyphens remain in the English text while preserving
    valid URLs intact.
    """
    if not text:
        return text

    # Protect any URLs so their paths are not broken
    urls: list[str] = []

    def _save_url(m: re.Match) -> str:
        urls.append(m.group(0))
        return f"__URL_PLACEHOLDER_{len(urls)-1}__"

    text = re.sub(r'https?://\S+', _save_url, text)

    # 1. Replace em-dashes, en-dashes, and unicode dash variants with clean comma or space
    for dash in ["—", "–", "‒", "―", "−", "‐", "‑"]:
        text = text.replace(dash, ", ")

    # 2. Handle line-start bullet hyphens: "- item" -> "• item"
    lines = []
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped.startswith("- ") or stripped.startswith("• -"):
            line = re.sub(r'^\s*[-•]\s*[-–—]?\s*', '• ', line)
        elif stripped.startswith("-"):
            line = re.sub(r'^\s*[-–—]\s*', '• ', line)
        # Replace inline spaced dash " - " or " -- " -> ", "
        line = re.sub(r'\s+[-–—]+\s+', ', ', line)
        lines.append(line)
    text = "\n".join(lines)

    # 3. Handle negative numbers or benchmark stats: "-68%" -> "68%"
    text = re.sub(r'(^|\s)-(\d+)', r'\1\2', text)

    # 4. Handle compound words: "real-world" -> "real world", "high-signal" -> "high signal"
    text = re.sub(r'([a-zA-Z0-9])-([a-zA-Z0-9])', r'\1 \2', text)

    # 5. Eliminate any remaining stray '-' or unicode dashes
    for ch in ["-", "—", "–", "‒", "―", "−", "‐", "‑"]:
        text = text.replace(ch, "")

    # 6. Clean up any accidental double spaces or comma anomalies resulting from replacements
    text = re.sub(r'[ ]{2,}', ' ', text)
    text = re.sub(r',\s*,', ',', text)
    text = re.sub(r'\s+,', ',', text)

    # Restore URLs
    for idx, u in enumerate(urls):
        text = text.replace(f"__URL_PLACEHOLDER_{idx}__", u)

    return text


def enforce_user_constraints(text: str, edit_notes: str | None) -> str:
    """Deterministically validates and enforces user editorial constraints on the generated text.
    Unconditionally guarantees zero hyphens or dashes in all outputs, and obeys explicit user commands
    (e.g. removing emojis, hashtags).
    """
    if not text:
        return text

    notes_lower = (edit_notes or "").lower()

    # 1. Hashtag Removal Constraint
    if any(k in notes_lower for k in ["remove hashtag", "no hashtag", "delete hashtag", "strip hashtag", "without hashtag"]):
        logger.info("Deterministic gate: Enforcing zero-hashtag constraint per user directive")
        text = re.sub(r'#\w+', '', text).strip()

    # 2. Emoji Removal Constraint
    if any(k in notes_lower for k in ["remove emoji", "no emoji", "delete emoji", "strip emoji", "without emoji"]):
        logger.info("Deterministic gate: Enforcing zero-emoji constraint per user directive")
        try:
            import emoji
            text = emoji.replace_emoji(text, replace='')
        except Exception:
            text = re.sub(r'[\U00010000-\U0010ffff]', '', text)

    # 3. Universal Zero-Hyphen Constraint (Mandatory for all outputs)
    text = strip_all_hyphens(text)

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
                "- Use simple, normal, conversational English. Keep concrete technical terms (e.g. latency, KV cache, token usage, PostgreSQL, Docker, APIs) intact, but use clean, everyday words.\n"
                "- BANNED: Do NOT use hard, pretentious, or academic vocabulary (such as ephemeral, paradigm, esoteric, concomitant, heterogeneous, ubiquitous, tapestry, dichotomy).\n"
                "- STRICT ZERO-HYPHEN RULE: Never use '-' or '—' or '–'. Write compound words without hyphens (real world, open source, high signal). For lists, use unicode dots (•) or numbers.\n"
                "- Natural cadence: Mix short punchy sentences with simple, direct explanations.\n"
                "- Eliminate ALL textbook definitions and formulaic transitions.\n"
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
                "1. Keep technical terms intact, but rewrite in simple everyday words without hard or pretentious vocabulary.",
                "2. ZERO hyphens or dashes allowed. Write compound words with spaces.",
                "3. Alternate short and clear sentences naturally.",
                "4. Remove all textbook definitions and AI transition phrases.",
                "5. Retain technical accuracy, debate question CTA, comment pointer, and hashtags. NO outbound URLs.",
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
            f"2. ZERO HYPHENS: DO NOT use ANY '-' or '—' or '–' characters anywhere in the post. Use flowing narrative sentences, numbered lists (1., 2.), unicode dots (•), or clean line breaks instead.\n"
            f"3. LANGUAGE: Use normal, clear English with simple vocabulary. Keep real technical terms intact, but ban hard, pretentious words.\n"
            f"4. If the user asks for humor or tone changes, apply them using relatable, simple tech comedy.\n"
            f"5. Maintain all technical accuracy and keep outbound URLs out of the body."
        )
    else:
        user_instructions.append(
            "Instruction: Polish this post into an authentic, human engineering voice using simple, normal English and zero hyphens. "
            "Keep technical terms (e.g. latency, cache, tokens, queries) intact, but eliminate hard, pretentious vocabulary. Keep outbound URLs out of the body."
        )

    if is_humor_requested:
        user_instructions.append(
            "🎭 HUMOR & SATIRE DIRECTIVE: Make this post hilarious, witty, and rich in relatable developer satire! "
            "Joke about production realities, terminal misery, and engineering hype using simple, punchy, everyday words. "
            "Do NOT use hard or pretentious vocabulary. Keep technical terms accurate and hyphens at zero."
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
