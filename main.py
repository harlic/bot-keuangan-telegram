import os
import json
import base64
import logging
from datetime import datetime, timedelta
from flask import Flask

from dotenv import load_dotenv
import gspread
from google.oauth2.service_account import Credentials

from telegram import Update
from telegram.ext import (
    Application, CommandHandler,
    MessageHandler, ContextTypes, filters
)

# === Load ENV ===
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
SPREADSHEET_NAME = os.getenv("SPREADSHEET_NAME")
KATEGORI_SHEET = os.getenv("KATEGORI_SHEET", "Kategori")
DATA_SHEET = os.getenv("DATA_SHEET", "Sheet1")
encoded_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON_BASE64")

# === Logging ===
logging.basicConfig(level=logging.INFO)

# === Flask App for UptimeRobot ===
app = Flask(__name__)

@app.route("/")
def home():
    return "Bot Keuangan Aktif 🚀"

@app.route("/ping")
def ping():
    return "pong"

# === Google Sheets Setup ===
try:
    creds_dict = json.loads(base64.b64decode(encoded_json).decode("utf-8"))
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    gc = gspread.authorize(creds)
    sheet = gc.open(SPREADSHEET_NAME).worksheet(DATA_SHEET)
    kategori_sheet = gc.open(SPREADSHEET_NAME).worksheet(KATEGORI_SHEET)
    kategori_list = [k.strip().lower() for k in kategori_sheet.col_values(1)[1:] if k.strip()]
except Exception as e:
    logging.error("❌ Gagal inisialisasi Google Sheets:", exc_info=e)
    raise SystemExit("❌ Tidak bisa lanjut tanpa Google Credentials!")

# === Handler Functions ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Halo! Kirim catatan keuangan kamu:\n<jumlah> <deskripsi> #kategori"
    )

async def kategori_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    daftar = "\n".join(f"- {k.title()}" for k in kategori_list)
    await update.message.reply_text("*Kategori:*\n" + daftar, parse_mode="Markdown")

async def rekap(update: Update, context: ContextTypes.DEFAULT_TYPE, tipe: str):
    try:
        now = datetime.now()
        if tipe == "mingguan":
            start = now - timedelta(days=now.weekday())
        else:
            start = now.replace(day=1)

        rows = sheet.get_all_values()[1:]
        data = [r for r in rows if datetime.strptime(r[0], "%Y-%m-%d") >= start]
        total = sum(int(r[1].replace(",", "")) for r in data)

        per_kategori = {}
        for r in data:
            per_kategori[r[3]] = per_kategori.get(r[3], 0) + int(r[1].replace(",", ""))

        msg = f"📊 Rekap {tipe.capitalize()}:\n"
        for k, v in per_kategori.items():
            msg += f"- {k.title()}: Rp{v:,}\n"
        msg += f"\nTotal: Rp{total:,}"
        await update.message.reply_text(msg)
    except Exception as e:
        logging.error("Error rekap:", exc_info=e)
        await update.message.reply_text("❌ Gagal ambil data rekap.")

async def rekap_mingguan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await rekap(update, context, "mingguan")

async def rekap_bulanan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await rekap(update, context, "bulanan")

async def handle_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        text = update.message.text.strip()
        parts = text.split()
        amount = int(parts[0])
        hashtag_index = next(i for i, part in enumerate(parts) if part.startswith("#"))
        description = " ".join(parts[1:hashtag_index])
        kategori = " ".join(parts[hashtag_index:])[1:].strip().lower()

        if kategori not in kategori_list:
            await update.message.reply_text(
                f"❌ Kategori *{kategori}* tidak ditemukan.",
                parse_mode="Markdown"
            )
            return

        tanggal = datetime.now().strftime("%Y-%m-%d")
        sheet.append_row([tanggal, amount, description, kategori])
        await update.message.reply_text("✅ Catatan disimpan!")
    except Exception as e:
        logging.error("Error handle_msg:", exc_info=e)
        await update.message.reply_text(
            "❌ Format salah. Contoh:\n`15000 beli kopi #makan`",
            parse_mode="Markdown"
        )

# === Telegram App & Handlers ===
application = Application.builder().token(BOT_TOKEN).build()
application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("kategori", kategori_cb))
application.add_handler(CommandHandler("rekapminggu", rekap_mingguan))
application.add_handler(CommandHandler("rekapbulan", rekap_bulanan))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_msg))

# === Jalankan bot dan Flask secara paralel ===
if __name__ == "__main__":
    import threading

    def run_telegram():
        application.run_polling()

    def run_flask():
        app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))

    threading.Thread(target=run_telegram).start()
    run_flask()
