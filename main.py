import os, json, base64, logging, asyncio
from datetime import datetime, timedelta
from flask import Flask, request
from dotenv import load_dotenv
import gspread
from google.oauth2.service_account import Credentials
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

# --- Load ENV ---
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
SPREADSHEET_NAME = os.getenv("SPREADSHEET_NAME")
KATEGORI_SHEET = os.getenv("KATEGORI_SHEET", "Kategori")
DATA_SHEET = os.getenv("DATA_SHEET", "Sheet1")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # tanpa slash di akhir
encoded_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON_BASE64")

# --- Logging ---
logging.basicConfig(level=logging.INFO)

# --- Flask Setup ---
flask_app = Flask(__name__)

@flask_app.route("/")
def home():
    return "Bot Keuangan Aktif 🚀"

@flask_app.route("/ping")
def ping():
    return "pong"

# --- Google Sheets Setup ---
try:
    decoded_json = base64.b64decode(encoded_json).decode("utf-8")
    service_account_info = json.loads(decoded_json)
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    creds = Credentials.from_service_account_info(service_account_info, scopes=scopes)
    gc = gspread.authorize(creds)

    sheet = gc.open(SPREADSHEET_NAME).worksheet(DATA_SHEET)
    kategori_sheet = gc.open(SPREADSHEET_NAME).worksheet(KATEGORI_SHEET)
    kategori_values = kategori_sheet.col_values(1)[1:]
    kategori_list = [k.strip().lower() for k in kategori_values if k.strip()]
except Exception as e:
    logging.error("Gagal inisialisasi Google Sheets:", exc_info=e)
    raise SystemExit("❌ Gagal memuat Google credentials.")

# --- Command Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Halo! Kirim catatan keuangan kamu dengan format:\n\n"
        "<jumlah> <deskripsi> #kategori\n\n"
        "Contoh:\n15000 beli kopi #makan"
    )

async def show_kategori(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = "*📂 Daftar Kategori:*\n" + "\n".join(f"- {k.title()}" for k in kategori_list)
    await update.message.reply_text(msg, parse_mode="Markdown")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        parts = update.message.text.strip().split()
        amount = int(parts[0].replace(",", ""))
        hashtag_index = next(i for i, p in enumerate(parts) if p.startswith("#"))
        description = " ".join(parts[1:hashtag_index])
        category_raw = " ".join(parts[hashtag_index:])[1:].strip().lower()

        if category_raw not in kategori_list:
            await update.message.reply_text(
                f"❌ Kategori *{category_raw}* tidak ditemukan!\nGunakan /kategori untuk melihat daftar.",
                parse_mode="Markdown"
            )
            return

        tanggal = datetime.now().strftime("%Y-%m-%d")
        sheet.append_row([tanggal, amount, description, category_raw])
        await update.message.reply_text("✅ Tersimpan!")
    except Exception as e:
        logging.error("Error handle_message:", exc_info=e)
        await update.message.reply_text("❌ Format salah. Cth: `15000 beli kopi #makan`", parse_mode="Markdown")

async def rekap_periode(update: Update, context: ContextTypes.DEFAULT_TYPE, periode: str):
    try:
        data = sheet.get_all_values()[1:]
        now = datetime.now()
        start = now - timedelta(days=now.weekday()) if periode == "mingguan" else now.replace(day=1)
        filtered = [row for row in data if datetime.strptime(row[0], "%Y-%m-%d") >= start]
        total = sum(int(row[1].replace(",", "").strip()) for row in filtered)
        by_cat = {}
        for row in filtered:
            by_cat[row[3]] = by_cat.get(row[3], 0) + int(row[1].replace(",", "").strip())
        msg = f"📊 Rekap {periode.capitalize()} mulai {start.strftime('%Y-%m-%d')}:\n"
        for k, v in by_cat.items():
            msg += f"- {k.title()}: Rp{v:,}\n"
        msg += f"\nTotal: Rp{total:,}"
        await update.message.reply_text(msg)
    except Exception as e:
        logging.error("Error rekap:", exc_info=e)
        await update.message.reply_text("❌ Gagal membuat rekap.")

async def rekap_mingguan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await rekap_periode(update, context, "mingguan")

async def rekap_bulanan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await rekap_periode(update, context, "bulanan")

# --- Init Application ---
application = Application.builder().token(BOT_TOKEN).build()
application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("kategori", show_kategori))
application.add_handler(CommandHandler("rekapminggu", rekap_mingguan))
application.add_handler(CommandHandler("rekapbulan", rekap_bulanan))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

# --- Webhook Endpoint ---
@flask_app.route("/webhook", methods=["POST"])
def webhook():
    try:
        data = request.get_json(force=True)
        update = Update.de_json(data, application.bot)
        asyncio.run(application.initialize())  # ✅ Penting agar tidak error!
        asyncio.run(application.process_update(update))
    except Exception as e:
        logging.error("❌ Webhook error:", exc_info=e)
        return "Internal Server Error", 500
    return "ok", 200

# --- Set Webhook saat startup ---
async def set_webhook():
    await application.bot.set_webhook(url=f"{WEBHOOK_URL}/webhook")

if __name__ == "__main__":
    asyncio.run(set_webhook())
    flask_app.run(host="0.0.0.0", port=int(os.getenv("PORT", 10000)))
