#!/usr/bin/env python3
import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import anthropic

# Set up logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Initialize Claude client
claude_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /start is issued."""
    await update.message.reply_text(
        "👋 Hello! I'm a Telegram bot powered by Claude AI.\n\n"
        "Send me any message and I'll respond with Claude's insights.\n\n"
        "Commands:\n"
        "/start - Show this message\n"
        "/help - Get help"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /help is issued."""
    await update.message.reply_text(
        "I can help you with:\n"
        "• Questions and answers\n"
        "• Writing and editing\n"
        "• Coding help\n"
        "• Creative tasks\n"
        "• And much more!\n\n"
        "Just send me a message and I'll respond."
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle incoming messages and respond with Claude."""
    user_message = update.message.text
    user_id = update.message.from_user.id
    
    logger.info(f"Message from {user_id}: {user_message}")
    
    # Show typing indicator
    await update.message.chat.send_action("typing")
    
    try:
        # Get response from Claude
        message = claude_client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=1024,
            messages=[
                {"role": "user", "content": user_message}
            ]
        )
        
        response_text = message.content[0].text
        
        # Split long messages (Telegram max is 4096 chars)
        if len(response_text) > 4096:
            for i in range(0, len(response_text), 4096):
                await update.message.reply_text(response_text[i:i+4096])
        else:
            await update.message.reply_text(response_text)
            
    except Exception as e:
        logger.error(f"Error getting Claude response: {e}")
        await update.message.reply_text(
            f"Sorry, I encountered an error: {str(e)}\n\n"
            "Please try again later."
        )

def main() -> None:
    """Start the bot."""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN environment variable not set")
    
    # Create the Application
    application = Application.builder().token(token).build()

    # on different commands - answer in Telegram
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))

    # on non command i.e message - echo the message on Telegram
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Run the bot
    logger.info("Starting bot...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()

