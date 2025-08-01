import os, json, base64, logging, asyncio
from datetime import datetime, timedelta
from flask import Flask, request
from dotenv import load_dotenv
import gspread
from google.oauth2.service_account import Credentials
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

# --- Load environment ---
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
SPREADSHEET_NAME = os.getenv("SPREADSHEET_NAME")
KATEGORI_SHEET = os.getenv("KATEGORI_SHEET", "Kategori")
DATA_SHEET = os.getenv("DATA_SHEET", "Sheet1")
encoded = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON_BASE64")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

# --- Flask App ---
flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    return "Bot Keuangan Aktif 🚀"

@flask_app.route('/ping')
def ping():
    return "pong"

# --- Logging ---
logging.basicConfig(level=logging.INFO)

# --- Google Sheets Setup ---
try:
    creds_json = json.loads(base64.b64decode(encoded).decode())
    creds = Credentials.from_service_account_info(
        creds_json,
        scopes=[
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
    )
    gc = gspread.authorize(creds)
    sheet = gc.open(SPREADSHEET_NAME).worksheet(DATA_SHEET)
    kategori = gc.open(SPREADSHEET_NAME).worksheet(KATEGORI_SHEET)
    kategori_list = [c.strip().lower() for c in kategori.col_values(1)[1:] if c.strip()]
except Exception as e:
    logging.error("❌ Google Sheets init error:", exc_info=True)
    raise SystemExit("Gagal memuat Google credentials")

# --- Telegram Handlers ---
async def start_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Halo! Kirim catatan keuangan kamu:\n<jumlah> <deskripsi> #kategori"
    )

async def listkategori(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = "*Daftar Kategori:*\n" + "\n".join(f"- {k.title()}" for k in kategori_list)
    await update.message.reply_text(msg, parse_mode="Markdown")

async def handle_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        parts = update.message.text.strip().split()
        amount = int(parts[0].replace(",", ""))
        hashtag_index = next(i for i, p in enumerate(parts) if p.startswith("#"))
        desc = " ".join(parts[1:hashtag_index])
        cat = " ".join(parts[hashtag_index:])[1:].strip().lower()

        if cat not in kategori_list:
            await update.message.reply_text(
                f"❌ Kategori *{cat}* tidak ada. Gunakan /kategori untuk melihat daftar.",
                parse_mode="Markdown"
            )
            return

        today = datetime.now().strftime("%Y-%m-%d")
        sheet.append_row([today, amount, desc, cat])
        await update.message.reply_text("✅ Tersimpan!")
    except Exception:
        await update.message.reply_text(
            "❌ Format salah. Contoh: `15000 beli kopi #makan`",
            parse_mode="Markdown"
        )

async def rekap_per(update: Update, context: ContextTypes.DEFAULT_TYPE, periode: str):
    data = sheet.get_all_values()[1:]
    now = datetime.now()
    if periode == "mingguan":
        start = now - timedelta(days=now.weekday())
    else:
        start = now.replace(day=1)

    filtered = [r for r in data if datetime.strptime(r[0], "%Y-%m-%d") >= start]
    total = sum(int(r[1].replace(",", "")) for r in filtered)
    by_cat = {}
    for r in filtered:
        by_cat[r[3]] = by_cat.get(r[3], 0) + int(r[1].replace(",", ""))

    msg = f"📊 Rekap {periode.capitalize()} sejak {start.strftime('%Y-%m-%d')}:\n"
    for k, v in by_cat.items():
        msg += f"- {k.title()}: Rp{v:,}\n"
    msg += f"\nTotal: Rp{total:,}"
    await update.message.reply_text(msg)

async def rekap_mingguan_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await rekap_per(update, context, "mingguan")

async def rekap_bulanan_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await rekap_per(update, context, "bulanan")

# --- Build Telegram Application ---
application = Application.builder().token(BOT_TOKEN).build()
application.add_handler(CommandHandler("start", start_cb))
application.add_handler(CommandHandler("kategori", listkategori))
application.add_handler(CommandHandler("rekapminggu", rekap_mingguan_cb))
application.add_handler(CommandHandler("rekapbulan", rekap_bulanan_cb))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_msg))

# --- Webhook Route ---
@flask_app.route('/webhook', methods=['POST'])
def webhook():
    try:
        data = request.get_json(force=True)
        update = Update.de_json(data, application.bot)
        # Jalankan secara blocking agar tidak error loop
        asyncio.run(application.process_update(update))
    except Exception as e:
        logging.error("❌ Webhook error:", exc_info=True)
        return "error", 500
    return "ok", 200

# --- Set Webhook On Startup ---
async def set_webhook():
    await application.bot.set_webhook(url=f"{WEBHOOK_URL}/webhook")
    logging.info("✅ Webhook set ke %s/webhook", WEBHOOK_URL)

if __name__ == "__main__":
    asyncio.run(set_webhook())
    port = int(os.getenv("PORT", 10000))
    flask_app.run(host="0.0.0.0", port=port)
