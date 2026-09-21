import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from anthropic import Anthropic

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Initialize Anthropic client
anthropic_client = Anthropic()

# Store conversation history per user
user_conversations = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Start the bot and send a greeting."""
    user_id = update.effective_user.id
    user_conversations[user_id] = []
    await update.message.reply_text(
        "👋 Hello! I'm Claude, your AI assistant. Send me any message and I'll help you!"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when /help is issued."""
    help_text = """
    I'm a Telegram bot powered by Claude AI.
    
    Commands:
    /start - Start chatting
    /clear - Clear conversation history
    /help - Show this message
    
    Just send me any message and I'll respond!
    """
    await update.message.reply_text(help_text)

async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Clear conversation history for the user."""
    user_id = update.effective_user.id
    user_conversations[user_id] = []
    await update.message.reply_text("✅ Conversation history cleared!")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle incoming messages and respond with Claude."""
    user_id = update.effective_user.id
    user_message = update.message.text
    
    # Initialize conversation if needed
    if user_id not in user_conversations:
        user_conversations[user_id] = []
    
    # Add user message to history
    user_conversations[user_id].append({
        "role": "user",
        "content": user_message
    })
    
    try:
        # Show typing indicator
        await update.message.chat.send_action("typing")
        
        # Get response from Claude
        response = anthropic_client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=1024,
            messages=user_conversations[user_id]
        )
        
        assistant_message = response.content[0].text
        
        # Add assistant message to history
        user_conversations[user_id].append({
            "role": "assistant",
            "content": assistant_message
        })
        
        # Keep only last 10 messages per user to save memory
        if len(user_conversations[user_id]) > 20:
            user_conversations[user_id] = user_conversations[user_id][-20:]
        
        # Send response (split if too long)
        if len(assistant_message) <= 4096:
            await update.message.reply_text(assistant_message)
        else:
            # Split long messages
            for i in range(0, len(assistant_message), 4096):
                await update.message.reply_text(assistant_message[i:i+4096])
    
    except Exception as e:
        logger.error(f"Error processing message: {e}")
        await update.message.reply_text("❌ Sorry, I encountered an error. Please try again.")

def main() -> None:
    """Start the bot."""
    # Get token from environment
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN environment variable not set")
    
    # Create the Application
    application = Application.builder().token(token).build()
    
    # Register handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("clear", clear_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Start the bot
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()

