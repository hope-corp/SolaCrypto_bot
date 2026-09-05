import os
import threading
import logging
import requests
from flask import Flask
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# --- 1. HEALTH CHECK WEB SERVER (For Cloud Hosts) ---
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is active and running!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

# --- 2. BOT LOGIC ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

BOT_TOKEN = os.environ.get("BOT_TOKEN")

async def analyze_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    contract_address = update.message.text.strip()
    if len(contract_address) < 30:
        await update.message.reply_text("Please send a valid Solana Contract Address (CA).")
        return

    await update.message.reply_text("🔎 Fetching all DEXScreener token attributes...")
    api_url = f"https://api.dexscreener.com/latest/dex/tokens/{contract_address}"
    
    try:
        response = requests.get(api_url, timeout=10)
        data = response.json()
        pairs = data.get('pairs')
        if not pairs:
            await update.message.reply_text("❌ Token not found on DEXScreener.")
            return

        pair = pairs[0]

        # Extracting variables
        chain_id = pair.get('chainId', 'N/A')
        dex_id = pair.get('dexId', 'N/A')
        pair_url = pair.get('url', 'N/A')
        pair_address = pair.get('pairAddress', 'N/A')

        base_token = pair.get('baseToken', {})
        base_address = base_token.get('address', 'N/A')
        base_name = base_token.get('name', 'N/A')
        base_symbol = base_token.get('symbol', 'N/A')

        quote_token = pair.get('quoteToken', {})
        quote_address = quote_token.get('address', 'N/A')
        quote_name = quote_token.get('name', 'N/A')
        quote_symbol = quote_token.get('symbol', 'N/A')

        price_native = pair.get('priceNative', '0')
        price_usd = pair.get('priceUsd', '0')

        txns = pair.get('txns', {})
        txns_m5_buys = txns.get('m5', {}).get('buys', 0)
        txns_m5_sells = txns.get('m5', {}).get('sells', 0)
        txns_h1_buys = txns.get('h1', {}).get('buys', 0)
        txns_h1_sells = txns.get('h1', {}).get('sells', 0)
        txns_h6_buys = txns.get('h6', {}).get('buys', 0)
        txns_h6_sells = txns.get('h6', {}).get('sells', 0)
        txns_h24_buys = txns.get('h24', {}).get('buys', 0)
        txns_h24_sells = txns.get('h24', {}).get('sells', 0)

        volume = pair.get('volume', {})
        vol_m5 = volume.get('m5', 0)
        vol_h1 = volume.get('h1', 0)
        vol_h6 = volume.get('h6', 0)
        vol_h24 = volume.get('h24', 0)

        price_change = pair.get('priceChange', {})
        change_m5 = price_change.get('m5', 0)
        change_h1 = price_change.get('h1', 0)
        change_h6 = price_change.get('h6', 0)
        change_h24 = price_change.get('h24', 0)

        liquidity = pair.get('liquidity', {})
        liq_usd = liquidity.get('usd', 0)
        liq_base = liquidity.get('base', 0)
        liq_quote = liquidity.get('quote', 0)

        fdv = pair.get('fdv', 0)
        market_cap = pair.get('marketCap', 0)
        pair_created_at = pair.get('pairCreatedAt', 'N/A')

        info = pair.get('info', {})
        image_url = info.get('imageUrl', 'N/A')
        websites = [w.get('url', '') for w in info.get('websites', [])]
        socials = [f"{s.get('type', '')}: {s.get('url', '')}" for s in info.get('socials', [])]

        website_str = ", ".join(websites) if websites else "None"
        socials_str = "\n".join(socials) if socials else "None"

        # Format full output
        msg = (
            f"📌 **PAIR IDENTIFIERS**\n"
            f"• **Chain:** {chain_id}\n"
            f"• **DEX:** {dex_id}\n"
            f"• **Pair Address:** `{pair_address}`\n"
            f"• **URL:** {pair_url}\n"
            f"• **Created At:** {pair_created_at}\n\n"

            f"🪙 **BASE TOKEN**\n"
            f"• **Name:** {base_name}\n"
            f"• **Symbol:** ${base_symbol}\n"
            f"• **Address:** `{base_address}`\n\n"

            f"💵 **QUOTE TOKEN**\n"
            f"• **Name:** {quote_name}\n"
            f"• **Symbol:** {quote_symbol}\n"
            f"• **Address:** `{quote_address}`\n\n"

            f"💰 **PRICING & VALUATION**\n"
            f"• **Price USD:** ${float(price_usd):.8f}\n"
            f"• **Price Native:** {price_native} {quote_symbol}\n"
            f"• **Market Cap:** ${market_cap:,.2f}\n"
            f"• **FDV:** ${fdv:,.2f}\n\n"

            f"💧 **LIQUIDITY**\n"
            f"• **Total USD:** ${liq_usd:,.2f}\n"
            f"• **Base Tokens:** {liq_base:,.2f}\n"
            f"• **Quote Tokens:** {liq_quote:,.2f}\n\n"

            f"📊 **PRICE CHANGE**\n"
            f"• **5m:** {change_m5}%\n"
            f"• **1h:** {change_h1}%\n"
            f"• **6h:** {change_h6}%\n"
            f"• **24h:** {change_h24}%\n\n"

            f"📈 **VOLUME**\n"
            f"• **5m:** ${vol_m5:,.2f}\n"
            f"• **1h:** ${vol_h1:,.2f}\n"
            f"• **6h:** ${vol_h6:,.2f}\n"
            f"• **24h:** ${vol_h24:,.2f}\n\n"

            f"🔄 **TRANSACTIONS (BUYS / SELLS)**\n"
            f"• **5m:** {txns_m5_buys} B / {txns_m5_sells} S\n"
            f"• **1h:** {txns_h1_buys} B / {txns_h1_sells} S\n"
            f"• **6h:** {txns_h6_buys} B / {txns_h6_sells} S\n"
            f"• **24h:** {txns_h24_buys} B / {txns_h24_sells} S\n\n"

            f"🌐 **MEDIA & LINKS**\n"
            f"• **Image URL:** {image_url}\n"
            f"• **Websites:** {website_str}\n"
            f"• **Socials:**\n{socials_str}"
        )

        await update.message.reply_text(msg, parse_mode='Markdown', disable_web_page_preview=True)

    except Exception as e:
        await update.message.reply_text(f"⚠️ Error: {str(e)}")

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Send me any token Contract Address (CA) to get all raw DEXScreener metrics.")

if __name__ == '__main__':
    threading.Thread(target=run_flask, daemon=True).start()

    telegram_app = ApplicationBuilder().token(BOT_TOKEN).build()
    telegram_app.add_handler(CommandHandler('start', start_command))
    telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, analyze_command))
    
    print("Bot starting...")
    telegram_app.run_polling()
