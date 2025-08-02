import os
import json
import base64
import logging
import threading
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

# === Flask App ===
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
    await update.message.reply_text("Halo! Kirim catatan keuangan kamu dengan format:\n\n<jumlah> <deskripsi> #kategori\n\nContoh:\n15000 beli kopi #jajan")

async def kategori_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    daftar = "\n".join(f"- {k.title()}" for k in kategori_list)
    await update.message.reply_text("*Kategori:*\n" + daftar, parse_mode="Markdown")

def parse_amount(s: str) -> int:
    return int(s.replace(",", "").replace(".", "").strip())

async def rekap(update: Update, context: ContextTypes.DEFAULT_TYPE, tipe: str):
    try:
        now = datetime.now()
        if tipe == "mingguan":
            start = now - timedelta(days=now.weekday())
        elif tipe == "bulanan":
            start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        else:
            await update.message.reply_text("❌ Tipe rekap tidak dikenal.")
            return

        rows = sheet.get_all_values()[1:]
        data = []
        for r in rows:
            try:
                tanggal = datetime.strptime(r[0].strip(), "%Y-%m-%d")
                if tanggal >= start:
                    data.append(r)
            except Exception:
                continue

        total = sum(parse_amount(r[1]) for r in data)

        per_kategori = {}
        for r in data:
            key = r[3].strip().lower()
            per_kategori[key] = per_kategori.get(key, 0) + parse_amount(r[1])

        start_str = start.strftime("%Y-%m-%d")
        msg = f"📊 Rekap {tipe.capitalize()} (mulai {start_str}):\n"
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
        logging.error("❌ Error handle_msg:", exc_info=e)
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

# === Run polling and Flask together ===
if __name__ == "__main__":
    def run_flask():
        port = int(os.environ.get("PORT", 10000))
        app.run(host="0.0.0.0", port=port)

    threading.Thread(target=run_flask).start()
    application.run_polling()
