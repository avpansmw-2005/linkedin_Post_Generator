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
    call_to_action: str = Field(
        description="Targeted, debate-sparking open-ended question prompting peer discussion and comments. BANNED: passive summary statements like 'Bottom line:' or 'In conclusion:'."
    )
    comment_pointer: str = Field(
        default="👇 Check the source paper in the comments!",
        description="A punchy 1-line pointer directing readers to find the link/paper in the comments (e.g. '👇 Check the source paper in the comments!' or '👇 Link to the paper & repo in the comments!')."
    )
    first_comment: str = Field(
        description="The exact text for the very first comment posted under the publication, containing the link to the paper/source and a friendly note (e.g. 'Here is the link to the paper & code 👇\\nhttps://...')."
    )
    hashtags: list[str] = Field(description="3 to 5 high-relevance hashtags (e.g. ['#AI', '#MachineLearning', '#LLM']).")
    card_title: str = Field(
        description="Punchy 4-7 word architectural concept title for an infographic card (e.g. 'Token-Aware Caching for LLMs' or 'Zero-Overhead KV Cache Reuse')."
    )
    card_pillars: list[str] = Field(
        description="Exactly 3 concise, high-signal technical pillars or takeaways (under 12 words each) summarizing the architectural mechanism."
    )
    code_snippet: str | None = Field(
        default=None,
        description="A clean 4-8 line code snippet, config block (YAML/JSON/Python/Redis), or data flow pseudo-diagram illustrating the technical mechanism for high dwell-time visuals."
    )
    benchmark_stat: str | None = Field(
        default=None,
        description="A punchy quantitative stat if applicable, e.g. '-68% Latency', '4.2x KV Reuse', or '<15ms Boot Time'."
    )
    ai_visual_prompt: str = Field(
        description="A detailed prompt for generating a crisp, minimalist 2D/isometric technical system architecture diagram or data flow blueprint. BANNED: generic sci-fi server rooms, generic glowing cubes, or abstract cyborg stock art."
    )


WRITER_SYSTEM_PROMPT = """You are an elite, battle-tested Principal Infrastructure & AI Systems Architect writing on LinkedIn.

Your goal is to write raw, authentic, high-signal engineering thoughts that read 100% human, maximize reach and dwell time, and completely defeat AI detectors (ZeroGPT, CopyLeaks, GPTZero).

CRITICAL LINK REACH POLICY (ZERO OUTBOUND LINKS IN BODY):
1. LinkedIn's feed algorithm heavily penalizes posts containing outbound URLs because it wants to keep users on its platform.
2. NEVER include any http:// or https:// URLs in the hook, body, takeaway, or call_to_action.
3. The post body MUST conclude with your debate-sparking question (call_to_action), followed immediately by your comment_pointer ("👇 Check the source paper in the comments!").
4. Drop the actual paper/article URL exclusively into the first_comment field (e.g. "Here's the link to the paper & repo 👇\\nhttps://...").

MANDATORY CONVERSATION STARTER (CTA):
1. LinkedIn's algorithm prioritizes active comment discussions and debate over passive likes.
2. NEVER end the post with a summary statement ("Bottom line: Redis's new cache could seriously cut LLM costs..."). While informative, it gives readers zero reason to comment.
3. End with a targeted, debate-sparking question aimed at practitioners to provoke peer discussion.
   Examples:
   - "Are you currently building custom caching layers for your LLM pipelines, or relying on native provider caching? Let's discuss in the comments."
   - "Have you hit context window memory bottlenecks with long-running agent loops yet, or are you still relying on basic truncation?"
   - "Would you trust an ephemeral microVM sandbox in production, or are gVisor/container namespaces enough for your threat model?"

VISUAL OPTIMIZATION & DWELL TIME:
1. Generic 3D AI server art blends into feeds. Technical posts perform dramatically better when paired with a clean code snippet, terminal output, benchmark stat, or architecture flow diagram.
2. Provide a realistic 4-8 line code/config snippet in code_snippet (e.g., Python config, Redis cache decorator, or YAML pipeline).
3. If an ai_visual_prompt is generated, mandate a clean, high-contrast 2D/isometric system architecture diagram or data flow blueprint with labeled boxes. NEVER prompt for generic sci-fi servers, glowing cyber brains, or abstract AI faces.

TAILORED CONTENT ARCHETYPES (BY CATEGORY):
1. For 'developer_mistake' (Mistakes Developers Make / Pitfalls / Postmortems):
   - Hook: Call out the specific pitfall or silent bug directly ("Most teams make this mistake when configuring RAG retrieval:", "Here's the silent failure mode in autonomous agent loops:").
   - Body: Break down what developers assume vs what actually breaks under the hood. Detail the exact failure mechanism (memory leak, socket exhaustion, hallucination loop, race condition).
   - Takeaway: The production-tested fix and the rule of thumb to prevent it.
   - card_pillars: Exactly 3 pillars structured as ['1. Anti-Pattern: ...', '2. Failure Mode: ...', '3. Production Fix: ...'].

2. For 'ai_learning' (AI Concepts, Architectures, Tutorials):
   - Hook: Introduce the actionable AI concept, agent protocol (MCP), or local inference technique developers should learn today.
   - Body: Explain the architectural mechanism under the hood with concrete technical levers (token latency, KV cache reuse, sandbox isolation).
   - Takeaway: Actionable developer guidance to implement it in real projects.
   - card_pillars: Exactly 3 core architectural principles or implementation steps.

3. For 'latest_news' (Model Releases & Breakthroughs):
   - Hook: High-signal technical announcement without marketing hype.
   - Body: Architectural differentiator, benchmark numbers, and practical impact on engineering roadmaps.
   - Takeaway: What this changes for production systems.
   - card_pillars: Exactly 3 key technical capabilities or benchmark breakthroughs.

CRITICAL ANTI-DETECTION HEURISTICS:
1. High Burstiness & Natural Rhythm:
   - Mix ultra-short 2-to-4 word sentences ("Don't do it.", "It failed.", "Zero exceptions.") with dense, highly specific 20-word technical explanations.
   - Never write three sentences of uniform length in a row.
   - Use natural contractions (we've, doesn't, isn't) and occasional sentence fragments.
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
   - Mention concrete technical levers: p99 latency, kernel namespaces, read-only tmpfs, memory footprints, CVEs, eBPF, gVisor vs microVMs."""


def write(story: RankedItem) -> dict:
    """Generates a complete post draft from a chosen ranked story."""
    category = story.get("category", "ai_learning")
    user_prompt = (
        f"Chosen Story:\n"
        f"Category: {category}\n"
        f"Title: {story.get('title', '')}\n"
        f"Source: {story.get('source', '')}\n"
        f"URL: {story.get('url', '')}\n"
        f"Summary: {story.get('summary', '')}\n"
        f"Selection Reason: {story.get('reason', '')}\n\n"
        f"Draft a compelling, technically rigorous LinkedIn post based on this {category.replace('_', ' ')} story. "
        f"Remember: NEVER include the outbound URL in the body text; set first_comment with the URL and end the post with a debate-sparking CTA and comment pointer."
    )

    try:
        draft = llm_client.complete(
            system=WRITER_SYSTEM_PROMPT,
            user=user_prompt,
            schema=LinkedInDraft,
            temperature=0.6,
        )

        # Assemble full text WITHOUT external links
        tag_line = " ".join(t if t.startswith("#") else f"#{t}" for t in draft.hashtags)
        pointer = draft.comment_pointer.strip() if getattr(draft, "comment_pointer", None) else "👇 Check the source paper in the comments!"

        assembled_post = (
            f"{draft.hook}\n\n"
            f"{draft.body}\n\n"
            f"💡 Key Takeaway: {draft.takeaway}\n\n"
            f"{draft.call_to_action}\n\n"
            f"{pointer}\n\n"
            f"{tag_line}"
        )

        # Double check: strip any accidental URLs from body
        from integrations.linkedin import strip_urls_from_text
        clean_post, body_extracted_urls = strip_urls_from_text(assembled_post)

        source_url = story.get("url", "")
        all_urls = [u for u in [source_url] + body_extracted_urls if u]
        primary_url = all_urls[0] if all_urls else ""

        first_comment = (draft.first_comment or "").strip()
        if not first_comment and primary_url:
            first_comment = f"Here's the link to the paper & discussion 👇\n{primary_url}"
        elif primary_url and primary_url not in first_comment:
            first_comment = f"{first_comment}\n{primary_url}"

        return {
            "text": clean_post,
            "tags": draft.hashtags,
            "card_title": draft.card_title,
            "card_pillars": draft.card_pillars,
            "code_snippet": draft.code_snippet,
            "benchmark_stat": draft.benchmark_stat,
            "first_comment": first_comment,
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
            f"💡 Why it matters: {story.get('reason', 'Significant milestone in engineering architecture.')}\n\n"
            f"How is your team currently approaching this pattern in production? Let's discuss in the comments.\n\n"
            f"👇 Check the source paper in the comments!\n\n"
            f"{' '.join(fallback_tags)}"
        )
        source_url = story.get("url", "")
        fallback_comment = f"Here's the link to the source paper & code 👇\n{source_url}" if source_url else ""

        return {
            "text": fallback_text,
            "tags": fallback_tags,
            "card_title": story.get("title", "AI Architecture Breakdown"),
            "card_pillars": [
                "1. System Boundary: Isolated tool execution",
                "2. Production Safety: Ephemeral runtime sandbox",
                "3. Reliability: Deterministic state management",
            ],
            "code_snippet": (
                "# Architecture configuration snippet\n"
                "cache_policy:\n"
                "  strategy: token_aware\n"
                "  max_ttl_seconds: 3600\n"
                "  eviction: dynamic_expiry\n"
                "  granularity: prompt_prefix"
            ),
            "benchmark_stat": "-68% Latency | 4.2x Reuse",
            "first_comment": fallback_comment,
            "ai_visual_prompt": f"Minimalist 2D technical system architecture diagram of {story.get('title', 'AI architecture')} in deep indigo and cyan on dark slate, component data flow boxes, 16:9 aspect ratio",
            "takeaway": story.get("reason", "Practical engineering breakthrough."),
            "raw_draft": {},
        }
