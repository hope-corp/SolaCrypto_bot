import os
import logging
import threading
import asyncio
from flask import Flask, jsonify

# Safely attempt to import python-dotenv
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
)

# Configure text-based logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Retrieve Telegram Bot Token from environment
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("BOT_TOKEN")

# Initialize Flask App
app = Flask(__name__)

@app.route("/")
def health_check():
    """Health check endpoint for Flask app."""
    return jsonify({"status": "healthy", "service": "Flask-Telegram-Bot"}), 200

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Telegram /start command handler."""
    logger.info("Received /start command from user_id: %s", update.effective_user.id)
    await update.message.reply_text("Bot is active and receiving live updates!")

async def log_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Telegram /log command handler to output text-based logs."""
    user_id = update.effective_user.id
    logger.info("Live log requested by user_id: %s", user_id)
    await update.message.reply_text(f"Live log update captured for user: {user_id}")

def build_telegram_application():
    """Validates the bot token and builds the Telegram Application instance."""
    if not BOT_TOKEN or BOT_TOKEN.strip() == "":
        logger.critical(
            "FATAL: BOT_TOKEN is missing or empty. Ensure TELEGRAM_BOT_TOKEN "
            "environment variable is properly set in your container."
        )
        raise ValueError(
            "Invalid or missing TELEGRAM_BOT_TOKEN. "
            "Please pass a valid token via environment variables."
        )
    
    logger.info("Initializing Telegram Bot Application...")
    application = ApplicationBuilder().token(BOT_TOKEN).build()
    
    # Register command handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("log", log_command))
    
    return application

def start_telegram_bot():
    """Runs the Telegram Bot event loop in a dedicated thread."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    telegram_app = build_telegram_application()
    logger.info("Starting Telegram Bot polling loop...")
    
    # run_polling handles its own loop execution and blocking safely
    telegram_app.run_polling(stop_signals=None)

if __name__ == "__main__":
    try:
        # Start Telegram Bot in a separate background thread so it doesn't block Flask
        bot_thread = threading.Thread(target=start_telegram_bot, daemon=True)
        bot_thread.start()
        
        # Start Flask Web Server on the main thread
        logger.info("Starting Flask HTTP server on 0.0.0.0:8080...")
        app.run(host="0.0.0.0", port=8080, debug=False, use_reloader=False)
        
    except (KeyboardInterrupt, SystemExit):
        logger.info("Application stopped gracefully.")
    except Exception as e:
        logger.error("Unhandled exception during execution: %s", e, exc_info=True)
