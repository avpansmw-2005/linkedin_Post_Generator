"""Image generator creating technical architecture cards (Pillow) and AI visuals (OpenAI gpt-image-2.5-flare)."""

from __future__ import annotations

import os
import re
import base64
import hashlib
import textwrap
import logging
from PIL import Image, ImageDraw, ImageFont
import httpx
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

OUTPUT_DIR = "data/images"
CARD_WIDTH = 1200
CARD_HEIGHT = 630

# Modern Dark Slate & Neon Accent Palette
COLOR_BG_DARK = (15, 23, 42)          # Slate 900
COLOR_BG_GRADIENT = (24, 20, 60)      # Deep Indigo / Violet 950
COLOR_ACCENT_PRIMARY = (99, 102, 241) # Indigo 500
COLOR_ACCENT_CYAN = (6, 182, 212)     # Cyan 500
COLOR_ACCENT_EMERALD = (16, 185, 129) # Emerald 500
COLOR_TEXT_WHITE = (255, 255, 255)
COLOR_TEXT_MUTED = (148, 163, 184)    # Slate 400
COLOR_TEXT_DIM = (100, 116, 139)      # Slate 500
COLOR_CARD_BG = (24, 33, 54)          # Slate 850
COLOR_CARD_BORDER = (45, 60, 85)      # Slate 750
COLOR_BADGE_BG = (30, 41, 59)         # Slate 800
COLOR_BADGE_BORDER = (51, 65, 85)     # Slate 700


def _get_system_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Loads modern system typography or falls back to default."""
    candidate_fonts = [
        "C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/calibrib.ttf" if bold else "C:/Windows/Fonts/calibri.ttf",
    ]
    for path in candidate_fonts:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size=size)
            except Exception:
                continue
    return ImageFont.load_default()


def _draw_gradient_background(draw: ImageDraw.ImageDraw, width: int, height: int) -> None:
    """Renders a smooth vertical/diagonal dark gradient."""
    for y in range(height):
        ratio = y / height
        r = int(COLOR_BG_DARK[0] * (1 - ratio) + COLOR_BG_GRADIENT[0] * ratio)
        g = int(COLOR_BG_DARK[1] * (1 - ratio) + COLOR_BG_GRADIENT[1] * ratio)
        b = int(COLOR_BG_DARK[2] * (1 - ratio) + COLOR_BG_GRADIENT[2] * ratio)
        draw.line([(0, y), (width, y)], fill=(r, g, b))


def _draw_accent_header(draw: ImageDraw.ImageDraw, width: int) -> None:
    """Draws a glowing gradient accent bar across the top."""
    bar_height = 8
    for x in range(width):
        ratio = x / width
        r = int(COLOR_ACCENT_PRIMARY[0] * (1 - ratio) + COLOR_ACCENT_CYAN[0] * ratio)
        g = int(COLOR_ACCENT_PRIMARY[1] * (1 - ratio) + COLOR_ACCENT_CYAN[1] * ratio)
        b = int(COLOR_ACCENT_PRIMARY[2] * (1 - ratio) + COLOR_ACCENT_CYAN[2] * ratio)
        draw.line([(x, 0), (x, bar_height)], fill=(r, g, b))


def render_architecture_card(
    card_title: str,
    card_pillars: list[str],
    takeaway: str,
    source: str = "Engineering Feed",
    tag: str = "ARCHITECTURE",
    branding: str = "AI SYSTEMS ARCHITECTURE",
    output_path: str | None = None,
) -> str:
    """Renders a substantive 1200x630 technical architecture card displaying:
    - Concept Hook / Title
    - 3 Structured Architectural Pillars / Key Takeaways
    - Core Engineering Finding Banner
    - Branded Footer
    """
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    if not output_path:
        filename = f"card_arch_{hashlib.md5((card_title + source).encode()).hexdigest()[:10]}.png"
        output_path = os.path.join(OUTPUT_DIR, filename)

    img = Image.new("RGB", (CARD_WIDTH, CARD_HEIGHT), color=COLOR_BG_DARK)
    draw = ImageDraw.Draw(img)

    # 1. Background & Glowing Accent Top Bar
    _draw_gradient_background(draw, CARD_WIDTH, CARD_HEIGHT)
    _draw_accent_header(draw, CARD_WIDTH)

    margin_x = 70
    top_y = 35

    # 2. Pill Badges (Tag, Source, and Architecture Label)
    badge_font = _get_system_font(18, bold=True)
    tag_text = tag.upper().replace("#", "")
    tag_bbox = draw.textbbox((0, 0), tag_text, font=badge_font)
    tag_w = (tag_bbox[2] - tag_bbox[0]) + 24
    tag_h = 32

    # Tag Badge (Indigo)
    draw.rounded_rectangle(
        [(margin_x, top_y), (margin_x + tag_w, top_y + tag_h)],
        radius=16,
        fill=COLOR_ACCENT_PRIMARY,
    )
    draw.text((margin_x + 12, top_y + 6), tag_text, font=badge_font, fill=COLOR_TEXT_WHITE)

    # Source Badge (Slate)
    source_x = margin_x + tag_w + 12
    source_bbox = draw.textbbox((0, 0), source, font=badge_font)
    source_w = (source_bbox[2] - source_bbox[0]) + 24
    draw.rounded_rectangle(
        [(source_x, top_y), (source_x + source_w, top_y + tag_h)],
        radius=16,
        fill=COLOR_BADGE_BG,
        outline=COLOR_BADGE_BORDER,
        width=1,
    )
    draw.text((source_x + 12, top_y + 6), source, font=badge_font, fill=COLOR_TEXT_MUTED)

    # Architecture Spec Label (Cyan accent outline)
    spec_label = "SYSTEM DESIGN PATTERN"
    spec_x = source_x + source_w + 12
    spec_bbox = draw.textbbox((0, 0), spec_label, font=badge_font)
    spec_w = (spec_bbox[2] - spec_bbox[0]) + 24
    draw.rounded_rectangle(
        [(spec_x, top_y), (spec_x + spec_w, top_y + tag_h)],
        radius=16,
        fill=(15, 30, 50),
        outline=COLOR_ACCENT_CYAN,
        width=1,
    )
    draw.text((spec_x + 12, top_y + 6), spec_label, font=badge_font, fill=COLOR_ACCENT_CYAN)

    # 3. Main Concept Title
    title_y = top_y + tag_h + 20
    title_font = _get_system_font(34, bold=True)
    # Wrap title cleanly
    title_lines = textwrap.wrap(card_title, width=52)[:2]
    curr_y = title_y
    for line in title_lines:
        draw.text((margin_x, curr_y), line, font=title_font, fill=COLOR_TEXT_WHITE)
        curr_y += 42

    # 4. Three Structured Architectural Pillar Cards
    pillars_start_y = max(curr_y + 15, 175)
    box_width = CARD_WIDTH - (margin_x * 2)
    box_height = 64
    box_gap = 12

    pillar_font = _get_system_font(21, bold=False)
    pillar_chip_font = _get_system_font(17, bold=True)

    # Ensure exactly 3 pillars
    clean_pillars = (card_pillars + [
        "1. Boundary Isolation: Hard-enforced sandbox limits",
        "2. Deterministic State: Zero-loss checkpoint recovery",
        "3. Production Observability: Structured tracing metrics",
    ])[:3]

    for idx, pillar in enumerate(clean_pillars):
        p_y = pillars_start_y + (idx * (box_height + box_gap))

        # Card container box
        draw.rounded_rectangle(
            [(margin_x, p_y), (margin_x + box_width, p_y + box_height)],
            radius=12,
            fill=COLOR_CARD_BG,
            outline=COLOR_CARD_BORDER,
            width=1,
        )

        # Left accent glowing strip
        draw.rounded_rectangle(
            [(margin_x, p_y), (margin_x + 6, p_y + box_height)],
            radius=3,
            fill=COLOR_ACCENT_PRIMARY if idx == 0 else (COLOR_ACCENT_CYAN if idx == 1 else COLOR_ACCENT_EMERALD),
        )

        # Number chip [ 01 ], [ 02 ], [ 03 ]
        num_str = f"0{idx+1}"
        chip_x = margin_x + 20
        chip_y = p_y + 16
        draw.rounded_rectangle(
            [(chip_x, chip_y), (chip_x + 42, chip_y + 32)],
            radius=8,
            fill=(30, 41, 59),
            outline=COLOR_CARD_BORDER,
            width=1,
        )
        draw.text((chip_x + 10, chip_y + 6), num_str, font=pillar_chip_font, fill=COLOR_ACCENT_CYAN)

        # Strip any existing leading "1. " or "2. " from pillar text for clean alignment
        clean_text = re.sub(r'^\d+[\.\)]\s*', '', pillar).strip()
        # Truncate if excessively long
        if len(clean_text) > 85:
            clean_text = clean_text[:82] + "..."

        text_x = chip_x + 58
        text_y = p_y + 20
        draw.text((text_x, text_y), clean_text, font=pillar_font, fill=COLOR_TEXT_WHITE)

    # 5. Core Engineering Takeaway Banner
    takeaway_y = pillars_start_y + (3 * (box_height + box_gap)) + 18
    takeaway_h = 68

    draw.rounded_rectangle(
        [(margin_x, takeaway_y), (margin_x + box_width, takeaway_y + takeaway_h)],
        radius=12,
        fill=(20, 28, 48),
        outline=COLOR_ACCENT_CYAN,
        width=1,
    )

    # Glowing Cyan indicator icon & label
    takeaway_label_font = _get_system_font(17, bold=True)
    draw.text((margin_x + 20, takeaway_y + 24), "CORE TAKEAWAY:", font=takeaway_label_font, fill=COLOR_ACCENT_CYAN)

    takeaway_content_font = _get_system_font(19, bold=False)
    clean_takeaway = takeaway.strip()
    if len(clean_takeaway) > 78:
        clean_takeaway = clean_takeaway[:75] + "..."
    draw.text((margin_x + 180, takeaway_y + 23), clean_takeaway, font=takeaway_content_font, fill=COLOR_TEXT_WHITE)

    # 6. Footer Branding
    footer_y = CARD_HEIGHT - 45
    draw.line(
        [(margin_x, footer_y - 12), (CARD_WIDTH - margin_x, footer_y - 12)],
        fill=COLOR_CARD_BORDER,
        width=1,
    )

    brand_font = _get_system_font(19, bold=True)
    draw.text((margin_x, footer_y), branding, font=brand_font, fill=COLOR_TEXT_MUTED)

    # Glowing cyan dot
    brand_bbox = draw.textbbox((margin_x, footer_y), branding, font=brand_font)
    dot_x = brand_bbox[2] + 14
    draw.ellipse([(dot_x, footer_y + 4), (dot_x + 10, footer_y + 14)], fill=COLOR_ACCENT_CYAN)

    img.save(output_path, "PNG", quality=95)
    logger.info("Generated high-signal Architecture Card at %s", output_path)
    return output_path


def generate_ai_visual(
    prompt: str,
    output_path: str | None = None,
) -> str:
    """Generates a cutting-edge 16:9 technical concept visual using OpenAI's latest gpt-image-2.5-flare model.
    Falls back gracefully if the API is unavailable.
    """
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    if not output_path:
        filename = f"ai_visual_{hashlib.md5(prompt.encode()).hexdigest()[:10]}.png"
        output_path = os.path.join(OUTPUT_DIR, filename)

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY not configured in environment.")

    from openai import OpenAI
    client = OpenAI(api_key=api_key)

    # Candidate models in order of capability (latest gpt-image series)
    candidate_models = [
        "gpt-image-2.5-flare",
        "gpt-image-2.5-sunburst",
        "gpt-image-2",
        "gpt-image-1.5",
    ]

    last_err: Exception | None = None
    for model in candidate_models:
        try:
            logger.info("Calling OpenAI image generation with model: %s...", model)
            res = client.images.generate(
                model=model,
                prompt=prompt,
                size="1536x1024",
            )
            # Check for base64 payload
            if res.data and res.data[0].b64_json:
                raw_bytes = base64.b64decode(res.data[0].b64_json)
                with open(output_path, "wb") as f:
                    f.write(raw_bytes)
                logger.info("Successfully generated and saved AI visual using %s to %s", model, output_path)
                return output_path

            # Check for URL payload
            if res.data and res.data[0].url:
                resp = httpx.get(res.data[0].url, timeout=20.0)
                if resp.status_code == 200:
                    with open(output_path, "wb") as f:
                        f.write(resp.content)
                    logger.info("Successfully downloaded and saved AI visual from URL to %s", output_path)
                    return output_path

        except Exception as e:
            logger.warning("Failed generation with model %s: %s", model, e)
            last_err = e

    raise RuntimeError(f"All image models failed. Last error: {last_err}")


def render(story: dict, draft: dict, mode: str = "card") -> str:
    """Unified entrypoint for generating images.
    Supports:
    - 'card': High-signal Technical Architecture Infographic Card (Local Pillow)
    - 'ai_visual': High-tech 16:9 AI Visual Concept using OpenAI gpt-image-2.5-flare
    """
    card_title = draft.get("card_title") or story.get("title") or "AI Systems Architecture"
    card_pillars = draft.get("card_pillars") or [
        "1. Boundary Isolation: Enforce least-privilege tool access",
        "2. Deterministic State: StateGraph persistence & audit gates",
        "3. Egress Control: Hard quotas to mitigate data exfiltration",
    ]
    takeaway = draft.get("takeaway") or story.get("reason") or "Production engineering breakthrough."
    source = story.get("source") or "Hacker News"
    tags = draft.get("tags") or ["AI"]
    primary_tag = tags[0].replace("#", "") if tags else "AI"

    if mode == "ai_visual":
        prompt = draft.get("ai_visual_prompt")
        if not prompt:
            prompt = (
                f"Minimalist 3D isometric technical blueprint of {card_title}, "
                f"glowing cyan and indigo data streams, dark slate server architecture, 16:9 aspect ratio, 8k render"
            )
        try:
            return generate_ai_visual(prompt)
        except Exception as e:
            logger.error("AI visual generation failed; falling back to Architecture Card: %s", e)
            # Fallback to rich architecture card
            return render_architecture_card(
                card_title=card_title,
                card_pillars=card_pillars,
                takeaway=takeaway,
                source=source,
                tag=primary_tag,
            )

    # Default to Architecture Card
    return render_architecture_card(
        card_title=card_title,
        card_pillars=card_pillars,
        takeaway=takeaway,
        source=source,
        tag=primary_tag,
    )


def render_card(
    headline: str,
    source: str = "AI News",
    tag: str = "BREAKTHROUGH",
    branding: str = "AI SYSTEMS ARCHITECTURE",
    output_path: str | None = None,
) -> str:
    """Backward-compatible helper mapping headline to architecture card."""
    return render_architecture_card(
        card_title=headline,
        card_pillars=[
            "1. Architecture Pattern: Scalable system design",
            "2. Production Boundary: Hard isolation guarantees",
            "3. Engineering Impact: High performance reliability",
        ],
        takeaway="Key engineering milestone.",
        source=source,
        tag=tag,
        branding=branding,
        output_path=output_path,
    )
