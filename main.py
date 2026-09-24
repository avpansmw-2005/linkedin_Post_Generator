"""Unified entrypoint for the AI News to LinkedIn Agent.

Runs the Telegram Bot polling daemon with integrated APScheduler cron jobs,
and supports direct CLI manual invocation.
"""

from __future__ import annotations

import os
import sys
import argparse
import asyncio
import logging
from datetime import datetime, timezone
from dotenv import load_dotenv

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from orchestrator import create_pipeline
from integrations.telegram_bot import build_telegram_app, trigger_pipeline_run, get_allowed_chat_id

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("main")


def parse_args():
    parser = argparse.ArgumentParser(description="AI News -> LinkedIn Agent")
    parser.add_argument(
        "--run-once",
        action="store_true",
        help="Run the pipeline in CLI mode without starting the Telegram bot daemon.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Force DRY_RUN=true for testing without live LinkedIn publishing.",
    )
    parser.add_argument(
        "--topic",
        type=str,
        default=None,
        help="Specific topic to search for (e.g. --topic 'MCP' or --topic 'PostgreSQL').",
    )
    parser.add_argument(
        "--mode",
        type=str,
        choices=["all", "learning", "mistakes", "news"],
        default=None,
        help="Filter mode: 'learning', 'mistakes', 'news', or 'all'.",
    )
    parser.add_argument(
        "--humor",
        action="store_true",
        help="Inject witty developer satire and relatable engineering comedy into the post.",
    )
    return parser.parse_args()


def run_cli_pipeline(topic: str | None = None, mode: str | None = None, humor: bool = False):
    """Runs a demonstration pipeline pass in the terminal with Agentic Style Communication."""
    print("\n" + "=" * 65)
    print("🤖 AUTONOMOUS MULTI-AGENT LINKEDIN CONTENT PIPELINE")
    print("=" * 65)
    logger.info("Executing pipeline in CLI mode (topic=%s, mode=%s, humor=%s)...", topic, mode, humor)
    app = create_pipeline()
    thread_id = f"cli_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    config = {"configurable": {"thread_id": thread_id}}

    print("\n🕵️‍♂️ [Research Scout Agent] Scouring Google News & Search, Hacker News, Dev.to & Tech Feeds...")
    print("   • Querying premier publications: Forbes, Tom's Hardware, VentureBeat, TechCrunch, The New Stack")
    print("   • Analyzing what developers and practitioners actually want to hear...")
    if humor:
        print("   • 🎭 Humor Mode: Active (will inject sharp engineering satire)")

    input_payload = {"run_date": datetime.now(timezone.utc).isoformat(), "humor_mode": humor}
    if topic:
        input_payload["topic"] = topic
    if mode:
        input_payload["mode"] = mode
    state = app.invoke(input_payload, config=config)

    ranked_stories = state.get("ranked_options") or state.get("ranked_top10") or state.get("ranked_top5", [])
    if not ranked_stories:
        logger.warning("No news stories returned.")
        return

    count = len(ranked_stories)
    print("\n" + "-" * 65)
    print(f"⚖️ [Signal Curator Agent] Screened candidate stories. Top {count} ranked by signal:")
    print("-" * 65)
    for idx, story in enumerate(ranked_stories, start=1):
        cat = story.get("category", "ai_learning").replace("_", " ").upper()
        print(f"\n[{idx}] [{story.get('source')}] {story.get('title')}")
        print(f"    Category: {cat} | Signal Score: {story.get('score')}")
        print(f"    💡 Takeaway: {story.get('reason')}")
    print("\n" + "-" * 65)

    # In CLI mode, prompt terminal user to pick
    try:
        user_input = input(f"\n👉 Select a story number (1-{count}) or press Enter for #1: ").strip()
        idx = int(user_input) - 1 if user_input.isdigit() else 0
        idx = max(0, min(idx, count - 1))
    except (EOFError, KeyboardInterrupt):
        idx = 0

    chosen = ranked_stories[idx]
    print(f"\n✅ Selected Story: {chosen.get('title')}")

    from langgraph.types import Command

    print("\n🤖 [Collaborative Agent Execution In Motion]")
    print("   • ✍️ [Senior Tech Writer Agent] Drafting structured post & debate-sparking CTA...")
    print("   • 🎨 [Visual Architect Agent] Rendering high-dwell infographic card...")
    print("   • 🧬 [Voice & Anti-AI Agent] Eliminating clichés and maximizing burstiness...")

    state2 = app.invoke(Command(resume=chosen), config=config)

    from agents import detector
    ai_score_info = detector.analyze_ai_probability(state2.get("humanized_post") or state2.get("draft_post", ""))

    print("\n" + "=" * 65)
    print("📋 [Quality Gate Agent Report] GENERATED POST DRAFT")
    print(f"🛡️  AI Detection Score: {ai_score_info['ai_score']}% AI · {ai_score_info['human_score']}% Human ({ai_score_info['status']})")
    print(f"⚡ Burstiness Variance: {ai_score_info['burstiness']:.2f}")
    print("=" * 65)
    print(state2.get("humanized_post") or state2.get("draft_post"))
    print("=" * 65)
    if state2.get("first_comment"):
        print(f"💬 1st Comment (Published with post):\n{state2.get('first_comment')}")
        print("=" * 65)
    print(f"🖼️ Generated Card Image: {state2.get('draft_image_path')}\n")

    try:
        review_choice = input("👉 Options: Press Enter/'approve' to publish, 'humor' for witty satire, or type edit notes: ").strip()
    except (EOFError, KeyboardInterrupt):
        review_choice = "approve"

    if review_choice.lower() == "approve" or not review_choice:
        print("\n🚀 [Publisher Agent] Dispatching post to LinkedIn REST API...")
        state3 = app.invoke(Command(resume={"action": "approve"}), config=config)
        print(f"\n🎉 Published Successfully! URL: {state3.get('linkedin_post_url')}")
        from integrations import linkedin
        if state3.get("first_comment"):
            if linkedin.LAST_COMMENT_STATUS == "posted":
                print(f"💬 1st Comment Published Automatically:\n{state3.get('first_comment')}\n")
            else:
                print(
                    f"⚠️  1st Comment could not be posted automatically (LinkedIn developer tokens lack commenting permission).\n"
                    f"👉 Copy & drop this 1st comment manually on your post:\n\n"
                    f"{state3.get('first_comment')}\n"
                )
    elif review_choice.lower() in ("humor", "wit", "funny"):
        print("\n🎭 [Humor Specialist Agent] Injecting sharp developer wit and relatable tech satire...")
        state3 = app.invoke(Command(resume={"action": "humor"}), config=config)
        print("\n" + "=" * 65)
        print("🎭 [Humor Specialist Agent] REVISED DRAFT WITH WIT:")
        print("=" * 65)
        print(state3.get("humanized_post"))
        print("=" * 65)
        auto_pub = input("\nType 'approve' to publish this humorous version, or press Enter: ").strip()
        state4 = app.invoke(Command(resume={"action": "approve"}), config=config)
        print(f"\n🎉 Published Successfully! URL: {state4.get('linkedin_post_url')}")
    else:
        print(f"\n🎯 [Command Center] Directive received: \"{review_choice}\"")
        print("   • 🧬 [Humanizer Agent] Executing rewrite with mandatory executive override...")
        print("   • 🔍 [Quality Gate Agent] Verifying constraint compliance...")
        state3 = app.invoke(Command(resume={"action": "edit", "notes": review_choice}), config=config)
        revised = state3.get("humanized_post", "")
        if "remove hyphen" in review_choice.lower() or "no hyphen" in review_choice.lower():
            if "-" not in revised and "—" not in revised:
                print("   • ✅ [Quality Gate Agent] Verified: 0 hyphens or dashes in revised text.")
        print("\n" + "=" * 65)
        print("📋 [Quality Gate Agent] REVISED POST:")
        print("=" * 65)
        print(revised)
        print("=" * 65)
        if state3.get("first_comment"):
            print(f"💬 1st Comment:\n{state3.get('first_comment')}")
            print("=" * 65)
        # Auto-approve revised
        print("\n🚀 [Publisher Agent] Dispatching finalized post to LinkedIn REST API...")
        state4 = app.invoke(Command(resume={"action": "approve"}), config=config)
        print(f"\n🎉 Published Successfully! URL: {state4.get('linkedin_post_url')}")
        from integrations import linkedin
        if state4.get("first_comment"):
            if linkedin.LAST_COMMENT_STATUS == "posted":
                print(f"💬 1st Comment Published Automatically:\n{state4.get('first_comment')}\n")
            else:
                print(
                    f"⚠️  1st Comment could not be posted automatically (LinkedIn developer tokens lack commenting permission).\n"
                    f"👉 Copy & drop this 1st comment manually on your post:\n\n"
                    f"{state4.get('first_comment')}\n"
                )


async def scheduled_pipeline_trigger(bot):
    """Callback for APScheduler cron trigger."""
    chat_id = get_allowed_chat_id()
    if not chat_id:
        logger.warning("Scheduled job triggered, but TELEGRAM_ALLOWED_CHAT_ID is not set.")
        return
    logger.info("Triggering scheduled pipeline scan for chat ID: %s", chat_id)
    await trigger_pipeline_run(chat_id, bot)


def main():
    args = parse_args()
    if args.dry_run:
        os.environ["DRY_RUN"] = "true"

    if args.run_once:
        run_cli_pipeline(topic=args.topic, mode=args.mode, humor=args.humor)
        return

    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not bot_token or bot_token == "your_telegram_bot_token_here":
        logger.error(
            "TELEGRAM_BOT_TOKEN is not set in .env! "
            "Please create your bot via @BotFather and set the token in .env. "
            "Alternatively, run with --run-once for terminal testing."
        )
        sys.exit(1)

    logger.info("Configuring Telegram bot application and scheduler...")
    scheduler = AsyncIOScheduler()
    cron_expr = os.getenv("PIPELINE_SCHEDULE_CRON", "0 9 * * 1-5")  # Default 9 AM Weekdays
    parts = cron_expr.split()

    async def on_startup(app):
        # 1. Register Telegram command menu button popup
        from telegram import BotCommand
        bot_commands = [
            BotCommand("topic", "Search stories by topic (e.g. /topic postgres)"),
            BotCommand("random", "Pick a random technical topic to explore"),
            BotCommand("fetch", "Scan daily developer engineering blogs"),
            BotCommand("status", "View current pipeline status"),
            BotCommand("help", "Show bot commands and guide"),
        ]
        try:
            await app.bot.set_my_commands(bot_commands)
            logger.info("Telegram command menu button registered successfully.")
        except Exception as e:
            logger.warning("Could not register bot commands with Telegram: %s", e)

        # 2. Start APScheduler if cron schedule configured
        if len(parts) == 5:
            minute, hour, day, month, day_of_week = parts
            scheduler.add_job(
                scheduled_pipeline_trigger,
                trigger=CronTrigger(
                    minute=minute,
                    hour=hour,
                    day=day,
                    month=month,
                    day_of_week=day_of_week,
                ),
                args=[app.bot],
                id="scheduled_linkedin_pipeline",
                replace_existing=True,
            )
            scheduler.start()
            logger.info("APScheduler started with cron schedule: '%s'", cron_expr)
        else:
            logger.warning("Invalid PIPELINE_SCHEDULE_CRON '%s'; scheduler disabled.", cron_expr)

    async def on_shutdown(app):
        if scheduler.running:
            scheduler.shutdown(wait=False)
            logger.info("APScheduler stopped.")

    application = build_telegram_app(post_init=on_startup, post_shutdown=on_shutdown)

    logger.info("Starting Telegram polling daemon. Press Ctrl+C to stop.")
    application.run_polling()


# ==============================================================================
# Vercel Serverless / ASGI Compatibility
# ==============================================================================
async def app(scope, receive, send):
    """ASGI entrypoint allowing Vercel to serve the dashboard without error."""
    if scope.get("type") == "http":
        path = scope.get("path", "/")
        clean_path = path.lstrip("/")
        base_dir = os.path.join(os.path.dirname(__file__), "frontend")
        
        filename = clean_path if clean_path else "index.html"
        filepath = os.path.join(base_dir, filename)

        if not (os.path.exists(filepath) and os.path.isfile(filepath)):
            filepath = os.path.join(base_dir, "index.html")

        ext = os.path.splitext(filepath)[1].lower()
        content_types = {
            ".html": b"text/html; charset=utf-8",
            ".css": b"text/css; charset=utf-8",
            ".js": b"application/javascript; charset=utf-8",
            ".json": b"application/json",
            ".png": b"image/png",
            ".svg": b"image/svg+xml",
        }
        content_type = content_types.get(ext, b"text/html; charset=utf-8")

        try:
            with open(filepath, "rb") as f:
                body = f.read()
        except Exception:
            body = b"Not Found"

        await send({
            "type": "http.response.start",
            "status": 200,
            "headers": [
                [b"content-type", content_type],
                [b"content-length", str(len(body)).encode("ascii")],
            ],
        })
        await send({
            "type": "http.response.body",
            "body": body,
        })


if __name__ == "__main__":
    main()
