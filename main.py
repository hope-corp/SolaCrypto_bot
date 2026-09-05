import os
import logging
import threading
import asyncio
import datetime
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

# Environment Configuration
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("BOT_TOKEN")

# Optional: Put your personal Telegram User ID here (e.g. 123456789)
# You can get your ID from @userinfobot on Telegram
MY_USER_ID = os.getenv("MY_TELEGRAM_USER_ID")

# Set of active recipient chat IDs
SUBSCRIBED_USERS = set()
if MY_USER_ID:
    SUBSCRIBED_USERS.add(int(MY_USER_ID))

# Initialize Flask App
app = Flask(__name__)

@app.route("/")
def health_check():
    """Health check endpoint for container platform."""
    return jsonify({
        "status": "healthy",
        "service": "Direct-Telegram-Broadcaster",
        "active_subscribers": len(SUBSCRIBED_USERS)
    }), 200

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Registers your personal chat ID to receive live direct messages."""
    user = update.effective_user
    chat_id = update.effective_chat.id
    
    SUBSCRIBED_USERS.add(chat_id)
    logger.info("Direct message feed activated for user: %s (ID: %s)", user.first_name, chat_id)
    
    await update.message.reply_text(
        f"👋 Hello {user.first_name}!\n\n"
        "✅ Live updates activated. I will text you directly right here whenever new updates come in."
    )

async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Stops sending direct messages to your chat."""
    chat_id = update.effective_chat.id
    SUBSCRIBED_USERS.discard(chat_id)
    
    logger.info("Direct message feed paused for chat ID: %s", chat_id)
    await update.message.reply_text("⏸️ Live updates paused. Send /start anytime to resume.")

async def fetch_live_update() -> str:
    """
    Fetch or generate live data to send.
    Replace this function logic with your real API call or log reader.
    """
    current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return f"📩 **Direct Update** [{current_time}]\nEverything is running smoothly on your server."

async def direct_message_worker(application):
    """Background task that sends live messages directly to your private chat."""
    logger.info("Direct message background worker started.")
    while True:
        try:
            # Interval between live updates in seconds (e.g., 60 seconds)
            await asyncio.sleep(60)

            if not SUBSCRIBED_USERS:
                continue

            # Get latest live update text
            update_text = await fetch_live_update()

            # Send directly to your personal chat
            for user_chat_id in list(SUBSCRIBED_USERS):
                try:
                    await application.bot.send_message(
                        chat_id=user_chat_id,
                        text=update_text,
                        parse_mode="Markdown"
                    )
                    logger.info("Sent direct update to user ID: %s", user_chat_id)
                except Exception as send_error:
                    logger.error("Failed to send direct message to %s: %s", user_chat_id, send_error)

        except Exception as e:
            logger.error("Error in direct message worker: %s", e, exc_info=True)
            await asyncio.sleep(5)

def build_telegram_application():
    """Validates the bot token and builds the Telegram Application instance."""
    if not BOT_TOKEN or BOT_TOKEN.strip() == "":
        logger.critical("FATAL: BOT_TOKEN environment variable is missing.")
        raise ValueError("Invalid or missing TELEGRAM_BOT_TOKEN.")
    
    application = ApplicationBuilder().token(BOT_TOKEN).build()
    
    # Register command handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("stop", stop_command))
    
    return application

def start_telegram_bot():
    """Runs the Telegram Bot and background loop in a dedicated thread."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    application = build_telegram_application()
    
    # Schedule the live direct message background task
    loop.create_task(direct_message_worker(application))
    
    logger.info("Starting Telegram Bot polling for direct messages...")
    application.run_polling(stop_signals=None)

if __name__ == "__main__":
    try:
        # Start Telegram Bot in background thread
        bot_thread = threading.Thread(target=start_telegram_bot, daemon=True)
        bot_thread.start()
        
        # Start Flask Web Server
        logger.info("Starting Flask HTTP server on 0.0.0.0:8080...")
        app.run(host="0.0.0.0", port=8080, debug=False, use_reloader=False)
        
    except (KeyboardInterrupt, SystemExit):
        logger.info("Application stopped gracefully.")
    except Exception as e:
        logger.error("Unhandled exception during execution: %s", e, exc_info=True)
