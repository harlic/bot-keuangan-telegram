import os, json, base64, logging
import asyncio
from datetime import datetime, timedelta
from flask import Flask, request
from dotenv import load_dotenv
import gspread
from google.oauth2.service_account import Credentials
from telegram import Update
from telegram.ext import (
    Application, CommandHandler,
    MessageHandler, ContextTypes, filters
)

# Load env
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
SPREADSHEET_NAME = os.getenv("SPREADSHEET_NAME")
KATEGORI_SHEET = os.getenv("KATEGORI_SHEET", "Kategori")
DATA_SHEET = os.getenv("DATA_SHEET", "Sheet1")
ENCODED = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON_BASE64")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

@app.route('/')
def home():
    return "Bot Keuangan Aktif 🚀"
@app.route('/ping')
def ping():
    return "pong"

# Sheets
try:
    creds_json = json.loads(base64.b64decode(ENCODED).decode())
    creds = Credentials.from_service_account_info(creds_json, scopes=[
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ])
    gc = gspread.authorize(creds)
    sheet = gc.open(SPREADSHEET_NAME).worksheet(DATA_SHEET)
    kategori_list = [k.strip().lower() for k in gc.open(SPREADSHEET_NAME).worksheet(KATEGORI_SHEET).col_values(1)[1:]]
except Exception as e:
    logging.error("Google Sheets init error", exc_info=e)
    raise SystemExit

# Handler callbacks...
async def start_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Halo! Kirim pengeluaran: <jumlah> <desc> #kategori")

async def listkategori(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = "*Daftar Kategori:*\n" + "\n".join(f"- {k.title()}" for k in kategori_list)
    await update.message.reply_text(msg, parse_mode="Markdown")

async def handle_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        parts = update.message.text.strip().split()
        amount = int(parts[0].replace(",", ""))
        idx = next(i for i,p in enumerate(parts) if p.startswith("#"))
        desc = " ".join(parts[1:idx])
        cat = " ".join(parts[idx:])[1:].strip().lower()
        if cat not in kategori_list:
            await update.message.reply_text(f"❌ Kategori *{cat}* tidak ada")
            return
        sheet.append_row([datetime.now().strftime("%Y-%m-%d"), amount, desc, cat])
        await update.message.reply_text("✅ Tersimpan!")
    except Exception:
        await update.message.reply_text("❌ Format salah. Contoh: `15000 beli kopi #makan`")

async def rekap_per(update: Update, context: ContextTypes.DEFAULT_TYPE, periode: str):
    data = sheet.get_all_values()[1:]
    today = datetime.now()
    start = today - timedelta(days=today.weekday()) if periode == "mingguan" else today.replace(day=1)
    filtered = [r for r in data if datetime.strptime(r[0], "%Y-%m-%d") >= start]
    total = sum(int(r[1].replace(",", "")) for r in filtered)
    bycat = {}
    for r in filtered:
        bycat[r[3]] = bycat.get(r[3], 0) + int(r[1].replace(",", ""))
    msg = f"📊 Rekap {periode.capitalize()} sejak {start.strftime('%Y-%m-%d')}:\n"
    for k,v in bycat.items(): msg += f"- {k.title()}: Rp{v:,}\n"
    msg += f"\nTotal: Rp{total:,}"
    await update.message.reply_text(msg)

async def rekap_mingguan_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await rekap_per(update, context, "mingguan")

async def rekap_bulanan_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await rekap_per(update, context, "bulanan")

# Telegram Application
application = Application.builder().token(BOT_TOKEN).build()
application.add_handler(CommandHandler("start", start_cb))
application.add_handler(CommandHandler("kategori", listkategori))
application.add_handler(CommandHandler("rekapminggu", rekap_mingguan_cb))
application.add_handler(CommandHandler("rekapbulan", rekap_bulanan_cb))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_msg))

# Webhook route
@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json(force=True)
    update = Update.de_json(data, application.bot)
    asyncio.run(application.initialize())
    asyncio.run(application.process_update(update))
    return "OK", 200

# Startup: set webhook
if __name__ == "__main__":
    asyncio.run(application.bot.set_webhook(url=f"{WEBHOOK_URL}/webhook"))
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 10000)))
