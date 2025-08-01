import os
import json
import base64
import logging
from datetime import datetime, timedelta
from dotenv import load_dotenv
from flask import Flask, request

import gspread
from google.oauth2.service_account import Credentials

from telegram import Update
from telegram.ext import (
    Application, CommandHandler,
    MessageHandler, ContextTypes, filters
)
import asyncio

# --- Load ENV ---
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
SPREADSHEET_NAME = os.getenv("SPREADSHEET_NAME")
KATEGORI_SHEET = os.getenv("KATEGORI_SHEET", "Kategori")
DATA_SHEET = os.getenv("DATA_SHEET", "Sheet1")
encoded_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON_BASE64")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # e.g., https://xxx.onrender.com

# --- Flask Setup ---
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
    decoded_json = base64.b64decode(encoded_json).decode("utf-8")
    service_account_info = json.loads(decoded_json)
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(service_account_info, scopes=scopes)
    gc = gspread.authorize(creds)

    sheet = gc.open(SPREADSHEET_NAME).worksheet(DATA_SHEET)
    kategori_sheet = gc.open(SPREADSHEET_NAME).worksheet(KATEGORI_SHEET)
    kategori_values = kategori_sheet.col_values(1)[1:]  # kolom A
    kategori_list = [k.strip().lower() for k in kategori_values if k.strip()]
except Exception as e:
    logging.error("❌ Gagal inisialisasi Google Sheets:", exc_info=e)
    raise SystemExit("❌ Gagal memuat Google credentials.")

# --- Command Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Halo! Kirim catatan keuangan kamu dengan format:\n\n"
        "<jumlah> <deskripsi> #kategori\n\n"
        "Contoh:\n15000 beli kopi #makan"
    )

async def show_kategori(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        msg = "*📂 Daftar Kategori:*\n"
        msg += "\n".join(f"- {k.title()}" for k in kategori_list)
        await update.message.reply_text(msg, parse_mode="Markdown")
    except Exception as e:
        logging.error(f"Error show kategori: {e}")
        await update.message.reply_text("❌ Gagal mengambil daftar kategori.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        parts = update.message.text.strip().split()
        amount = int(parts[0])
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
    except ValueError:
        await update.message.reply_text("❌ Jumlah harus berupa angka di awal.")
    except StopIteration:
        await update.message.reply_text("❌ Format salah! Gunakan tanda `#kategori` di akhir.", parse_mode="Markdown")
    except Exception as e:
        logging.error(f"Error handle_message: {e}")
        await update.message.reply_text("❌ Terjadi kesalahan. Coba lagi ya!")

async def rekap_periode(update: Update, context: ContextTypes.DEFAULT_TYPE, periode: str):
    try:
        data = sheet.get_all_values()[1:]
        now = datetime.now()

        if periode == "mingguan":
            start_date = now - timedelta(days=now.weekday())
        elif periode == "bulanan":
            start_date = now.replace(day=1)
        else:
            await update.message.reply_text("❌ Periode tidak valid.")
            return

        filtered = [row for row in data if datetime.strptime(row[0], "%Y-%m-%d") >= start_date]
        total = sum(int(row[1].replace(",", "").strip()) for row in filtered)

        kategori_rekap = {}
        for row in filtered:
            angka = int(row[1].replace(",", "").strip())
            kategori_rekap[row[3]] = kategori_rekap.get(row[3], 0) + angka

        msg = f"📊 Rekap {periode.capitalize()} (mulai {start_date.strftime('%Y-%m-%d')}):\n"
        for kategori, jumlah in kategori_rekap.items():
            msg += f"- {kategori.title()}: Rp{jumlah:,}\n"
        msg += f"\nTotal: Rp{total:,}"
        await update.message.reply_text(msg)
    except Exception as e:
        logging.error(f"Error rekap {periode}: {e}")
        await update.message.reply_text("❌ Gagal membuat rekap.")

async def rekap_mingguan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await rekap_periode(update, context, "mingguan")

async def rekap_bulanan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await rekap_periode(update, context, "bulanan")

# --- Inisialisasi Bot ---
application = Application.builder().token(BOT_TOKEN).build()
application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("kategori", show_kategori))
application.add_handler(CommandHandler("rekapminggu", rekap_mingguan))
application.add_handler(CommandHandler("rekapbulan", rekap_bulanan))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

# --- Telegram Webhook Handler ---
@flask_app.route("/webhook", methods=["POST"])
def webhook():
    try:
        request_data = request.get_json(force=True)
        update = Update.de_json(request_data, application.bot)
        asyncio.run(application.process_update(update))
    except Exception as e:
        logging.error("❌ Webhook error:", exc_info=e)
    return "OK"

# --- Set Webhook & Run Flask ---
if __name__ == "__main__":
    import asyncio
    asyncio.run(application.bot.set_webhook(url=f"{WEBHOOK_URL}/webhook"))
    port = int(os.environ.get("PORT", 10000))
    flask_app.run(host="0.0.0.0", port=port)
