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


LINKEDIN_API_VERSION = "202401"
LINKEDIN_REST_BASE = "https://api.linkedin.com/rest"


def _get_linkedin_person_urn(access_token: str) -> str:
    """Discovers person URN via /v2/userinfo or /v2/me, or reads from LINKEDIN_PERSON_URN."""
    explicit_urn = os.getenv("LINKEDIN_PERSON_URN", "").strip()
    if explicit_urn:
        if not explicit_urn.startswith("urn:li:person:"):
            return f"urn:li:person:{explicit_urn}"
        return explicit_urn

    headers = {"Authorization": f"Bearer {access_token}"}
    import httpx

    with httpx.Client(timeout=10.0) as client:
        # 1. Try OpenID Connect /v2/userinfo (Modern standard)
        try:
            resp = client.get("https://api.linkedin.com/v2/userinfo", headers=headers)
            if resp.status_code == 200:
                sub = resp.json().get("sub")
                if sub:
                    logger.info("Discovered LinkedIn person URN from /v2/userinfo: urn:li:person:%s", sub)
                    return f"urn:li:person:{sub}"
        except Exception as e:
            logger.debug("OIDC /v2/userinfo attempt failed: %s", e)

        # 2. Try legacy /v2/me
        try:
            resp_me = client.get("https://api.linkedin.com/v2/me", headers=headers)
            if resp_me.status_code == 200:
                user_id = resp_me.json().get("id")
                if user_id:
                    logger.info("Discovered LinkedIn person URN from /v2/me: urn:li:person:%s", user_id)
                    return f"urn:li:person:{user_id}"
        except Exception as e:
            logger.debug("/v2/me attempt failed: %s", e)

    raise RuntimeError(
        "Could not automatically discover LinkedIn Person URN. "
        "Please add LINKEDIN_PERSON_URN=urn:li:person:YOUR_ID to your .env file."
    )


def _upload_linkedin_image_rest(image_path: str, access_token: str, person_urn: str) -> str:
    """Uploads an image using the official LinkedIn REST API (202401):
    1. POST /rest/images?action=initializeUpload
    2. PUT <uploadUrl> with binary PNG/JPEG content
    Returns: The image URN (e.g., 'urn:li:image:D4E10AQH...').
    """
    import httpx

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "X-Restli-Protocol-Version": "2.0.0",
        "LinkedIn-Version": LINKEDIN_API_VERSION,
    }

    init_payload = {
        "initializeUploadRequest": {
            "owner": person_urn
        }
    }

    with httpx.Client(timeout=30.0) as client:
        logger.info("Initializing image upload via LinkedIn REST API...")
        resp = client.post(
            f"{LINKEDIN_REST_BASE}/images?action=initializeUpload",
            headers=headers,
            json=init_payload,
        )
        if resp.status_code not in (200, 201):
            raise RuntimeError(f"LinkedIn image initializeUpload failed ({resp.status_code}): {resp.text}")

        data = resp.json().get("value", {})
        image_urn = data.get("image")
        upload_url = data.get("uploadUrl")
        if not (image_urn and upload_url):
            raise RuntimeError(f"Missing image URN or upload URL in LinkedIn response: {resp.text}")

        # Step 2: Binary PUT
        with open(image_path, "rb") as f:
            image_bytes = f.read()

        put_headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "image/png",
        }
        logger.info("Uploading binary image bytes to LinkedIn upload URL...")
        put_resp = client.put(upload_url, headers=put_headers, content=image_bytes)
        if put_resp.status_code not in (200, 201, 204):
            raise RuntimeError(f"LinkedIn binary image upload failed ({put_resp.status_code}): {put_resp.text}")

        logger.info("Successfully uploaded image to LinkedIn: %s", image_urn)
        return image_urn


def _post_official_rest(text: str, image_path: str | None = None) -> str:
    """Publishes a post directly using the official LinkedIn 202401 /rest/posts API."""
    access_token = os.getenv("LINKEDIN_ACCESS_TOKEN", "").strip()
    if not access_token:
        raise RuntimeError("LINKEDIN_ACCESS_TOKEN is not configured in .env.")

    person_urn = _get_linkedin_person_urn(access_token)
    import httpx

    image_urn = None
    if image_path and os.path.exists(image_path):
        image_urn = _upload_linkedin_image_rest(image_path, access_token, person_urn)

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "X-Restli-Protocol-Version": "2.0.0",
        "LinkedIn-Version": LINKEDIN_API_VERSION,
    }

    payload: dict = {
        "author": person_urn,
        "commentary": text,
        "visibility": "PUBLIC",
        "distribution": {
            "feedDistribution": "MAIN_FEED",
            "targetEntities": [],
            "thirdPartyDistributionChannels": []
        },
        "lifecycleState": "PUBLISHED",
        "isReshareDisabledByAuthor": False,
    }

    if image_urn:
        payload["content"] = {
            "media": {
                "id": image_urn,
                "title": "Technical Architecture Breakdown",
            }
        }

    logger.info("Submitting post to official LinkedIn /rest/posts endpoint...")
    with httpx.Client(timeout=20.0) as client:
        resp = client.post(f"{LINKEDIN_REST_BASE}/posts", headers=headers, json=payload)
        if resp.status_code not in (200, 201):
            raise RuntimeError(f"LinkedIn /rest/posts failed ({resp.status_code}): {resp.text}")

        post_urn = resp.headers.get("x-restli-id") or ""
        logger.info("Successfully created LinkedIn post via official REST API: %s", post_urn)
        if post_urn:
            return f"https://www.linkedin.com/feed/update/{post_urn}"
        return "https://www.linkedin.com/in/me/recent-activity/all/"


def post(text: str, image_path: str | None = None) -> str:
    """Publishes a post to LinkedIn.

    Signature: post(text: str, image_path: str | None) -> post_url: str
    If DRY_RUN=true, logs the action and returns a mock LinkedIn URL.
    Prefers official LinkedIn REST API (/rest/posts) if LINKEDIN_ACCESS_TOKEN is configured.
    Otherwise falls back to Ayrshare.
    """
    clean_text = format_linkedin_text(text)

    if is_dry_run():
        logger.info("[DRY-RUN] Simulating LinkedIn post publication.")
        logger.info("[DRY-RUN] Post content preview (first 150 chars):\n%s...", clean_text[:150])
        if image_path:
            logger.info("[DRY-RUN] Post attached image: %s", image_path)
        fake_id = "dryrun_" + str(abs(hash(clean_text)))[:10]
        return f"https://www.linkedin.com/feed/update/urn:li:activity:{fake_id}"

    # 1. Primary: Official LinkedIn REST API (No third-party branding, no Ayrshare watermark)
    if os.getenv("LINKEDIN_ACCESS_TOKEN"):
        logger.info("Using official LinkedIn REST API (/rest/posts) with w_member_social...")
        return _post_official_rest(clean_text, image_path)

    # 2. Fallback: Ayrshare Gateway
    ayrshare_key = os.getenv("AYRSHARE_API_KEY")
    if not ayrshare_key:
        raise RuntimeError("Neither LINKEDIN_ACCESS_TOKEN nor AYRSHARE_API_KEY is set in environment or .env file.")

    logger.info("LINKEDIN_ACCESS_TOKEN not found; falling back to Ayrshare...")
    from ayrshare import SocialPost
    social = SocialPost(ayrshare_key)

    media_urls: list[str] = []
    if image_path and os.path.exists(image_path):
        # Try Cloudinary if configured
        public_url = _upload_to_cloudinary(image_path)
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
