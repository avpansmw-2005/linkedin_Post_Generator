"""Official LinkedIn REST API publishing integration with full dry-run support."""

from __future__ import annotations

import os
import logging
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# Tracks whether the 1st comment was posted automatically or requires manual drop
LAST_COMMENT_STATUS: str | None = None


def is_dry_run() -> bool:
    """Returns True if the pipeline is operating in dry-run mode."""
    val = os.getenv("DRY_RUN", "true").lower().strip()
    return val in ("true", "1", "yes")


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


LINKEDIN_API_VERSION = os.getenv("LINKEDIN_API_VERSION", "202608")
LINKEDIN_REST_BASE = "https://api.linkedin.com/rest"
CANDIDATE_VERSIONS = ["202608", "202607", "202606", "202605", "202604", "202603", "202602", "202601"]


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
    """Uploads an image using the official LinkedIn REST API:
    1. POST /rest/images?action=initializeUpload
    2. PUT <uploadUrl> with binary PNG/JPEG content
    Returns: The image URN (e.g., 'urn:li:image:D4E10AQH...').
    """
    import httpx

    init_payload = {
        "initializeUploadRequest": {
            "owner": person_urn
        }
    }

    versions_to_try = [LINKEDIN_API_VERSION] + [v for v in CANDIDATE_VERSIONS if v != LINKEDIN_API_VERSION]
    last_err: Exception | None = None

    with httpx.Client(timeout=30.0) as client:
        for ver in versions_to_try:
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
                "X-Restli-Protocol-Version": "2.0.0",
                "LinkedIn-Version": ver,
            }
            logger.info("Initializing image upload via LinkedIn REST API (version %s)...", ver)
            resp = client.post(
                f"{LINKEDIN_REST_BASE}/images?action=initializeUpload",
                headers=headers,
                json=init_payload,
            )
            if resp.status_code in (200, 201):
                data = resp.json().get("value", {})
                image_urn = data.get("image")
                upload_url = data.get("uploadUrl")
                if image_urn and upload_url:
                    # Step 2: Binary PUT
                    with open(image_path, "rb") as f:
                        image_bytes = f.read()

                    put_headers = {
                        "Authorization": f"Bearer {access_token}",
                        "Content-Type": "image/png",
                    }
                    logger.info("Uploading binary image bytes to LinkedIn upload URL...")
                    put_resp = client.put(upload_url, headers=put_headers, content=image_bytes)
                    if put_resp.status_code in (200, 201, 204):
                        logger.info("Successfully uploaded image to LinkedIn: %s (using version %s)", image_urn, ver)
                        return image_urn
                    else:
                        raise RuntimeError(f"LinkedIn binary image upload failed ({put_resp.status_code}): {put_resp.text}")

            logger.warning("LinkedIn image initializeUpload failed with version %s (status %d): %s", ver, resp.status_code, resp.text)
            last_err = RuntimeError(f"LinkedIn image initializeUpload failed ({resp.status_code}): {resp.text}")

    raise last_err or RuntimeError("Failed to initialize LinkedIn image upload on all versions.")


def strip_urls_from_text(text: str) -> tuple[str, list[str]]:
    """Removes outbound URLs from the post body to protect LinkedIn feed reach.
    Returns (cleaned_text, list_of_extracted_urls).
    """
    import re
    urls: list[str] = []

    # 1. Match markdown links [Label](https://...) -> replace with Label
    def md_repl(match):
        label = match.group(1)
        url = match.group(2)
        urls.append(url)
        return label

    cleaned = re.sub(r"\[([^\]]+)\]\((https?://[^\s\)]+)\)", md_repl, text)

    # 2. Match raw URLs
    def raw_repl(match):
        url = match.group(0)
        urls.append(url)
        return ""

    cleaned = re.sub(r"https?://[^\s]+", raw_repl, cleaned)

    # Clean up empty lines or orphan labels like "Source & Paper: " or "Read more: "
    cleaned = re.sub(r"(?im)^(?:source\s*(?:&|and)?\s*paper|read\s*more|link(?:\s+to\s+the\s+paper)?):\s*$", "", cleaned)
    # Normalize double linebreaks
    paragraphs = [p.strip() for p in cleaned.split("\n\n") if p.strip()]
    return "\n\n".join(paragraphs), urls


def _add_linkedin_comment_rest(
    post_urn: str,
    comment_text: str,
    access_token: str,
    person_urn: str,
) -> str | None:
    """Posts the 1st comment on a LinkedIn post via official REST API."""
    import urllib.parse
    import httpx

    target_urn = post_urn
    if not target_urn.startswith("urn:li:"):
        target_urn = f"urn:li:share:{post_urn}"

    encoded_urn = urllib.parse.quote(target_urn, safe="")
    url = f"{LINKEDIN_REST_BASE}/socialActions/{encoded_urn}/comments"

    payload = {
        "actor": person_urn,
        "object": target_urn,
        "message": {
            "text": comment_text,
        },
    }

    global LAST_COMMENT_STATUS
    versions_to_try = [LINKEDIN_API_VERSION] + [v for v in CANDIDATE_VERSIONS if v != LINKEDIN_API_VERSION]
    with httpx.Client(timeout=15.0) as client:
        for ver in versions_to_try:
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
                "X-Restli-Protocol-Version": "2.0.0",
                "LinkedIn-Version": ver,
            }
            logger.info("Posting 1st comment to LinkedIn REST API (version %s)...", ver)
            try:
                resp = client.post(url, headers=headers, json=payload)
                if resp.status_code in (200, 201):
                    comment_urn = resp.headers.get("x-restli-id") or resp.json().get("id") or "created"
                    logger.info("Successfully posted 1st comment on LinkedIn post %s: %s", target_urn, comment_urn)
                    LAST_COMMENT_STATUS = "posted"
                    return comment_urn
                logger.warning(
                    "Posting comment failed with version %s (status %d): %s",
                    ver,
                    resp.status_code,
                    resp.text,
                )
            except Exception as e:
                logger.warning("LinkedIn comment request failed with version %s: %s", ver, e)

    LAST_COMMENT_STATUS = "pending_manual"
    logger.warning("Could not post 1st comment via LinkedIn REST API on any candidate version.")
    return None


def _post_official_rest(text: str, image_path: str | None = None, first_comment: str | None = None) -> str:
    """Publishes a post directly using the official LinkedIn /rest/posts API and attaches 1st comment."""
    access_token = os.getenv("LINKEDIN_ACCESS_TOKEN", "").strip()
    if not access_token:
        raise RuntimeError("LINKEDIN_ACCESS_TOKEN is not configured in .env.")

    person_urn = _get_linkedin_person_urn(access_token)
    import httpx

    image_urn = None
    if image_path and os.path.exists(image_path):
        image_urn = _upload_linkedin_image_rest(image_path, access_token, person_urn)

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

    versions_to_try = [LINKEDIN_API_VERSION] + [v for v in CANDIDATE_VERSIONS if v != LINKEDIN_API_VERSION]
    last_err: Exception | None = None

    with httpx.Client(timeout=20.0) as client:
        for ver in versions_to_try:
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
                "X-Restli-Protocol-Version": "2.0.0",
                "LinkedIn-Version": ver,
            }
            logger.info("Submitting post to official LinkedIn /rest/posts endpoint (version %s)...", ver)
            resp = client.post(f"{LINKEDIN_REST_BASE}/posts", headers=headers, json=payload)
            if resp.status_code in (200, 201):
                post_urn = resp.headers.get("x-restli-id") or ""
                logger.info("Successfully created LinkedIn post via official REST API: %s", post_urn)

                # Post 1st comment immediately after publishing
                if first_comment and post_urn:
                    comment_res = _add_linkedin_comment_rest(post_urn, first_comment, access_token, person_urn)
                    if not comment_res:
                        global LAST_COMMENT_STATUS
                        LAST_COMMENT_STATUS = "pending_manual"

                if post_urn:
                    return f"https://www.linkedin.com/feed/update/{post_urn}"
                return "https://www.linkedin.com/in/me/recent-activity/all/"
            logger.warning("LinkedIn /rest/posts failed with version %s (status %d): %s", ver, resp.status_code, resp.text)
            last_err = RuntimeError(f"LinkedIn /rest/posts failed ({resp.status_code}): {resp.text}")

    raise last_err or RuntimeError("Failed to create LinkedIn post on all API versions.")


def post(text: str, image_path: str | None = None, first_comment: str | None = None) -> str:
    """Publishes a post to LinkedIn using official REST API and handles 1st comment.

    Signature: post(text: str, image_path: str | None, first_comment: str | None) -> post_url: str
    If DRY_RUN=true, logs the action and returns a mock LinkedIn URL.
    Uses the official LinkedIn REST API (/rest/posts) with LINKEDIN_ACCESS_TOKEN.
    """
    global LAST_COMMENT_STATUS
    clean_text, extracted_urls = strip_urls_from_text(format_linkedin_text(text))

    # If first_comment was not explicitly provided but URLs were stripped from body,
    # turn them into the 1st comment automatically
    if not first_comment and extracted_urls:
        first_comment = f"Link to the paper & source 👇\n" + "\n".join(extracted_urls)

    if is_dry_run():
        logger.info("[DRY-RUN] Simulating LinkedIn post publication.")
        logger.info("[DRY-RUN] Post content preview (first 150 chars):\n%s...", clean_text[:150])
        if image_path:
            logger.info("[DRY-RUN] Post attached image: %s", image_path)
        fake_id = "dryrun_" + str(abs(hash(clean_text)))[:10]
        post_url = f"https://www.linkedin.com/feed/update/urn:li:activity:{fake_id}"

        if first_comment:
            logger.info("[DRY-RUN] Simulating 1st comment publication on LinkedIn post: %s", post_url)
            logger.info("[DRY-RUN] 1st Comment content:\n%s", first_comment)
            LAST_COMMENT_STATUS = "posted"

        return post_url

    if not os.getenv("LINKEDIN_ACCESS_TOKEN"):
        raise RuntimeError("LINKEDIN_ACCESS_TOKEN is not configured in .env.")

    logger.info("Using official LinkedIn REST API (/rest/posts) with w_member_social...")
    return _post_official_rest(clean_text, image_path, first_comment=first_comment)
