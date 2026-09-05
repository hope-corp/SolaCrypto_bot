import os
import logging
import threading
import asyncio
from flask import Flask, jsonify
import requests

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
# Optional: Set your Telegram user/chat ID directly, or send /start to auto-subscribe
MY_USER_ID = os.getenv("MY_TELEGRAM_USER_ID")

# Set of active recipient chat IDs
SUBSCRIBED_USERS = set()
if MY_USER_ID:
    SUBSCRIBED_USERS.add(int(MY_USER_ID))

# Default Token Contract to monitor (e.g., SOL, ETH, or any DEX token address)
# Example: Solana WSOL contract address
DEFAULT_TOKEN_ADDRESS = os.getenv("TOKEN_ADDRESS", "So11111111111111111111111111111111111111112")

# Initialize Flask App for Container Health Checks
app = Flask(__name__)

@app.route("/")
def health_check():
    """Health check endpoint for container platform."""
    return jsonify({
        "status": "healthy",
        "service": "Telegram-Token-Tracker",
        "subscribers": len(SUBSCRIBED_USERS)
    }), 200

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Registers your personal chat ID to receive live direct token updates."""
    user = update.effective_user
    chat_id = update.effective_chat.id
    
    SUBSCRIBED_USERS.add(chat_id)
    logger.info("Token alert subscription activated for user: %s (ID: %s)", user.first_name, chat_id)
    
    await update.message.reply_text(
        f"🚀 **Live Token Alerts Activated**\n\n"
        f"Hello {user.first_name}! I will text you live price feeds, liquidity, and volume metrics directly in this chat.\n\n"
        f"• Use `/track <contract_address>` to change the token\n"
        f"• Use `/stop` to pause live alerts"
    )

async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Stops sending direct token messages."""
    chat_id = update.effective_chat.id
    SUBSCRIBED_USERS.discard(chat_id)
    
    logger.info("Token feed paused for chat ID: %s", chat_id)
    await update.message.reply_text("⏸️ Live token updates paused. Send /start anytime to resume.")

async def track_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Allows updating the tracked token address on the fly."""
    global DEFAULT_TOKEN_ADDRESS
    if context.args:
        DEFAULT_TOKEN_ADDRESS = context.args[0].strip()
        await update.message.reply_text(f"🎯 Now tracking token address: `{DEFAULT_TOKEN_ADDRESS}`", parse_mode="Markdown")
    else:
        await update.message.reply_text("Please provide a contract address. Example: `/track <0x123...>`", parse_mode="Markdown")

def fetch_dex_token_data(token_address: str) -> str:
    """
    Fetches real-time market data for the target token from DexScreener.
    """
    url = f"https://api.dexscreener.com/latest/dex/tokens/{token_address}"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            pairs = data.get("pairs")
            if not pairs:
                return f"⚠️ No active liquidity pairs found for contract: `{token_address}`"

            # Primary pair metrics
            primary_pair = pairs[0]
            base_token = primary_pair.get("baseToken", {}).get("symbol", "TOKEN")
            price_usd = primary_pair.get("priceUsd", "N/A")
            liquidity = primary_pair.get("liquidity", {}).get("usd", 0)
            mcap = primary_pair.get("fdv", 0)
            
            # Price changes
            h1_change = primary_pair.get("priceChange", {}).get("h1", 0)
            h24_change = primary_pair.get("priceChange", {}).get("h24", 0)
            
            # Transactions in last 24h
            buys = primary_pair.get("txns", {}).get("h24", {}).get("buys", 0)
            sells = primary_pair.get("txns", {}).get("h24", {}).get("sells", 0)

            # Format the live report
            report = (
                f"📈 **LIVE TOKEN UPDATE** | **${base_token}**\n\n"
                f"💵 **Price:** `${price_usd}`\n"
                f"📊 **1H Change:** `{h1_change}%`\n"
                f"📊 **24H Change:** `{h24_change}%`\n"
                f"💧 **Liquidity:** `${liquidity:,.0f}`\n"
                f"🧢 **Market Cap (FDV):** `${mcap:,.0f}`\n"
                f"🔄 **24H Txns:** {buys} Buys / {sells} Sells\n\n"
                f"🔗 [View on DexScreener]({primary_pair.get('url', '')})"
            )
            return report
        else:
            return f"⚠️ Failed to pull market data (Status Code: {response.status_code})"
    except Exception as e:
        logger.error("Error fetching token data: %s", e)
        return "⚠️ Error fetching live market metrics."

async def live_token_broadcaster(application):
    """Background loop that fetches live token metrics and texts them directly to you."""
    logger.info("Live token update worker loop initiated.")
    while True:
        try:
            # Refresh rate in seconds (e.g., send update every 30 seconds)
            await asyncio.sleep(30)

            if not SUBSCRIBED_USERS:
                continue

            # Get fresh market update
            message_text = fetch_dex_token_data(DEFAULT_TOKEN_ADDRESS)

            # Push live update directly to your Telegram chat
            for user_chat_id in list(SUBSCRIBED_USERS):
                try:
                    await application.bot.send_message(
                        chat_id=user_chat_id,
                        text=message_text,
                        parse_mode="Markdown",
                        disable_web_page_preview=True
                    )
                    logger.info("Live token metrics sent directly to user ID: %s", user_chat_id)
                except Exception as send_error:
                    logger.error("Failed to send token update to %s: %s", user_chat_id, send_error)

        except Exception as e:
            logger.error("Error in live token broadcaster: %s", e, exc_info=True)
            await asyncio.sleep(5)

def build_telegram_application():
    """Validates the bot token and registers command handlers."""
    if not BOT_TOKEN or BOT_TOKEN.strip() == "":
        logger.critical("FATAL: BOT_TOKEN environment variable is missing.")
        raise ValueError("Invalid or missing TELEGRAM_BOT_TOKEN.")
    
    application = ApplicationBuilder().token(BOT_TOKEN).build()
    
    # Register command handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("stop", stop_command))
    application.add_handler(CommandHandler("track", track_command))
    
    return application

def start_telegram_bot():
    """Runs the Telegram Bot event loop in a dedicated daemon thread."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    application = build_telegram_application()
    
    # Run the live token broadcast background task
    loop.create_task(live_token_broadcaster(application))
    
    logger.info("Starting Telegram Bot polling for direct token messages...")
    application.run_polling(stop_signals=None)

if __name__ == "__main__":
    try:
        # Start Telegram bot in background thread
        bot_thread = threading.Thread(target=start_telegram_bot, daemon=True)
        bot_thread.start()
        
        # Start Flask web server for container environment
        logger.info("Starting Flask HTTP server on 0.0.0.0:8080...")
        app.run(host="0.0.0.0", port=8080, debug=False, use_reloader=False)
        
    except (KeyboardInterrupt, SystemExit):
        logger.info("Application stopped gracefully.")
    except Exception as e:
        logger.error("Unhandled exception during execution: %s", e, exc_info=True)
