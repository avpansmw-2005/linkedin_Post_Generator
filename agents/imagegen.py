"""Image generator creating high-aesthetic 1200x630 branded social media cards using Pillow."""

from __future__ import annotations

import os
import hashlib
import textwrap
import logging
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

OUTPUT_DIR = "data/images"
CARD_WIDTH = 1200
CARD_HEIGHT = 630

# Aesthetic Dark Palette
COLOR_BG_DARK = (15, 23, 42)          # Slate 900
COLOR_BG_GRADIENT = (30, 27, 75)      # Deep Indigo 950
COLOR_ACCENT_PRIMARY = (99, 102, 241) # Indigo 500
COLOR_ACCENT_CYAN = (6, 182, 212)     # Cyan 500
COLOR_TEXT_WHITE = (255, 255, 255)
COLOR_TEXT_MUTED = (148, 163, 184)    # Slate 400
COLOR_BADGE_BG = (30, 41, 59)         # Slate 800
COLOR_BADGE_BORDER = (51, 65, 85)     # Slate 700


def _get_system_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Attempts to load a modern Windows system font, falling back to default."""
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
    """Draws a modern glowing gradient accent bar across the top."""
    bar_height = 8
    for x in range(width):
        ratio = x / width
        r = int(COLOR_ACCENT_PRIMARY[0] * (1 - ratio) + COLOR_ACCENT_CYAN[0] * ratio)
        g = int(COLOR_ACCENT_PRIMARY[1] * (1 - ratio) + COLOR_ACCENT_CYAN[1] * ratio)
        b = int(COLOR_ACCENT_PRIMARY[2] * (1 - ratio) + COLOR_ACCENT_CYAN[2] * ratio)
        draw.line([(x, 0), (x, bar_height)], fill=(r, g, b))


def _wrap_and_fit_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    max_width: int,
    max_height: int,
    initial_font_size: int = 54,
    min_font_size: int = 32,
) -> tuple[list[str], ImageFont.FreeTypeFont | ImageFont.ImageFont, int]:
    """Dynamically wraps text and reduces font size to guarantee it fits inside the bounding box."""
    font_size = initial_font_size
    while font_size >= min_font_size:
        font = _get_system_font(font_size, bold=True)
        # Estimate characters per line based on average character width
        char_width_est = font_size * 0.55
        wrap_width = max(15, int(max_width / char_width_est))

        lines = textwrap.wrap(text, width=wrap_width)
        line_height = int(font_size * 1.3)
        total_height = len(lines) * line_height

        # Verify actual pixel bounds
        fits = True
        if total_height > max_height:
            fits = False
        else:
            for line in lines:
                bbox = draw.textbbox((0, 0), line, font=font)
                if (bbox[2] - bbox[0]) > max_width:
                    fits = False
                    break

        if fits or font_size == min_font_size:
            return lines, font, line_height

        font_size -= 4

    return lines, _get_system_font(min_font_size, bold=True), int(min_font_size * 1.3)


def render_card(
    headline: str,
    source: str = "AI News",
    tag: str = "BREAKTHROUGH",
    branding: str = "AI ENGINEERING PULSE",
    output_path: str | None = None,
) -> str:
    """Renders a polished 1200x630 social card and saves to disk.
    Guarantees text never clips or overflows.
    """
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    if not output_path:
        filename = f"card_{hashlib.md5(headline.encode()).hexdigest()[:10]}.png"
        output_path = os.path.join(OUTPUT_DIR, filename)

    img = Image.new("RGB", (CARD_WIDTH, CARD_HEIGHT), color=COLOR_BG_DARK)
    draw = ImageDraw.Draw(img)

    # 1. Background gradient & top glowing bar
    _draw_gradient_background(draw, CARD_WIDTH, CARD_HEIGHT)
    _draw_accent_header(draw, CARD_WIDTH)

    margin_x = 80
    top_y = 60

    # 2. Pill Badges (Category Tag & Source)
    badge_font = _get_system_font(20, bold=True)
    badge_y = top_y

    # Tag Badge (Indigo accent)
    tag_text = tag.upper()
    tag_bbox = draw.textbbox((0, 0), tag_text, font=badge_font)
    tag_w = (tag_bbox[2] - tag_bbox[0]) + 28
    tag_h = 36
    draw.rounded_rectangle(
        [(margin_x, badge_y), (margin_x + tag_w, badge_y + tag_h)],
        radius=18,
        fill=COLOR_ACCENT_PRIMARY,
    )
    draw.text(
        (margin_x + 14, badge_y + 8),
        tag_text,
        font=badge_font,
        fill=COLOR_TEXT_WHITE,
    )

    # Source Badge (Slate rounded chip)
    source_x = margin_x + tag_w + 16
    source_text = source
    source_bbox = draw.textbbox((0, 0), source_text, font=badge_font)
    source_w = (source_bbox[2] - source_bbox[0]) + 28
    draw.rounded_rectangle(
        [(source_x, badge_y), (source_x + source_w, badge_y + tag_h)],
        radius=18,
        fill=COLOR_BADGE_BG,
        outline=COLOR_BADGE_BORDER,
        width=2,
    )
    draw.text(
        (source_x + 14, badge_y + 8),
        source_text,
        font=badge_font,
        fill=COLOR_TEXT_MUTED,
    )

    # 3. Dynamic Headline
    content_y = badge_y + tag_h + 40
    max_content_w = CARD_WIDTH - (margin_x * 2)
    max_content_h = 340

    lines, title_font, line_height = _wrap_and_fit_text(
        draw, headline, max_width=max_content_w, max_height=max_content_h
    )

    curr_y = content_y
    for line in lines:
        draw.text((margin_x, curr_y), line, font=title_font, fill=COLOR_TEXT_WHITE)
        curr_y += line_height

    # 4. Footer Branding & Decorative Line
    footer_y = CARD_HEIGHT - 70
    draw.line(
        [(margin_x, footer_y - 20), (CARD_WIDTH - margin_x, footer_y - 20)],
        fill=COLOR_BADGE_BORDER,
        width=1,
    )

    brand_font = _get_system_font(22, bold=True)
    draw.text((margin_x, footer_y), branding, font=brand_font, fill=COLOR_TEXT_MUTED)

    # Accent dot in footer
    brand_bbox = draw.textbbox((margin_x, footer_y), branding, font=brand_font)
    dot_x = brand_bbox[2] + 16
    draw.ellipse([(dot_x, footer_y + 6), (dot_x + 10, footer_y + 16)], fill=COLOR_ACCENT_CYAN)

    img.save(output_path, "PNG", quality=95)
    logger.info("Saved generated social card to %s", output_path)
    return output_path


def render(story: dict, draft: dict) -> str:
    """Orchestrator hook to render card from story and draft metadata."""
    title = story.get("title", "AI Research Breakthrough")
    source = story.get("source", "Curated News")
    tags = draft.get("tags", ["AI"])
    primary_tag = tags[0].replace("#", "") if tags else "AI"

    return render_card(
        headline=title,
        source=source,
        tag=primary_tag,
    )
