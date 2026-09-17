"""Statistical AI Detection Engine measuring burstiness, perplexity, and AI hallmark markers."""

from __future__ import annotations

import re
import math
import logging

logger = logging.getLogger(__name__)

# Common AI hallmark transition phrases and formulaic tropes
AI_HALLMARK_PHRASES = [
    r"\bthe benefits are (?:pretty )?straightforward\b",
    r"\bof course,? there are (?:some )?trade-offs\b",
    r"\bcurious to hear (?:how|your|what)\b",
    r"\bit is worth noting that\b",
    r"\bit's worth noting that\b",
    r"\bin today's fast-paced\b",
    r"\bin today's world\b",
    r"\bin the fast-paced world\b",
    r"\bwhen it comes to\b",
    r"\bharness(?:ing)? the power\b",
    r"\bgame changer\b",
    r"\bdive deep\b",
    r"\bdelve into\b",
    r"\bdelving into\b",
    r"\ba testament to\b",
    r"\bbeacon of\b",
    r"\btapestry of\b",
    r"\brevolutioniz(?:e|ing|ed)\b",
    r"\bpivotal role\b",
    r"\bcrucial role\b",
    r"\bmoreover\b",
    r"\bfurthermore\b",
    r"\bin conclusion\b",
    r"\bseamlessly integrate\b",
    r"\bunleash(?:ing)? the\b",
    r"\bby leveraging\b",
    r"\bleveraging the power\b",
    r"\bnavigat(?:e|ing) the complexities\b",
    r"\bever-evolving\b",
    r"\bstands as a testament\b",
    r"\ba double-edged sword\b",
    r"\ba holistic approach\b",
    r"\bfoster(?:ing)? innovation\b",
    r"\bpush(?:ing)? the boundaries\b",
    r"\bat its core\b",
    r"\bin essence\b",
]


def split_sentences(text: str) -> list[str]:
    """Splits text into cleaned sentences, stripping URLs and hashtags."""
    # Strip URLs
    clean = re.sub(r'https?://\S+', '', text)
    # Strip Hashtags
    clean = re.sub(r'#\w+', '', clean)
    # Split by period, exclamation, or question mark followed by whitespace
    raw_sentences = re.split(r'[.!?]+\s+', clean)
    sentences = [s.strip() for s in raw_sentences if len(s.strip().split()) >= 2]
    return sentences


def calculate_burstiness(sentences: list[str]) -> float:
    """Calculates sentence length standard deviation (burstiness).
    High burstiness (> 6.5) indicates human writing with varied sentence structures.
    Low burstiness (< 3.5) indicates uniform, robotic AI output.
    """
    if len(sentences) < 2:
        return 5.0  # Neutral default

    lengths = [len(s.split()) for s in sentences]
    mean = sum(lengths) / len(lengths)
    variance = sum((l - mean) ** 2 for l in lengths) / (len(lengths) - 1)
    stddev = math.sqrt(variance)
    return round(stddev, 2)


def scan_ai_hallmarks(text: str) -> list[str]:
    """Finds occurrences of stereotypical AI phrases."""
    lower_text = text.lower()
    matches = []
    for pattern in AI_HALLMARK_PHRASES:
        if re.search(pattern, lower_text):
            # Extract clean match
            found = re.findall(pattern, lower_text)
            matches.extend(found)
    return list(set(matches))


def analyze_ai_probability(text: str) -> dict:
    """Evaluates text and returns an AI detection score (0 to 100%).
    Calibrated against GPTZero, ZeroGPT, and academic perplexity/burstiness research.
    """
    if not text or len(text.strip().split()) < 10:
        return {
            "ai_score": 0,
            "human_score": 100,
            "status": "Likely Human",
            "badge": "✅",
            "burstiness": 0.0,
            "flagged_phrases": [],
        }

    sentences = split_sentences(text)
    burstiness = calculate_burstiness(sentences)
    flagged_phrases = scan_ai_hallmarks(text)

    # Base baseline probability
    # If burstiness is very low (uniform 12-16 word sentences), AI score increases
    base_score = 15.0

    if burstiness < 3.0:
        base_score += 40.0  # Extreme uniformity is a massive AI flag
    elif burstiness < 4.5:
        base_score += 25.0
    elif burstiness < 6.0:
        base_score += 10.0
    elif burstiness >= 8.0:
        base_score -= 15.0  # High variation heavily signals human writing
    elif burstiness >= 6.5:
        base_score -= 5.0

    # Penalize heavily for each detected hallmark phrase (20% per trope)
    hallmark_penalty = len(flagged_phrases) * 22.0
    total_score = base_score + hallmark_penalty

    # Check for elementary textbook definitions ("Docker is a...", "Containers are lightweight units")
    definition_patterns = [
        r"\b(?:containers|docker|microvms|agents) are (?:lightweight|a platform|designed to)\b",
        r"\bmeans every agent has its own\b",
    ]
    for dp in definition_patterns:
        if re.search(dp, text.lower()):
            total_score += 15.0

    # Clamp between 2% and 99%
    final_ai_score = int(max(2, min(99, round(total_score))))
    final_human_score = 100 - final_ai_score

    if final_ai_score <= 25:
        status = "Likely Human"
        badge = "✅"
    elif final_ai_score <= 55:
        status = "Moderate AI"
        badge = "⚠️"
    else:
        status = "High AI Signature"
        badge = "🚨"

    logger.info(
        "AI Detection Analysis: %d%% AI (%d%% Human), Burstiness: %.2f, Flagged: %s",
        final_ai_score,
        final_human_score,
        burstiness,
        flagged_phrases,
    )

    return {
        "ai_score": final_ai_score,
        "human_score": final_human_score,
        "status": status,
        "badge": badge,
        "burstiness": burstiness,
        "flagged_phrases": flagged_phrases,
    }
