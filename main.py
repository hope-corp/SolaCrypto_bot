import os
import logging
import asyncio
from flask import Flask, jsonify
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
)

# Load environment variables from .env file if available
load_dotenv()

# Configure logging to output standard text logs only
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
    await update.message.reply_text("Bot is running and operational!")

async def log_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Telegram /log command handler to output text-based logs."""
    user_id = update.effective_user.id
    logger.info("Log requested by user_id: %s", user_id)
    await update.message.reply_text("Log entry recorded successfully.")

def build_telegram_application():
    """Validates the bot token and builds the Telegram Application instance."""
    if not BOT_TOKEN or BOT_TOKEN.strip() == "":
        logger.critical(
            "FATAL: BOT_TOKEN is missing or empty. Ensure TELEGRAM_BOT_TOKEN "
            "environment variable is properly configured in your container."
        )
        raise ValueError(
            "Invalid or missing TELEGRAM_BOT_TOKEN. "
            "Please obtain a valid token from https://t.me/BotFather"
        )
    
    logger.info("Initializing Telegram Bot Application...")
    application = ApplicationBuilder().token(BOT_TOKEN).build()
    
    # Register handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("log", log_command))
    
    return application

async def run_bot_and_flask():
    """Runs the Telegram Bot polling alongside the Flask app."""
    telegram_app = build_telegram_application()
    
    # Initialize and start Telegram bot in polling mode
    await telegram_app.initialize()
    await telegram_app.start()
    await telegram_app.updater.start_polling()
    logger.info("Telegram Bot polling started.")

    # Run Flask development server (or use WSGI server like gunicorn in production)
    from werkzeug.serving import run_simple
    loop = asyncio.get_running_loop()
    
    logger.info("Starting Flask HTTP server on 0.0.0.0:8080...")
    await loop.run_in_executor(
        None, 
        lambda: run_simple("0.0.0.0", 8080, app, use_reloader=False)
    )

if __name__ == "__main__":
    try:
        asyncio.run(run_bot_and_flask())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Application stopped gracefully.")
    except Exception as e:
        logger.error("Unhandled exception during execution: %s", e, exc_info=True)
