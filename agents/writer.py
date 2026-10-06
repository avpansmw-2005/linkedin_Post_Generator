"""Post writer agent generating structured LinkedIn drafts, hashtags, and visual concepts."""

from __future__ import annotations

import logging
from pydantic import BaseModel, Field

from state import RankedItem
from agents import llm_client

from agents.humanizer import strip_all_hyphens

logger = logging.getLogger(__name__)


class LinkedInDraft(BaseModel):
    hook: str = Field(
        description="Attention-grabbing 1-2 sentence opening hook designed to stop the scroll on LinkedIn. "
        "Must use simple normal English without hard vocabulary and contain zero hyphens or dashes."
    )
    body: str = Field(
        description="Core explanation formatted with concise paragraphs and clean bullet points (using unicode dots '•' or numbers, never hyphens) "
        "explaining the technical breakthrough and practical impact in normal, clear English preserving real technical terms."
    )
    takeaway: str = Field(
        description="Actionable engineering takeaway in simple, normal English without hyphens or pretentious vocabulary."
    )
    call_to_action: str = Field(
        description="Targeted, debate-sparking open-ended question prompting peer discussion and comments in simple English without hyphens. "
        "BANNED: passive summary statements like 'Bottom line:' or 'In conclusion:'."
    )
    comment_pointer: str = Field(
        default="👇 Check the source paper in the comments!",
        description="A punchy 1-line pointer directing readers to find the link/paper in the comments (e.g. '👇 Check the source paper in the comments!' or '👇 Link to the paper & repo in the comments!')."
    )
    first_comment: str = Field(
        description="The exact text for the very first comment posted under the publication, containing the link to the paper/source and a friendly note (e.g. 'Here is the link to the paper & code 👇\\nhttps://...')."
    )
    hashtags: list[str] = Field(description="3 to 5 high-relevance hashtags (e.g. ['#AI', '#MachineLearning', '#LLM']). Zero hyphens.")
    card_title: str = Field(
        description="Punchy 4-7 word technical concept title for an infographic card (e.g. 'Token Aware Caching for LLMs' or 'Zero Overhead KV Cache Reuse'). Zero hyphens."
    )
    card_pillars: list[str] = Field(
        description="Exactly 3 concise, high-signal technical pillars or takeaways (under 12 words each) summarizing the architectural mechanism. Zero hyphens or dashes."
    )
    code_snippet: str | None = Field(
        default=None,
        description="A clean 4-8 line code snippet, config block (YAML/JSON/Python/Redis), or data flow pseudo-diagram illustrating the technical mechanism for high dwell-time visuals."
    )
    benchmark_stat: str | None = Field(
        default=None,
        description="A punchy quantitative stat if applicable, e.g. '68% Latency drop', '4.2x KV Reuse', or '<15ms Boot Time'. Zero hyphens or minus signs."
    )
    ai_visual_prompt: str = Field(
        description="A detailed prompt for generating a crisp, minimalist 2D/isometric technical system architecture diagram or data flow blueprint. BANNED: generic sci-fi server rooms, generic glowing cubes, or abstract cyborg stock art."
    )


WRITER_SYSTEM_PROMPT = """You are a knowledgeable senior software engineer writing on LinkedIn.

Your goal is to write authentic, high-signal engineering thoughts that read 100% human, maximize reach and dwell time, and completely defeat AI detectors (ZeroGPT, CopyLeaks, GPTZero).

CRITICAL TONE & VOCABULARY POLICY:
1. MANDATORY TECHNICAL ACCURACY:
   - Always use real technical terms, architecture concepts, frameworks, and metrics (e.g., latency, KV cache, RAG retrieval, token usage, PostgreSQL, Docker, APIs, GPU memory, concurrency, query plans).
   - Engineers and tech practitioners want real technical substance, not dumbed-down generic fluff.
2. USE NORMAL ENGLISH & BAN HARD VOCABULARY:
   - Explain technical concepts in clear, simple, normal everyday English. Write like a friendly, thoughtful developer chatting over coffee.
   - BANNED HARD / PRETENTIOUS VOCABULARY: NEVER use fancy, academic, or obscure words such as:
     ephemeral, paradigm, esoteric, concomitant, heterogeneous, ubiquitous, tapestry, dichotomy, behemoth, delve, harness.
   - Keep sentence structures clean, direct, and easy to read. Avoid convoluted, multi-clause run-ons.
3. STRICT ZERO-HYPHEN RULE:
   - You MUST NOT use ANY hyphens or dashes anywhere in your output! Zero hyphens are allowed.
   - NEVER use '-' (hyphen), '—' (em-dash), or '–' (en-dash).
   - Write compound words without hyphens (e.g. write 'real world', 'high signal', 'open source', 'end to end', 'token aware', 'state of the art', 'up to date').
   - For lists, use unicode dots (•), numbers (1., 2.), or clean paragraph line breaks. Never start a bullet with '-'.
   - For pauses, use commas or separate sentences instead of dashes.
   - In benchmark stats, write '68% faster' or 'down 40%', never '-68%'.
4. HUMOR & DEVELOPER WIT (WHEN HUMOR IS REQUESTED):
   - Deliver laugh-out-loud relatable engineering comedy using everyday developer realities (Friday deploys, runaway token bills, invisible YAML indentation bugs, unindexed database queries) using simple, punchy words.
   - Do NOT use hard or pretentious vocabulary even in humor mode.

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
   - "Have you hit context window memory bottlenecks with long running agent loops yet, or are you still relying on basic truncation?"
   - "Would you trust an isolated sandbox in production, or are container namespaces enough for your threat model?"

VISUAL OPTIMIZATION & DWELL TIME:
1. Generic 3D AI server art blends into feeds. Technical posts perform dramatically better when paired with a clean code snippet, terminal output, benchmark stat, or architecture flow diagram.
2. Provide a realistic 4-8 line code/config snippet in code_snippet (e.g., Python config, Redis cache decorator, or YAML pipeline).
3. If an ai_visual_prompt is generated, mandate a clean, high-contrast 2D/isometric system architecture diagram or data flow blueprint with labeled boxes. NEVER prompt for generic sci-fi servers, glowing cyber brains, or abstract AI faces.

TAILORED CONTENT ARCHETYPES (BY CATEGORY):
1. For 'developer_mistake' (Mistakes Developers Make / Pitfalls / Postmortems):
   - Hook: Call out the specific pitfall or silent bug directly ("Most teams make this mistake when configuring RAG retrieval:", "Here's the silent failure mode in autonomous agent loops:").
   - Body: Break down what developers assume vs what actually breaks under the hood in simple English. Detail the exact failure mechanism (memory leak, socket exhaustion, hallucination loop, race condition).
   - Takeaway: The production-tested fix and the rule of thumb to prevent it.
   - card_pillars: Exactly 3 pillars structured as ['1. Anti Pattern: ...', '2. Failure Mode: ...', '3. Production Fix: ...']. Zero hyphens.

2. For 'ai_learning' (AI Concepts, Architectures, Tutorials):
   - Hook: Introduce the actionable AI concept, agent protocol (MCP), or local inference technique developers should learn today.
   - Body: Explain the architectural mechanism under the hood with concrete technical terms (token latency, KV cache reuse, sandbox isolation) using normal, accessible English.
   - Takeaway: Actionable developer guidance to implement it in real projects.
   - card_pillars: Exactly 3 core architectural principles or implementation steps. Zero hyphens.

3. For 'latest_news' (Model Releases & Breakthroughs):
   - Hook: High-signal technical announcement without marketing hype.
   - Body: Architectural differentiator, benchmark numbers, and practical impact on engineering roadmaps.
   - Takeaway: What this changes for production systems.
   - card_pillars: Exactly 3 key technical capabilities or benchmark breakthroughs. Zero hyphens.

CRITICAL ANTI-DETECTION HEURISTICS:
1. Natural Cadence & Sentence Variety:
   - Mix punchy short sentences with clear explanations.
   - Never write three sentences of uniform length in a row.
   - Use natural contractions (we've, doesn't, isn't) and occasional sentence fragments.
2. ZERO High-School Textbook Definitions:
   - NEVER explain what basic tools are ("Docker is a container tool"). Senior engineers already know.
   - Jump straight into the architectural decision, the benchmark latency, or the edge case failure mode.
3. BANNED AI Transition Tropes (Instant 100% AI flags):
   - NEVER use: "The benefits are pretty straightforward:"
   - NEVER use: "Of course, there are some trade-offs."
   - NEVER use: "Curious to hear how others are balancing..."
   - NEVER use: "In today's fast-paced world..."
   - NEVER use: "When it comes to..."
   - NEVER use: "Harness the power", "Game changer", "Dive deep", "Delve", "Tapestry", "Beacon of innovation".
   - NEVER use cheesy marketer slang ("Boom!", "Like a pro", "Instant fortress").
4. Authentic Engineering Substance:
   - Speak with first-person technical conviction ("When we benchmarked this...", "A hard lesson we learned...", "If you give an LLM shell access...").
   - Mention real technical terms: latency, database queries, memory leaks, CVEs, APIs, models, caching."""


def write(story: RankedItem, humor: bool = False) -> dict:
    """Generates a complete post draft from a chosen ranked story, with optional humor injection."""
    category = story.get("category", "ai_learning")
    humor_instruction = ""
    if humor:
        humor_instruction = (
            "\n🎭 HUMOR DIRECTIVE: Inject sharp, witty, laugh-out-loud developer satire into this post! "
            "Make it relatable, cynical about engineering pain points, and hilarious while maintaining deep technical accuracy. "
            "Use simple, normal everyday English and zero hyphens; do NOT use hard, pretentious vocabulary.\n"
        )

    user_prompt = (
        f"Chosen Story:\n"
        f"Category: {category}\n"
        f"Title: {story.get('title', '')}\n"
        f"Source: {story.get('source', '')}\n"
        f"URL: {story.get('url', '')}\n"
        f"Summary: {story.get('summary', '')}\n"
        f"Selection Reason: {story.get('reason', '')}\n"
        f"{humor_instruction}\n"
        f"Draft a compelling, technically accurate LinkedIn post in clear, normal English with ZERO hyphens based on this {category.replace('_', ' ')} story. "
        f"Remember: Keep technical terms accurate, but ban hard vocabulary. NEVER include the outbound URL in the body text; set first_comment with the URL and end the post with a debate-sparking CTA and comment pointer."
    )

    try:
        draft = llm_client.complete(
            system=WRITER_SYSTEM_PROMPT,
            user=user_prompt,
            schema=LinkedInDraft,
            temperature=0.75 if humor else 0.6,
        )

        # Deterministically sanitize hyphens from all generated draft fields
        clean_hook = strip_all_hyphens(draft.hook)
        clean_body = strip_all_hyphens(draft.body)
        clean_takeaway = strip_all_hyphens(draft.takeaway)
        clean_cta = strip_all_hyphens(draft.call_to_action)
        pointer = strip_all_hyphens(draft.comment_pointer.strip() if getattr(draft, "comment_pointer", None) else "👇 Check the source paper in the comments!")
        clean_tags = [strip_all_hyphens(t).replace(" ", "") for t in draft.hashtags]
        clean_card_title = strip_all_hyphens(draft.card_title)
        clean_card_pillars = [strip_all_hyphens(p) for p in draft.card_pillars]
        clean_benchmark_stat = strip_all_hyphens(draft.benchmark_stat) if draft.benchmark_stat else None

        # Assemble full text WITHOUT external links
        tag_line = " ".join(t if t.startswith("#") else f"#{t}" for t in clean_tags)

        assembled_post = (
            f"{clean_hook}\n\n"
            f"{clean_body}\n\n"
            f"💡 Key Takeaway: {clean_takeaway}\n\n"
            f"{clean_cta}\n\n"
            f"{pointer}\n\n"
            f"{tag_line}"
        )

        # Double check: strip any accidental URLs from body
        from integrations.linkedin import strip_urls_from_text
        clean_post, body_extracted_urls = strip_urls_from_text(assembled_post)
        clean_post = strip_all_hyphens(clean_post)

        source_url = story.get("url", "")
        all_urls = [u for u in [source_url] + body_extracted_urls if u]
        primary_url = all_urls[0] if all_urls else ""

        first_comment = (draft.first_comment or "").strip()
        if not first_comment and primary_url:
            first_comment = f"Here is the link to the paper & discussion 👇\n{primary_url}"
        elif primary_url and primary_url not in first_comment:
            first_comment = f"{first_comment}\n{primary_url}"
        first_comment = strip_all_hyphens(first_comment)

        return {
            "text": clean_post,
            "tags": clean_tags,
            "card_title": clean_card_title,
            "card_pillars": clean_card_pillars,
            "code_snippet": draft.code_snippet,
            "benchmark_stat": clean_benchmark_stat,
            "first_comment": first_comment,
            "ai_visual_prompt": draft.ai_visual_prompt,
            "takeaway": clean_takeaway,
            "raw_draft": draft.model_dump(),
        }

    except Exception as e:
        logger.error("LLM writing failed, falling back to template draft: %s", e)
        fallback_tags = ["#AI", "#TechNews", "#SoftwareEngineering"]
        fallback_title = strip_all_hyphens(story.get('title', 'Latest AI Breakthrough'))
        fallback_summary = strip_all_hyphens(story.get('summary', ''))
        fallback_reason = strip_all_hyphens(story.get('reason', 'Significant milestone in engineering architecture.'))
        fallback_text = (
            f"🚀 {fallback_title}\n\n"
            f"{fallback_summary}\n\n"
            f"💡 Why it matters: {fallback_reason}\n\n"
            f"How is your team currently approaching this pattern in production? Let's discuss in the comments.\n\n"
            f"👇 Check the source paper in the comments!\n\n"
            f"{' '.join(fallback_tags)}"
        )
        source_url = story.get("url", "")
        fallback_comment = f"Here is the link to the source paper & code 👇\n{source_url}" if source_url else ""

        return {
            "text": strip_all_hyphens(fallback_text),
            "tags": fallback_tags,
            "card_title": fallback_title,
            "card_pillars": [
                "1. System Boundary: Isolated tool execution",
                "2. Production Safety: Isolated runtime sandbox",
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
            "benchmark_stat": "68% Latency drop | 4.2x Reuse",
            "first_comment": strip_all_hyphens(fallback_comment),
            "ai_visual_prompt": f"Minimalist 2D technical system architecture diagram of {fallback_title} in deep indigo and cyan on dark slate, component data flow boxes, 16:9 aspect ratio",
            "takeaway": fallback_reason,
            "raw_draft": {},
        }
