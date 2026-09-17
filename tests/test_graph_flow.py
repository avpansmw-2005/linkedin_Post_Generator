"""Unit test for LangGraph pause, resume, and human-in-the-loop review loop."""

import pytest
from langgraph.types import Command
from langgraph.checkpoint.memory import MemorySaver

from state import PipelineState
from orchestrator import PipelineOrchestrator


def make_stub_orchestrator():
    """Creates a PipelineOrchestrator with deterministic stub functions."""
    raw_stub_items = [
        {"title": f"Story {i}", "url": f"https://example.com/{i}", "source": "HN", "summary": f"Sum {i}", "published": "today"}
        for i in range(1, 10)
    ]

    def stub_fetcher():
        return raw_stub_items

    def stub_ranker(items):
        return [
            {**item, "score": 9.5 - idx * 0.5, "reason": f"Top pick {idx+1}"}
            for idx, item in enumerate(items[:5])
        ]

    def stub_writer(story):
        return {
            "text": f"Draft about {story['title']}",
            "tags": ["#AI", "#Tech"],
            "image_concept": "Futuristic neural network",
        }

    def stub_imagegen(story, draft):
        return "data/test_card.png"

    def stub_humanizer(base_text, edit_notes, story):
        if edit_notes:
            return f"{base_text} [Edited with: {edit_notes}]"
        return f"{base_text} [Humanized]"

    def stub_publisher(text, image_path):
        return "https://linkedin.com/feed/update/urn:li:activity:123456789"

    return PipelineOrchestrator(
        fetcher_fn=stub_fetcher,
        ranker_fn=stub_ranker,
        writer_fn=stub_writer,
        imagegen_fn=stub_imagegen,
        humanizer_fn=stub_humanizer,
        publisher_fn=stub_publisher,
    )


def test_pipeline_graph_full_flow():
    """Tests the full state graph flow including two interrupts and the edit loop."""
    orchestrator = make_stub_orchestrator()
    checkpointer = MemorySaver()
    app = orchestrator.build_graph(checkpointer=checkpointer)

    thread_id = "test-thread-full-flow"
    config = {"configurable": {"thread_id": thread_id}}

    # 1. Trigger pipeline -> should pause at await_story_choice
    state1 = app.invoke({"run_date": "2026-09-17"}, config=config)
    assert len(state1["raw_items"]) == 9
    assert len(state1["ranked_top5"]) == 5
    assert "chosen_story" not in state1 or state1["chosen_story"] is None

    # Check interrupt state
    current_snapshot = app.get_state(config)
    assert len(current_snapshot.tasks) > 0
    assert len(current_snapshot.tasks[0].interrupts) > 0
    interrupt_payload = current_snapshot.tasks[0].interrupts[0].value
    assert interrupt_payload["kind"] == "story_choice"
    assert len(interrupt_payload["options"]) == 5

    # 2. Resume with user's story choice (Story #2)
    selected_story = state1["ranked_top5"][1]
    state2 = app.invoke(Command(resume=selected_story), config=config)

    # Should have generated draft, humanized, and now paused at await_review
    assert state2["chosen_story"]["title"] == "Story 2"
    assert "Draft about Story 2" in state2["draft_post"]
    assert "[Humanized]" in state2["humanized_post"]
    assert state2["draft_image_path"] == "data/test_card.png"

    current_snapshot2 = app.get_state(config)
    assert len(current_snapshot2.tasks[0].interrupts) > 0
    review_payload = current_snapshot2.tasks[0].interrupts[0].value
    assert review_payload["kind"] == "review"

    # 3. Request edit (first review feedback)
    state3 = app.invoke(
        Command(resume={"action": "edit", "notes": "Make the tone more punchy"}),
        config=config,
    )
    # Graph routes back to humanize, applies notes, and pauses at await_review again
    assert state3["review_status"] == "edit_requested"
    assert "Make the tone more punchy" in state3["humanized_post"]

    current_snapshot3 = app.get_state(config)
    assert len(current_snapshot3.tasks[0].interrupts) > 0

    # 4. Final approval
    state4 = app.invoke(
        Command(resume={"action": "approve"}),
        config=config,
    )
    assert state4["review_status"] == "approved"
    assert state4["linkedin_post_url"] == "https://linkedin.com/feed/update/urn:li:activity:123456789"

    # Verify graph reached completion
    final_snapshot = app.get_state(config)
    assert len(final_snapshot.next) == 0  # No more pending nodes, at END
