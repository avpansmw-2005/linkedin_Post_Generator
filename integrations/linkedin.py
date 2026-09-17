"""LinkedIn publishing integration via Ayrshare and Cloudinary, with full dry-run support."""

from __future__ import annotations

import os
import logging
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


def is_dry_run() -> bool:
    """Returns True if the pipeline is operating in dry-run mode."""
    val = os.getenv("DRY_RUN", "true").lower().strip()
    return val in ("true", "1", "yes")


def _upload_to_cloudinary(local_path: str) -> str | None:
    """Uploads an image to Cloudinary and returns the secure public URL."""
    cloud_name = os.getenv("CLOUDINARY_CLOUD_NAME")
    api_key = os.getenv("CLOUDINARY_API_KEY")
    api_secret = os.getenv("CLOUDINARY_API_SECRET")

    if not (cloud_name and api_key and api_secret):
        logger.info("Cloudinary credentials not configured.")
        return None

    try:
        import cloudinary
        import cloudinary.uploader

        cloudinary.config(
            cloud_name=cloud_name,
            api_key=api_key,
            api_secret=api_secret,
        )
        logger.info("Uploading %s to Cloudinary...", local_path)
        result = cloudinary.uploader.upload(local_path)
        url = result.get("secure_url") or result.get("url")
        logger.info("Uploaded successfully: %s", url)
        return url
    except Exception as e:
        logger.warning("Cloudinary upload failed: %s", e)
        return None


def _upload_to_ayrshare_media(local_path: str, ayrshare_key: str) -> str | None:
    """Uploads local image bytes directly to Ayrshare media endpoint."""
    try:
        import httpx
        url = "https://app.ayrshare.com/api/media/upload"
        headers = {"Authorization": f"Bearer {ayrshare_key}"}

        filename = os.path.basename(local_path)
        with open(local_path, "rb") as f:
            files = {"file": (filename, f, "image/png")}
            resp = httpx.post(url, headers=headers, files=files, timeout=30.0)

        if resp.status_code in (200, 201):
            data = resp.json()
            return data.get("url")
        else:
            logger.warning("Ayrshare direct media upload returned %d: %s", resp.status_code, resp.text)
    except Exception as e:
        logger.warning("Direct Ayrshare media upload failed: %s", e)
    return None


def to_unicode_bold(text: str) -> str:
    """Converts standard ASCII characters to Unicode Mathematical Sans-Serif Bold."""
    chars = []
    for c in text:
        if "A" <= c <= "Z":
            chars.append(chr(0x1D5D4 + ord(c) - ord("A")))
        elif "a" <= c <= "z":
            chars.append(chr(0x1D5EE + ord(c) - ord("a")))
        elif "0" <= c <= "9":
            chars.append(chr(0x1D7EC + ord(c) - ord("0")))
        else:
            chars.append(c)
    return "".join(chars)


def format_linkedin_text(text: str) -> str:
    """Formats markdown specifically for LinkedIn feeds:
    1. Converts **bold** markdown into native Unicode bold characters (e.g. 𝗜𝘀𝗼𝗹𝗮𝘁𝗶𝗼𝗻:).
    2. Converts bullet lists (- item) into clean bullet symbols (• item).
    3. Normalizes paragraph spacing so lines don't collapse together on LinkedIn.
    """
    import re

    # 1. Convert **bold** markdown to native Unicode bold
    formatted = re.sub(r"\*\*(.+?)\*\*", lambda m: to_unicode_bold(m.group(1)), text)

    # 2. Convert markdown list dashes into clean bullets
    formatted = re.sub(r"^[ \t]*[-*][ \t]+", "• ", formatted, flags=re.MULTILINE)

    # 3. Ensure double newlines between paragraphs so LinkedIn doesn't collapse them
    paragraphs = [p.strip() for p in formatted.split("\n\n") if p.strip()]
    return "\n\n".join(paragraphs)


def post(text: str, image_path: str | None = None) -> str:
    """Publishes a post to LinkedIn.

    Signature: post(text: str, image_path: str | None) -> post_url: str
    If DRY_RUN=true, logs the action and returns a mock LinkedIn URL.
    """
    clean_text = format_linkedin_text(text)

    if is_dry_run():
        logger.info("[DRY-RUN] Simulating LinkedIn post publication.")
        logger.info("[DRY-RUN] Post content preview (first 150 chars):\n%s...", clean_text[:150])
        if image_path:
            logger.info("[DRY-RUN] Post attached image: %s", image_path)
        fake_id = "dryrun_" + str(abs(hash(clean_text)))[:10]
        return f"https://www.linkedin.com/feed/update/urn:li:activity:{fake_id}"

    ayrshare_key = os.getenv("AYRSHARE_API_KEY")
    if not ayrshare_key:
        raise RuntimeError("AYRSHARE_API_KEY is not set in environment or .env file.")

    from ayrshare import SocialPost
    social = SocialPost(ayrshare_key)

    media_urls: list[str] = []
    if image_path and os.path.exists(image_path):
        # 1. Try Cloudinary if configured
        public_url = _upload_to_cloudinary(image_path)

        # 2. Fall back to Ayrshare direct media upload if Cloudinary is not set
        if not public_url:
            public_url = _upload_to_ayrshare_media(image_path, ayrshare_key)

        if public_url:
            media_urls.append(public_url)
        else:
            logger.warning("Proceeding with text-only post as image could not be uploaded.")

    post_payload: dict = {
        "post": clean_text,
        "platforms": ["linkedin"],
    }
    if media_urls:
        post_payload["mediaUrls"] = media_urls

    logger.info("Submitting post to Ayrshare for LinkedIn...")
    result = social.post(post_payload)

    if not isinstance(result, dict) or result.get("status") == "error":
        raise RuntimeError(f"LinkedIn posting via Ayrshare failed: {result}")

    post_ids = result.get("postIds", [])
    if post_ids and isinstance(post_ids, list):
        post_url = post_ids[0].get("postUrl")
        if post_url:
            return post_url

    post_id = result.get("id") or "published"
    return f"https://www.linkedin.com/feed/update/urn:li:activity:{post_id}"
