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
    return parser.parse_args()


def run_cli_pipeline():
    """Runs a demonstration pipeline pass in the terminal."""
    logger.info("Executing pipeline in CLI mode...")
    app = create_pipeline()
    thread_id = f"cli_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    config = {"configurable": {"thread_id": thread_id}}

    logger.info("Step 1: Fetching & Ranking...")
    state = app.invoke({"run_date": datetime.now(timezone.utc).isoformat()}, config=config)

    top5 = state.get("ranked_top5", [])
    if not top5:
        logger.warning("No news stories returned.")
        return

    print("\n" + "=" * 60)
    print("TOP 5 RANKED AI STORIES:")
    print("=" * 60)
    for idx, story in enumerate(top5, start=1):
        print(f"\n[{idx}] {story.get('title')}")
        print(f"    Source: {story.get('source')} | Score: {story.get('score')}")
        print(f"    Reason: {story.get('reason')}")
    print("=" * 60 + "\n")

    # In CLI mode, prompt terminal user to pick
    try:
        user_input = input("Select a story number (1-5) or press Enter for #1: ").strip()
        idx = int(user_input) - 1 if user_input.isdigit() else 0
        idx = max(0, min(idx, len(top5) - 1))
    except (EOFError, KeyboardInterrupt):
        idx = 0

    chosen = top5[idx]
    logger.info("Selected: %s", chosen.get("title"))

    from langgraph.types import Command

    logger.info("Step 2: Generating draft, rendering card, and humanizing...")
    state2 = app.invoke(Command(resume=chosen), config=config)

    print("\n" + "=" * 60)
    print("GENERATED POST DRAFT (Zero Outbound Links):")
    print("=" * 60)
    print(state2.get("humanized_post") or state2.get("draft_post"))
    print("=" * 60)
    if state2.get("first_comment"):
        print(f"💬 1st Comment (Published with post):\n{state2.get('first_comment')}")
        print("=" * 60)
    print(f"Generated Card Image: {state2.get('draft_image_path')}\n")

    try:
        review_choice = input("Type 'approve' to publish, or type edit notes: ").strip()
    except (EOFError, KeyboardInterrupt):
        review_choice = "approve"

    if review_choice.lower() == "approve" or not review_choice:
        logger.info("Publishing to LinkedIn...")
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
    else:
        logger.info("Applying edits: %s", review_choice)
        state3 = app.invoke(Command(resume={"action": "edit", "notes": review_choice}), config=config)
        print("\n" + "=" * 60)
        print("REVISED POST:")
        print("=" * 60)
        print(state3.get("humanized_post"))
        print("=" * 60)
        if state3.get("first_comment"):
            print(f"💬 1st Comment:\n{state3.get('first_comment')}")
            print("=" * 60)
        # Auto-approve revised
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
        run_cli_pipeline()
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
