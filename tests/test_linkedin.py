"""Tests for LinkedIn publishing and dry-run simulation."""

import os
import pytest
from integrations import linkedin


def test_dry_run_mode(monkeypatch):
    monkeypatch.setenv("DRY_RUN", "true")
    assert linkedin.is_dry_run() is True

    url = linkedin.post("Breaking AI news breakdown", image_path=None)
    assert url.startswith("https://www.linkedin.com/feed/update/urn:li:activity:dryrun_")


def test_dry_run_with_image(monkeypatch, tmp_path):
    monkeypatch.setenv("DRY_RUN", "true")
    fake_img = tmp_path / "card.png"
    fake_img.write_text("fake image content")

    url = linkedin.post("Another exciting development", image_path=str(fake_img))
    assert "dryrun_" in url


def test_format_linkedin_text():
    markdown = "Here are the benefits:\n- **Isolation:** Great feature\n- **Security:** Strict boundaries"
    formatted = linkedin.format_linkedin_text(markdown)
    assert "**" not in formatted
    assert "•" in formatted
    assert "𝗜𝘀𝗼𝗹𝗮𝘁𝗶𝗼𝗻:" in formatted
