import os
import logging
import threading
import asyncio
import json
import urllib.request
import urllib.error
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

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Environment Configuration
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("BOT_TOKEN")
MY_USER_ID = os.getenv("MY_TELEGRAM_USER_ID")

# Set of active recipient chat IDs
SUBSCRIBED_USERS = set()
if MY_USER_ID:
    SUBSCRIBED_USERS.add(int(MY_USER_ID))

# Prevent duplicate alerts
SEEN_TOKENS = set()

# Initialize Flask App
app = Flask(__name__)

@app.route("/")
def health_check():
    """Health check endpoint for container environment."""
    return jsonify({
        "status": "healthy",
        "service": "Auto-Safety-Rater-Bot",
        "subscribers": len(SUBSCRIBED_USERS)
    }), 200

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Subscribe user to automated token safety analysis alerts."""
    user = update.effective_user
    chat_id = update.effective_chat.id
    
    SUBSCRIBED_USERS.add(chat_id)
    logger.info("Automated safety analyzer subscribed by user: %s (ID: %s)", user.first_name, chat_id)
    
    await update.message.reply_text(
        f"🤖 **Automated Safety Analyzer Active**\n\n"
        f"Hello {user.first_name}! I will continuously scan new tokens, perform contract & liquidity safety checks, "
        f"calculate a **Safety Rating %**, and send you direct alerts.\n\n"
        f"• Send `/check <contract_address>` to analyze any token manually.\n"
        f"• Send `/stop` to pause alerts.",
        parse_mode="Markdown"
    )

async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Stop alerts."""
    chat_id = update.effective_chat.id
    SUBSCRIBED_USERS.discard(chat_id)
    logger.info("Analyzer paused for chat ID: %s", chat_id)
    await update.message.reply_text("⏸️ Automated safety alerts paused. Send /start anytime to resume.")

async def check_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Allows manual check of any token address."""
    if not context.args:
        await update.message.reply_text("Please provide a token contract address. Usage: `/check <address>`", parse_mode="Markdown")
        return
    
    token_address = context.args[0].strip()
    await update.message.reply_text(f"🔍 Analyzing token address `{token_address}`...", parse_mode="Markdown")
    
    loop = asyncio.get_running_loop()
    report = await loop.run_in_executor(None, analyze_token_safety, token_address, "unknown")
    
    if report:
        await update.message.reply_text(report, parse_mode="Markdown", disable_web_page_preview=True)
    else:
        await update.message.reply_text("⚠️ Could not retrieve pair data or liquidity metrics for this contract.")

def query_rugcheck_solana(token_address: str) -> dict:
    """
    Queries RugCheck API for Solana tokens to check mint authority, freeze authority, and risk score.
    """
    url = f"https://api.rugcheck.xyz/v1/tokens/{token_address}/report/summary"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    
    try:
        with urllib.request.urlopen(req, timeout=8) as response:
            if response.status == 200:
                data = json.loads(response.read().decode("utf-8"))
                return data
    except Exception:
        pass
    return {}

def analyze_token_safety(token_address: str, chain_id: str) -> str:
    """
    Combines market data and contract security checks to build a safety score rating.
    """
    # 1. Fetch DexScreener market data
    pair_url = f"https://api.dexscreener.com/latest/dex/tokens/{token_address}"
    req = urllib.request.Request(pair_url, headers={"User-Agent": "Mozilla/5.0"})
    
    try:
        with urllib.request.urlopen(req, timeout=10) as res:
            if res.status != 200:
                return ""
            pair_data = json.loads(res.read().decode("utf-8"))
            pairs = pair_data.get("pairs")
            if not pairs:
                return ""
            
            primary_pair = pairs[0]
            base_token = primary_pair.get("baseToken", {}).get("symbol", "TOKEN")
            price_usd = primary_pair.get("priceUsd", "N/A")
            liquidity = primary_pair.get("liquidity", {}).get("usd", 0)
            volume_24h = primary_pair.get("volume", {}).get("h24", 0)
            fdv = primary_pair.get("fdv", 0)
            buys_24h = primary_pair.get("txns", {}).get("h24", {}).get("buys", 0)
            sells_24h = primary_pair.get("txns", {}).get("h24", {}).get("sells", 0)
            dex_url = primary_pair.get("url", "")
            chain = primary_pair.get("chainId", chain_id)

    except Exception as e:
        logger.error("Error pulling market data for %s: %s", token_address, e)
        return ""

    # 2. Automated Safety & Risk Scoring Matrix (Starts at 100 Base)
    score = 100
    risk_flags = []
    passed_checks = []

    # Liquidity depth check
    if liquidity >= 100000:
        passed_checks.append("✅ Strong Liquidity ($100k+)")
    elif liquidity >= 25000:
        score -= 15
        passed_checks.append("⚠️ Moderate Liquidity ($25k-$100k)")
    else:
        score -= 40
        risk_flags.append("🚨 Low Liquidity (Under $25k)")

    # Volume to FDV ratio check
    if volume_24h >= 10000:
        passed_checks.append("✅ Active Trading Volume")
    else:
        score -= 20
        risk_flags.append("⚠️ Low 24H Volume")

    # Buy/Sell transaction balance check
    total_txns = buys_24h + sells_24h
    if total_txns > 50:
        if sells_24h == 0:
            score -= 50
            risk_flags.append("⛔ Honeypot Warning (0 Sells Detected)")
        else:
            buy_ratio = buys_24h / total_txns
            if buy_ratio > 0.95:
                score -= 30
                risk_flags.append("⚠️ Suspicious Buy-Only Volume Ratio")
            else:
                passed_checks.append("✅ Healthy Buy/Sell Transaction Ratio")

    # Solana RugCheck integration
    if chain.lower() == "solana":
        rug_data = query_rugcheck_solana(token_address)
        if rug_data:
            # Check Mint Authority
            token_meta = rug_data.get("token", {})
            mint_auth = token_meta.get("mintAuthority")
            freeze_auth = token_meta.get("freezeAuthority")
            
            if mint_auth is None:
                passed_checks.append("✅ Mint Authority Revoked")
            else:
                score -= 30
                risk_flags.append("🚨 Mint Authority Still Active")

            if freeze_auth is None:
                passed_checks.append("✅ Freeze Authority Revoked")
            else:
                score -= 30
                risk_flags.append("🚨 Freeze Authority Still Active")

            # Score adjustments from RugCheck normalized rating
            rug_score = rug_data.get("score_normalised", 0)
            if rug_score > 40:
                score -= 25
                risk_flags.append("🚨 High Contract Risk Score (RugCheck)")

    # Bound final rating between 0% and 99%
    final_rating = max(0, min(99, score))

    # Format Telegram Report
    checks_formatted = "\n".join(passed_checks) if passed_checks else "None"
    risks_formatted = "\n".join(risk_flags) if risk_flags else "None Detected"

    rating_emoji = "🟢" if final_rating >= 75 else "🟡" if final_rating >= 45 else "🔴"

    report = (
        f"{rating_emoji} **AUTOMATED TOKEN SAFETY REPORT** | **${base_token}**\n\n"
        f"🛡️ **Safety Rating:** `{final_rating}%`\n"
        f"💵 **Price:** `${price_usd}` | 💧 **Liquidity:** `${liquidity:,.0f}`\n"
        f"📊 **24H Vol:** `${volume_24h:,.0f}` | 🧢 **FDV:** `${fdv:,.0f}`\n"
        f"🌐 **Chain:** `{chain}`\n\n"
        f"**Passed Safety Checks:**\n{checks_formatted}\n\n"
        f"**Identified Red Flags:**\n{risks_formatted}\n\n"
        f"📝 **Address:** `{token_address}`\n"
        f"🔗 [View Pair on DexScreener]({dex_url})"
    )

    return report

def scan_latest_tokens():
    """Fetches new candidates and filters for direct alerting."""
    url = "https://api.dexscreener.com/token-profiles/latest/v1"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    alerts = []
    
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            if response.status == 200:
                profiles = json.loads(response.read().decode("utf-8"))
                
                for profile in profiles[:10]:
                    token_address = profile.get("tokenAddress")
                    chain_id = profile.get("chainId", "unknown")
                    
                    if not token_address or token_address in SEEN_TOKENS:
                        continue
                        
                    SEEN_TOKENS.add(token_address)
                    report = analyze_token_safety(token_address, chain_id)
                    if report:
                        alerts.append(report)
    except Exception as e:
        logger.error("Error scanning latest tokens: %s", e)
        
    return alerts

async def automated_safety_worker(application):
    """Background loop that continuously runs safety evaluations and alerts you."""
    logger.info("Automated safety evaluation worker initialized.")
    while True:
        try:
            await asyncio.sleep(60)

            if not SUBSCRIBED_USERS:
                continue

            loop = asyncio.get_running_loop()
            new_alerts = await loop.run_in_executor(None, scan_latest_tokens)

            for alert_text in new_alerts:
                for user_chat_id in list(SUBSCRIBED_USERS):
                    try:
                        await application.bot.send_message(
                            chat_id=user_chat_id,
                            text=alert_text,
                            parse_mode="Markdown",
                            disable_web_page_preview=True
                        )
                        logger.info("Sent safety report to user ID: %s", user_chat_id)
                    except Exception as send_error:
                        logger.error("Failed to send safety report to %s: %s", user_chat_id, send_error)

        except Exception as e:
            logger.error("Error in automated safety worker: %s", e, exc_info=True)
            await asyncio.sleep(5)

def build_telegram_application():
    """Builds application and adds handlers."""
    if not BOT_TOKEN or BOT_TOKEN.strip() == "":
        logger.critical("FATAL: BOT_TOKEN environment variable is missing.")
        raise ValueError("Invalid or missing TELEGRAM_BOT_TOKEN.")
    
    application = ApplicationBuilder().token(BOT_TOKEN).build()
    
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("stop", stop_command))
    application.add_handler(CommandHandler("check", check_command))
    
    return application

def start_telegram_bot():
    """Runs the Telegram bot event loop in a background thread."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    application = build_telegram_application()
    loop.create_task(automated_safety_worker(application))
    
    logger.info("Starting Telegram Bot polling for direct safety reports...")
    application.run_polling(stop_signals=None)

if __name__ == "__main__":
    try:
        bot_thread = threading.Thread(target=start_telegram_bot, daemon=True)
        bot_thread.start()
        
        logger.info("Starting Flask HTTP server on 0.0.0.0:8080...")
        app.run(host="0.0.0.0", port=8080, debug=False, use_reloader=False)
        
    except (KeyboardInterrupt, SystemExit):
        logger.info("Application stopped gracefully.")
    except Exception as e:
        logger.error("Unhandled exception during execution: %s", e, exc_info=True)
