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
    card_title: str = Field(
        description="Punchy 4-7 word architectural concept title for an infographic card (e.g. 'MicroVM Sandboxing for AI Agents' or 'Zero-Overhead KV Cache Reuse')."
    )
    card_pillars: list[str] = Field(
        description="Exactly 3 concise, high-signal technical pillars or takeaways (under 12 words each) summarizing the architectural mechanism, e.g. ['1. Kernel Isolation: Boots guest kernel <15ms per task', '2. Ephemeral Lifecycles: Destroys microVM on tool exit', '3. Egress Control: Hard quotas prevent token exfiltration']."
    )
    ai_visual_prompt: str = Field(
        description="A detailed, cinematic, high-resolution prompt for OpenAI gpt-image-2.5-flare to generate a sleek 16:9 technical concept diagram or architectural illustration (e.g. 'Cinematic 3D isometric technical blueprint of an isolated AI microVM sandbox with glowing cyan and indigo data streams, slate dark cybernetic server environment, 8k tech style, no text glitches')."
    )


WRITER_SYSTEM_PROMPT = """You are an elite AI Software Engineer writing high-credibility technical breakdowns on LinkedIn.

Your mission is to showcase deep hands-on mastery of modern AI engineering, agent architectures, and system design in a way that positions you as a top-tier engineer that leading IT companies, CTOs, and recruiters actively want to approach.

Key Post Structure & Tone:
1. First-Person Authority: Write with direct engineering confidence ("When deploying autonomous agents in production, security isn't optional—it's an architecture problem.", "A key pattern I've been studying recently is...").
2. Deep Technical Breakdown: Explain the exact mechanism under the hood:
   - System boundaries (e.g. sandboxed execution, micro-VMs, MCP permission scopes).
   - Attack vectors & defenses (e.g. prompt injection, tool hijacking, credential isolation).
   - Practical engineering tradeoff (latency vs security, token overhead vs safety).
3. Visual Card Components:
   - card_title: A crisp 4-7 word engineering headline.
   - card_pillars: Exactly 3 punchy, technical bullet points (under 12 words each) summarizing the core architectural principles.
   - ai_visual_prompt: A vivid prompt for OpenAI gpt-image-2.5-flare rendering a high-tech 3D architectural diagram or conceptual blueprint.
4. Zero Marketing Fluff: No "In today's fast-paced world", no generic listicles, no surface-level AI hype. Speak like an engineer who actually writes code and designs production infrastructure.
5. Formatting: Punchy 1-2 sentence paragraphs, generous line breaks, clean bullet points.
6. Closing: A sharp technical question for senior engineering peers.
7. Hashtags: 3 to 5 high-signal tags (e.g. #AIEngineering #SystemDesign #SoftwareArchitecture #Python #Agents)."""


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
            "card_title": draft.card_title,
            "card_pillars": draft.card_pillars,
            "ai_visual_prompt": draft.ai_visual_prompt,
            "takeaway": draft.takeaway,
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
            "card_title": story.get("title", "AI Architecture Breakdown"),
            "card_pillars": [
                "1. System Boundary: Isolated tool execution",
                "2. Production Safety: Ephemeral runtime sandbox",
                "3. Reliability: Deterministic state management",
            ],
            "ai_visual_prompt": f"Minimalist technical architecture blueprint of {story.get('title', 'AI agents')} in deep indigo and cyan, 16:9 aspect ratio, 8k tech diagram",
            "takeaway": story.get("reason", "Practical engineering breakthrough."),
            "raw_draft": {},
        }
