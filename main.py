import logging
import os

from anthropic import AsyncAnthropic, APIStatusError
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
# httpx logs each request URL, which contains the Telegram bot token in plaintext.
# Raise it to WARNING to avoid leaking the token and to cut log spam.
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger("claude-telegram-bot")

# ---------------------------------------------------------------------------
# Configuration (all overridable via environment variables)
# ---------------------------------------------------------------------------
MODEL_CHAIN = [
    m.strip()
    for m in os.getenv(
        "ANTHROPIC_MODEL",
        # Try in order; the first model your account/API still supports wins.
        "claude-sonnet-4-5,claude-sonnet-4-6,claude-haiku-4-5,claude-3-5-sonnet-latest",
    ).split(",")
    if m.strip()
]
MAX_TOKENS = int(os.getenv("ANTHROPIC_MAX_TOKENS", "2048"))
MAX_HISTORY_MESSAGES = int(os.getenv("MAX_HISTORY_MESSAGES", "20"))
SYSTEM_PROMPT = os.getenv(
    "SYSTEM_PROMPT",
    "You are a helpful assistant running inside Telegram. "
    "Keep replies concise and use plain text (no markdown tables).",
)

anthropic_client = AsyncAnthropic()  # reads ANTHROPIC_API_KEY from the environment

# Store conversation history per user: user_id -> [{role, content}, ...]
user_conversations: dict[int, list[dict]] = {}
# Remember which model worked, so we do not re-probe every message.
_resolved_model: str | None = None


async def ask_claude(messages: list[dict]) -> tuple[str, str]:
    """Call Claude, falling back through MODEL_CHAIN if a model is unavailable.

    Returns (model_used, reply_text).
    """
    global _resolved_model
    candidates = [_resolved_model] if _resolved_model else MODEL_CHAIN
    candidates += [m for m in MODEL_CHAIN if m != _resolved_model]

    last_error: Exception | None = None
    for model in candidates:
        try:
            response = await anthropic_client.messages.create(
                model=model,
                max_tokens=MAX_TOKENS,
                system=SYSTEM_PROMPT,
                messages=messages,
            )
        except APIStatusError as exc:
            last_error = exc
            # 404 = model retired/not found; 400 may also mention unknown model.
            retriable = exc.status_code == 404 or (
                exc.status_code == 400 and "model" in str(exc).lower()
            )
            if retriable:
                logger.warning(
                    "Model %s unavailable (HTTP %s), trying next.", model, exc.status_code
                )
                if _resolved_model == model:
                    _resolved_model = None
                continue
            raise
        _resolved_model = model
        text = "".join(
            block.text for block in response.content if getattr(block, "type", "") == "text"
        ).strip()
        return model, text or "(Claude returned an empty response)"
    raise RuntimeError(f"No configured model worked: {MODEL_CHAIN}") from last_error


def history_for_api(user_id: int) -> list[dict]:
    """Return history trimmed to a window that starts with a user turn."""
    history = list(user_conversations.get(user_id, []))
    if len(history) > MAX_HISTORY_MESSAGES:
        history = history[-MAX_HISTORY_MESSAGES:]
        # Anthropic requires the first message to be from the user.
        while history and history[0]["role"] != "user":
            history.pop(0)
    return history


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_conversations[update.effective_user.id] = []
    await update.message.reply_text(
        "👋 Hello! I'm a Claude-powered assistant. Send me any message and I'll help you!\n\n"
        "Commands: /clear wipes the conversation, /help shows help."
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "I'm a Telegram bot powered by Claude AI.\n\n"
        "/start - Restart the chat\n"
        "/clear - Clear conversation history\n"
        "/help - Show this message\n\n"
        "Just send me any text message and I'll respond!"
    )


async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_conversations[update.effective_user.id] = []
    await update.message.reply_text("✅ Conversation history cleared!")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    user_message = (update.message.text or "").strip()
    if not user_message:
        return

    user_conversations.setdefault(user_id, []).append({"role": "user", "content": user_message})

    try:
        await update.message.chat.send_action(ChatAction.TYPING)
        model, reply = await ask_claude(history_for_api(user_id))
        user_conversations[user_id].append({"role": "assistant", "content": reply})

        # Telegram caps messages at 4096 chars; send in chunks if needed.
        for i in range(0, len(reply), 4096):
            await update.message.reply_text(reply[i : i + 4096])
        logger.info("Answered user %s with model %s (%d chars).", user_id, model, len(reply))
    except Exception as exc:  # surface failures instead of a silent generic ❌
        logger.exception("Error processing message")
        user_conversations[user_id].pop()  # roll back the unmatched user turn
        detail = str(exc)
        if len(detail) > 300:
            detail = detail[:300] + "…"
        await update.message.reply_text(f"❌ Sorry, something went wrong:\n{detail}")


def main() -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise SystemExit("TELEGRAM_BOT_TOKEN environment variable not set")
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise SystemExit("ANTHROPIC_API_KEY environment variable not set")

    application = Application.builder().token(token).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("clear", clear_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Starting Telegram Claude bot (model chain: %s)", MODEL_CHAIN)
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
