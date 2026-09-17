"""LangGraph orchestrator for the AI News to LinkedIn publishing pipeline."""

from __future__ import annotations

import logging
from typing import Any, Callable
from langgraph.graph import StateGraph, START, END
from langgraph.types import interrupt

from state import PipelineState, get_checkpointer

logger = logging.getLogger(__name__)


class PipelineOrchestrator:
    """Encapsulates node functions and graph building for the pipeline."""

    def __init__(
        self,
        fetcher_fn: Callable[[], list[dict]] | None = None,
        ranker_fn: Callable[[list[dict]], list[dict]] | None = None,
        writer_fn: Callable[[dict], dict] | None = None,
        imagegen_fn: Callable[[dict, dict], str] | None = None,
        humanizer_fn: Callable[[str, str | None, dict | None], str] | None = None,
        publisher_fn: Callable[[str, str | None], str] | None = None,
    ):
        # Lazy imports of default modules to avoid premature side-effects
        if fetcher_fn is None:
            from agents import fetcher
            fetcher_fn = fetcher.fetch_all
        if ranker_fn is None:
            from agents import ranker
            ranker_fn = ranker.rank
        if writer_fn is None:
            from agents import writer
            writer_fn = writer.write
        if imagegen_fn is None:
            from agents import imagegen
            imagegen_fn = imagegen.render
        if humanizer_fn is None:
            from agents import humanizer
            humanizer_fn = humanizer.rewrite
        if publisher_fn is None:
            from integrations import linkedin
            publisher_fn = linkedin.post

        self.fetcher_fn = fetcher_fn
        self.ranker_fn = ranker_fn
        self.writer_fn = writer_fn
        self.imagegen_fn = imagegen_fn
        self.humanizer_fn = humanizer_fn
        self.publisher_fn = publisher_fn

    def fetch_news(self, state: PipelineState) -> dict:
        logger.info("Fetching AI news stories...")
        items = self.fetcher_fn()
        return {"raw_items": items}

    def rank_news(self, state: PipelineState) -> dict:
        logger.info("Ranking news items...")
        raw_items = state.get("raw_items", [])
        top5 = self.ranker_fn(raw_items)
        return {"ranked_top5": top5}

    def await_story_choice(self, state: PipelineState) -> dict:
        logger.info("Pausing for user story selection (interrupt 1)...")
        options = state.get("ranked_top5", [])
        choice = interrupt({
            "kind": "story_choice",
            "options": options,
        })
        return {"chosen_story": choice}

    def generate_draft(self, state: PipelineState) -> dict:
        logger.info("Generating post draft and rendering image card...")
        chosen = state.get("chosen_story")
        if not chosen:
            raise ValueError("No story chosen before generate_draft!")

        draft = self.writer_fn(chosen)
        image_path = self.imagegen_fn(chosen, draft)
        return {
            "draft_post": draft.get("text", ""),
            "draft_hashtags": draft.get("tags", []),
            "draft_image_path": image_path,
        }

    def humanize(self, state: PipelineState) -> dict:
        logger.info("Humanizing post tone and incorporating edit feedback...")
        edit_notes = state.get("user_edit_notes")
        base_text = state.get("humanized_post") or state.get("draft_post", "")
        chosen = state.get("chosen_story")

        rewritten = self.humanizer_fn(base_text, edit_notes, chosen)
        return {
            "humanized_post": rewritten,
            "user_edit_notes": None,
        }

    def await_review(self, state: PipelineState) -> dict:
        logger.info("Pausing for user post review (interrupt 2)...")
        feedback = interrupt({
            "kind": "review",
            "text": state.get("humanized_post", ""),
            "image": state.get("draft_image_path", ""),
            "hashtags": state.get("draft_hashtags", []),
        })

        if not isinstance(feedback, dict):
            raise ValueError(f"Invalid review feedback payload: {feedback}")

        action = feedback.get("action")
        if action == "approve":
            return {
                "review_status": "approved",
                "final_post": state.get("humanized_post", ""),
                "final_image_path": state.get("draft_image_path", ""),
            }
        elif action in ("edit", "edit_requested"):
            return {
                "review_status": "edit_requested",
                "user_edit_notes": feedback.get("notes", ""),
            }
        else:
            raise ValueError(f"Unknown review action: {action}")

    def route_after_review(self, state: PipelineState) -> str:
        status = state.get("review_status")
        if status == "approved":
            return "publish"
        return "humanize"

    def publish(self, state: PipelineState) -> dict:
        logger.info("Publishing finalized post to LinkedIn...")
        final_post = state.get("final_post", "")
        image_path = state.get("final_image_path")
        post_url = self.publisher_fn(final_post, image_path)
        return {"linkedin_post_url": post_url}

    def build_graph(self, checkpointer: Any = None):
        """Constructs and compiles the StateGraph with interrupt checkpointer."""
        workflow = StateGraph(PipelineState)

        # Register nodes
        workflow.add_node("fetch_news", self.fetch_news)
        workflow.add_node("rank_news", self.rank_news)
        workflow.add_node("await_story_choice", self.await_story_choice)
        workflow.add_node("generate_draft", self.generate_draft)
        workflow.add_node("humanize", self.humanize)
        workflow.add_node("await_review", self.await_review)
        workflow.add_node("publish", self.publish)

        # Wire linear flow
        workflow.add_edge(START, "fetch_news")
        workflow.add_edge("fetch_news", "rank_news")
        workflow.add_edge("rank_news", "await_story_choice")
        workflow.add_edge("await_story_choice", "generate_draft")
        workflow.add_edge("generate_draft", "humanize")
        workflow.add_edge("humanize", "await_review")

        # Conditional loop for review
        workflow.add_conditional_edges(
            "await_review",
            self.route_after_review,
            {
                "publish": "publish",
                "humanize": "humanize",
            },
        )
        workflow.add_edge("publish", END)

        if checkpointer is None:
            checkpointer = get_checkpointer()

        return workflow.compile(checkpointer=checkpointer)


def create_pipeline(checkpointer: Any = None):
    """Convenience factory to create and compile the production pipeline graph."""
    orchestrator = PipelineOrchestrator()
    return orchestrator.build_graph(checkpointer=checkpointer)
