"""Interactive Telegram bot providing human-in-the-loop gates for story choice and review."""

from __future__ import annotations

import os
import asyncio
import logging
import traceback
from datetime import datetime, timezone
from typing import Any
from dotenv import load_dotenv

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from langgraph.types import Command

from state import PipelineState
from orchestrator import create_pipeline
from agents.fetcher import get_random_topic

load_dotenv()

logger = logging.getLogger(__name__)

# Active threads tracking: chat_id -> active thread info
ACTIVE_SESSIONS: dict[int, dict[str, Any]] = {}


def get_allowed_chat_id() -> int | None:
    """Retrieves the authorized chat ID from environment."""
    raw = os.getenv("TELEGRAM_ALLOWED_CHAT_ID", "").strip()
    if raw and raw.isdigit():
        return int(raw)
    return None


def is_authorized(user_id: int) -> bool:
    """Verifies whether the interacting user is strictly authorized.
    Fails closed: if TELEGRAM_ALLOWED_CHAT_ID is missing, denies all access.
    """
    allowed = get_allowed_chat_id()
    if allowed is None:
        logger.error("SECURITY ALERT: TELEGRAM_ALLOWED_CHAT_ID is not configured in .env! Rejecting all requests.")
        return False
    return user_id == allowed


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles /start command, displaying status and user ID."""
    if not update.effective_user or not update.effective_message:
        return

    user_id = update.effective_user.id
    if not is_authorized(user_id):
        logger.warning(
            "SECURITY: Blocked unauthorized /start attempt from user_id=%s (@%s)",
            user_id,
            update.effective_user.username,
        )
        await update.effective_message.reply_text("⛔ Access Denied: This is a private bot.")
        return

    help_text = (
        f"🤖 **Developer LinkedIn Content Bot**\n\n"
        f"🔒 **Security Status:** Authenticated (User ID: `{user_id}`)\n\n"
        f"**Available Commands:**\n"
        f"• `/topic [name]` — Search fresh stories on a specific topic (e.g. `/topic postgres`, `/topic docker`, `/topic rust`)\n"
        f"• `/random` — Pick a random fascinating developer topic and get fresh stories\n"
        f"• `/fetch` or `/run` — Scan latest developer engineering blogs and Hacker News\n"
        f"• `/status` — View current pipeline status\n"
        f"• `/help` — Show this guide\n\n"
        f"When a story is selected, I'll generate the post draft and branded visual card for your review."
    )
    await update.effective_message.reply_text(help_text, parse_mode="Markdown")


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Displays active session information."""
    if not update.effective_user or not update.effective_message:
        return
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        await update.effective_message.reply_text("⛔ Unauthorized access.")
        return

    session = ACTIVE_SESSIONS.get(user_id)
    if not session:
        await update.effective_message.reply_text("No active pipeline run. Send `/fetch`, `/topic [name]`, or `/random`.")
        return

    status = (
        f"📊 **Active Pipeline Session**\n"
        f"• **Thread ID:** `{session.get('thread_id')}`\n"
        f"• **Topic:** `{session.get('topic', 'General Dev Scan')}`\n"
        f"• **Current Gate:** `{session.get('current_gate', 'in_progress')}`\n"
        f"• **Started At:** `{session.get('started_at')}`"
    )
    await update.effective_message.reply_text(status, parse_mode="Markdown")


def _run_graph_sync(app: Any, input_data: Any, config: dict):
    """Executes app.invoke synchronously inside a background thread pool."""
    return app.invoke(input_data, config=config)


async def trigger_pipeline_run(chat_id: int, bot: Any, topic: str | None = None) -> None:
    """Initiates a complete pipeline run for the specified chat, optionally filtered by topic."""
    try:
        app = create_pipeline()
    except Exception as e:
        logger.error("Pipeline graph creation failed: %s", e, exc_info=True)
        await bot.send_message(
            chat_id=chat_id,
            text=f"❌ **Failed to initialize pipeline:**\n`{e}`",
            parse_mode="Markdown",
        )
        return

    thread_id = f"run_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    config = {"configurable": {"thread_id": thread_id}}

    ACTIVE_SESSIONS[chat_id] = {
        "thread_id": thread_id,
        "config": config,
        "app": app,
        "topic": topic,
        "started_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "current_gate": "fetching",
    }

    if topic:
        status_text = f"🔍 *Searching real-time developer discussions and articles for:* **{topic}**..."
    else:
        status_text = "⏳ *Scanning developer engineering blogs, GitHub & Hacker News...*"

    await bot.send_message(
        chat_id=chat_id,
        text=status_text,
        parse_mode="Markdown",
    )

    # 1. Run until first interrupt (await_story_choice)
    loop = asyncio.get_running_loop()
    graph_input = {
        "run_date": datetime.now(timezone.utc).isoformat(),
        "topic": topic,
    }
    try:
        await loop.run_in_executor(
            None,
            _run_graph_sync,
            app,
            graph_input,
            config,
        )
    except Exception as e:
        logger.error("Pipeline initiation failed: %s", e, exc_info=True)
        await bot.send_message(chat_id=chat_id, text=f"❌ Pipeline failed during fetch/rank: `{e}`")
        ACTIVE_SESSIONS.pop(chat_id, None)
        return

    # Check interrupt payload
    state_snapshot = app.get_state(config)
    if not state_snapshot.tasks or not state_snapshot.tasks[0].interrupts:
        await bot.send_message(chat_id=chat_id, text="⚠️ Graph did not pause at expected story choice interrupt.")
        return

    interrupt_value = state_snapshot.tasks[0].interrupts[0].value
    options = interrupt_value.get("options", [])

    if not options:
        await bot.send_message(
            chat_id=chat_id,
            text=(
                f"🔍 *No stories found matching:* \"{topic or 'query'}\".\n\n"
                f"💡 *Tip:* Try using concise keywords like `/topic AI security`, `/topic agent memory`, or tap `/random`!"
            ),
            parse_mode="Markdown",
        )
        ACTIVE_SESSIONS.pop(chat_id, None)
        return

    ACTIVE_SESSIONS[chat_id]["ranked_options"] = options
    ACTIVE_SESSIONS[chat_id]["current_gate"] = "story_choice"

    # Send ranked story options with inline buttons
    header = f"📰 **Top 5 Stories on '{topic}'**\n" if topic else "📰 **Top 5 Developer Stories Selected Today**\n"
    text_lines = [header]
    buttons = []
    for idx, item in enumerate(options, start=1):
        score = item.get("score", 0.0)
        source = item.get("source", "News")
        title = item.get("title", "Untitled")
        reason = item.get("reason", "")
        text_lines.append(f"*{idx}. {title}*\n⭐ Score: `{score}` | 📡 {source}\n💡 _{reason}_\n")
        btn_label = f"Select #{idx}: {title[:35]}..."
        buttons.append([InlineKeyboardButton(btn_label, callback_data=f"select_story_{idx-1}")])

    text_lines.append("👇 **Tap a story below to generate the post and visual card:**")
    await bot.send_message(
        chat_id=chat_id,
        text="\n".join(text_lines),
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode="Markdown",
    )


async def fetch_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Manual trigger command /fetch or /run with optional topic."""
    if not update.effective_user or not update.effective_chat:
        return
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        await update.effective_chat.send_message("⛔ Unauthorized.")
        return

    topic = " ".join(context.args).strip() if context.args else None
    await trigger_pipeline_run(update.effective_chat.id, context.bot, topic=topic)


async def topic_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Searches developer news by topic: /topic [keyword] or prompts for a topic."""
    if not update.effective_user or not update.effective_chat:
        return
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        await update.effective_chat.send_message("⛔ Unauthorized.")
        return

    chat_id = update.effective_chat.id
    if context.args:
        topic = " ".join(context.args).strip()
        await trigger_pipeline_run(chat_id, context.bot, topic=topic)
    else:
        ACTIVE_SESSIONS[chat_id] = {"waiting_for": "topic_input"}
        await update.effective_message.reply_text(
            "🎯 **What topic would you like to explore?**\n\n"
            "Reply with any developer topic or keyword, for example:\n"
            "• `PostgreSQL`\n"
            "• `Docker`\n"
            "• `Rust`\n"
            "• `FastAPI`\n"
            "• `LangGraph`\n"
            "• `Vector Search`\n"
            "• `Distributed Systems`",
            parse_mode="Markdown",
        )


async def random_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Picks a random developer topic and fetches fresh stories."""
    if not update.effective_user or not update.effective_chat:
        return
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        await update.effective_chat.send_message("⛔ Unauthorized.")
        return

    chosen_topic = get_random_topic()
    await update.effective_message.reply_text(
        f"🎲 **Random Topic Chosen:** *{chosen_topic}*\nFetching fresh stories...",
        parse_mode="Markdown",
    )
    await trigger_pipeline_run(update.effective_chat.id, context.bot, topic=chosen_topic)


async def handle_story_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Callback query handler when user taps a story button."""
    query = update.callback_query
    if not query or not query.data:
        return
    await query.answer()

    user_id = update.effective_user.id if update.effective_user else 0
    if not is_authorized(user_id):
        await query.edit_message_text("⛔ Unauthorized.")
        return

    chat_id = update.effective_chat.id if update.effective_chat else 0
    session = ACTIVE_SESSIONS.get(chat_id)
    if not session or session.get("current_gate") != "story_choice":
        await query.edit_message_text("⚠️ No active story selection pending.")
        return

    idx = int(query.data.replace("select_story_", ""))
    options = session.get("ranked_options", [])
    if idx >= len(options):
        await query.edit_message_text("❌ Selected option out of range.")
        return

    chosen_story = options[idx]
    await query.edit_message_text(f"✅ Selected: *{chosen_story.get('title')}*\n\nDrafting post and rendering card image...", parse_mode="Markdown")

    app = session["app"]
    config = session["config"]
    loop = asyncio.get_running_loop()

    # 2. Resume graph with chosen story -> runs generate_draft -> humanize -> await_review
    try:
        await loop.run_in_executor(
            None,
            _run_graph_sync,
            app,
            Command(resume=chosen_story),
            config,
        )
    except Exception as e:
        logger.error("Resume failed during drafting: %s", e, exc_info=True)
        await context.bot.send_message(chat_id=chat_id, text=f"❌ Failed drafting post: `{e}`")
        return

    state_snapshot = app.get_state(config)
    if not state_snapshot.tasks or not state_snapshot.tasks[0].interrupts:
        await context.bot.send_message(chat_id=chat_id, text="⚠️ Graph did not pause at review gate.")
        return

    session["current_gate"] = "await_review"
    current_state = state_snapshot.values

    # Send review prompt with image card
    await _send_review_message(chat_id, context.bot, current_state)


async def _send_review_message(chat_id: int, bot: Any, state: dict) -> None:
    """Sends the drafted post text, attached card image, and review action buttons."""
    image_path = state.get("draft_image_path")
    image_mode = state.get("image_mode") or "card"
    post_text = state.get("humanized_post") or state.get("draft_post", "")

    # Send card image if exists
    if image_path and os.path.exists(image_path):
        caption = (
            "📊 **Technical Architecture Infographic Card**\n_3 Structured Technical Pillars + Engineering Takeaway_"
            if image_mode == "card"
            else "🎨 **16:9 AI Visual Concept**\n_Generated with OpenAI gpt-image-2.5-flare_"
        )
        with open(image_path, "rb") as photo:
            await bot.send_photo(
                chat_id=chat_id,
                photo=photo,
                caption=caption,
                parse_mode="Markdown",
            )

    keyboard = [
        [
            InlineKeyboardButton("📊 Architecture Card", callback_data="switch_img_card"),
            InlineKeyboardButton("🎨 AI Visual (GPT-Image)", callback_data="switch_img_ai"),
        ],
        [InlineKeyboardButton("🚀 Approve & Publish", callback_data="review_approve")],
        [InlineKeyboardButton("✍️ Edit Feedback / Polish", callback_data="review_edit_prompt")],
    ]

    review_msg = (
        f"📝 **LinkedIn Post Preview:**\n\n"
        f"---\n"
        f"{post_text}\n"
        f"---\n\n"
        f"👉 **Options:**\n"
        f"• Tap **Architecture Card** or **AI Visual** to toggle image style.\n"
        f"• Tap **Approve & Publish** to post live to LinkedIn.\n"
        f"• Or simply **type a message reply** here with any edit instructions (e.g. _\"Highlight the microVM boot latency\"_) to regenerate!"
    )
    await bot.send_message(
        chat_id=chat_id,
        text=review_msg,
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def handle_review_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles review button callbacks (Approve, Edit, Switch Image Style)."""
    query = update.callback_query
    if not query or not query.data:
        return
    await query.answer()

    chat_id = update.effective_chat.id if update.effective_chat else 0
    user_id = update.effective_user.id if update.effective_user else 0
    if not is_authorized(user_id):
        logger.warning("SECURITY: Unauthorized review action attempt from user_id=%s", user_id)
        await query.message.reply_text("⛔ Unauthorized.")
        return

    session = ACTIVE_SESSIONS.get(chat_id)
    if not session or session.get("current_gate") != "await_review":
        await query.message.reply_text("⚠️ No review currently awaiting action.")
        return

    action = query.data
    app = session["app"]
    config = session["config"]
    loop = asyncio.get_running_loop()

    if action in ("switch_img_card", "switch_img_ai"):
        target_mode = "card" if action == "switch_img_card" else "ai_visual"
        current_state = app.get_state(config).values
        if current_state.get("image_mode") == target_mode and os.path.exists(current_state.get("draft_image_path", "")):
            await query.message.reply_text(f"ℹ️ The **{target_mode.upper()}** style is already active.", parse_mode="Markdown")
            return

        status_msg = (
            "⏳ *Rendering Technical Architecture Card...*"
            if target_mode == "card"
            else "⏳ *Generating 16:9 AI Visual using OpenAI gpt-image-2.5-flare (this takes ~4-6s)...*"
        )
        await query.message.reply_text(status_msg, parse_mode="Markdown")

        chosen = current_state.get("chosen_story", {})
        draft_meta = current_state.get("draft_metadata", {})

        from agents import imagegen
        try:
            new_img_path = await loop.run_in_executor(
                None,
                imagegen.render,
                chosen,
                draft_meta,
                target_mode,
            )
            # Update checkpointer state with new image path and mode
            app.update_state(config, {"draft_image_path": new_img_path, "image_mode": target_mode})
            updated_state = app.get_state(config).values
            await _send_review_message(chat_id, context.bot, updated_state)
        except Exception as e:
            logger.error("Failed switching image style: %s", e, exc_info=True)
            await query.message.reply_text(f"❌ Failed to generate {target_mode} image: `{e}`")

    elif action == "review_approve":
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text("⏳ Approving and publishing to LinkedIn...")

        try:
            await loop.run_in_executor(
                None,
                _run_graph_sync,
                app,
                Command(resume={"action": "approve"}),
                config,
            )
        except Exception as e:
            logger.error("Publishing failed: %s", e, exc_info=True)
            await query.message.reply_text(f"❌ Failed to publish post: `{e}`")
            return

        final_state = app.get_state(config).values
        post_url = final_state.get("linkedin_post_url", "")
        from integrations import linkedin
        if linkedin.is_dry_run():
            success_text = (
                f"🧪 <b>[DRY-RUN] Simulation Succeeded!</b>\n\n"
                f"Your post and visual were processed and simulated safely without touching your live LinkedIn profile.\n\n"
                f"👉 <i>The link ending in <code>dryrun_...</code> is a simulated mock URL.</i>\n\n"
                f"🚀 <b>To publish to your REAL LinkedIn account:</b>\n"
                f"1. Change <code>DRY_RUN=false</code> in <code>.env</code>\n"
                f"2. Restart <code>main.py</code> in terminal"
            )
        else:
            success_text = (
                f"🎉 <b>Live Post Successfully Published to LinkedIn!</b>\n\n"
                f"🔗 <b>LinkedIn URL:</b>\n{post_url}"
            )
        try:
            await query.message.reply_text(success_text, parse_mode="HTML")
        except Exception:
            await query.message.reply_text(f"🎉 Success!\n\nLinkedIn URL:\n{post_url}")
        ACTIVE_SESSIONS.pop(chat_id, None)

    elif action == "review_edit_prompt":
        await query.message.reply_text(
            "💬 **Type your edit instructions directly in a chat message.**\n"
            "For example:\n"
            "• _'Highlight the performance benchmark numbers more.'_\n"
            "• _'Make the opening hook 1 sentence.'_\n"
            "• _'Add a question about developer adoption.'_"
        )


async def handle_user_text_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Listens for free-text replies: either a topic response or edit notes during review."""
    if not update.effective_user or not update.effective_message or not update.effective_message.text:
        return

    user_id = update.effective_user.id
    if not is_authorized(user_id):
        return

    chat_id = update.effective_chat.id if update.effective_chat else 0
    session = ACTIVE_SESSIONS.get(chat_id, {})

    # Case 1: User is replying to the /topic prompt
    if session.get("waiting_for") == "topic_input":
        topic = update.effective_message.text.strip()
        ACTIVE_SESSIONS.pop(chat_id, None)
        await trigger_pipeline_run(chat_id, context.bot, topic=topic)
        return

    # Case 2: User is providing edit feedback during review gate
    if session.get("current_gate") != "await_review":
        return

    edit_notes = update.effective_message.text.strip()
    await update.effective_message.reply_text(
        f"✍️ *Applying your feedback:* \"_{edit_notes}_\"...\nRegenerating post with humanizer...",
        parse_mode="Markdown",
    )

    app = session["app"]
    config = session["config"]
    loop = asyncio.get_running_loop()

    # Resume graph with edit request -> loops back to humanize -> hits await_review
    try:
        await loop.run_in_executor(
            None,
            _run_graph_sync,
            app,
            Command(resume={"action": "edit", "notes": edit_notes}),
            config,
        )
    except Exception as e:
        logger.error("Failed to re-humanize with edits: %s", e, exc_info=True)
        await update.effective_message.reply_text(f"❌ Error applying edits: `{e}`")
        return

    state_snapshot = app.get_state(config)
    session["current_gate"] = "await_review"
    current_state = state_snapshot.values

    # Resend updated review preview
    await _send_review_message(chat_id, context.bot, current_state)


async def global_error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Catches all unhandled exceptions and notifies the user in Telegram."""
    logger.error("Exception while handling Telegram update:", exc_info=context.error)

    err_msg = str(context.error) if context.error else "Unknown error occurred"
    tb_list = traceback.format_exception(None, context.error, context.error.__traceback__) if context.error else []
    tb_text = "".join(tb_list)
    tb_snippet = tb_text[-600:] if len(tb_text) > 600 else tb_text

    notify_text = (
        f"⚠️ **Error in Pipeline / Bot:**\n\n"
        f"**Reason:** `{err_msg}`\n\n"
        f"**Traceback:**\n```\n{tb_snippet}\n```"
    )

    chat = None
    if isinstance(update, Update) and update.effective_chat:
        chat = update.effective_chat

    if chat:
        try:
            await chat.send_message(notify_text, parse_mode="Markdown")
        except Exception:
            await chat.send_message(f"⚠️ Error: {err_msg}\n\n{tb_snippet}")
    elif get_allowed_chat_id() and context.bot:
        try:
            await context.bot.send_message(
                chat_id=get_allowed_chat_id(),
                text=notify_text,
                parse_mode="Markdown",
            )
        except Exception:
            pass


def build_telegram_app(
    post_init: Any = None,
    post_shutdown: Any = None,
) -> Application:
    """Builds and configures the python-telegram-bot application."""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN environment variable is not configured.")

    builder = Application.builder().token(token)
    if post_init:
        builder.post_init(post_init)
    if post_shutdown:
        builder.post_shutdown(post_shutdown)

    application = builder.build()

    # Register error handler
    application.add_error_handler(global_error_handler)

    # Command handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("topic", topic_command))
    application.add_handler(CommandHandler("random", random_command))
    application.add_handler(CommandHandler("fetch", fetch_command))
    application.add_handler(CommandHandler("run", fetch_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("help", start_command))

    # Inline query callbacks
    application.add_handler(CallbackQueryHandler(handle_story_selection, pattern=r"^select_story_\d+$"))
    application.add_handler(CallbackQueryHandler(handle_review_action, pattern=r"^(review_.*|switch_img_.*)$"))

    # Free text message handler for topic input or edit loop
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_user_text_reply))

    return application
