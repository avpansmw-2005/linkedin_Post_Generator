from __future__ import annotations

import os
from typing import Literal, TypedDict
from langgraph.checkpoint.sqlite import SqliteSaver


class NewsItem(TypedDict, total=False):
    title: str
    url: str
    source: str
    summary: str
    published: str
    category: str  # "ai_learning" | "developer_mistake" | "latest_news"
    relative_time: str


class RankedItem(NewsItem, total=False):
    score: float
    reason: str


class PipelineState(TypedDict, total=False):
    run_date: str
    topic: str | None
    mode: str | None  # "all" | "learning" | "mistakes" | "news"
    raw_items: list[NewsItem]
    ranked_top5: list[RankedItem]
    chosen_story: RankedItem
    draft_post: str
    draft_hashtags: list[str]
    draft_metadata: dict
    image_mode: Literal["card", "ai_visual"]
    draft_image_path: str
    humanized_post: str
    ai_detection_score: int
    review_status: Literal["pending", "approved", "edit_requested"]
    user_edit_notes: str | None
    final_post: str
    final_image_path: str
    linkedin_post_url: str


import sqlite3


def get_checkpointer(db_path: str = "data/pipeline.db") -> SqliteSaver:
    """Returns a SqliteSaver checkpointer instance.
    Ensures the parent directory exists before connecting.
    """
    parent_dir = os.path.dirname(db_path)
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    return SqliteSaver(conn)
