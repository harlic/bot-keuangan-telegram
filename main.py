import os
import json
import base64
import logging
import threading
import time
import requests
from datetime import datetime, timedelta

from flask import Flask
from dotenv import load_dotenv
import gspread
from google.oauth2.service_account import Credentials

from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler,
    MessageHandler, ContextTypes, filters
)

# ===========================================================
# ENV & LOGGING
# ===========================================================
load_dotenv()

BOT_TOKEN        = os.getenv("BOT_TOKEN")
SPREADSHEET_NAME = os.getenv("SPREADSHEET_NAME")
KATEGORI_SHEET   = os.getenv("KATEGORI_SHEET", "Kategori")
DATA_SHEET       = os.getenv("DATA_SHEET", "Sheet1")
BUDGET_SHEET     = os.getenv("BUDGET_SHEET", "Budget")
ADMIN_CHAT_ID    = os.getenv("ADMIN_CHAT_ID")
encoded_json     = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON_BASE64")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

# ===========================================================
# Flask App (untuk UptimeRobot & self-ping)
# ===========================================================
app = Flask(__name__)

@app.route("/")
def home():
    return "Bot Keuangan Aktif 🚀"

@app.route("/ping")
def ping():
    return "pong"

# ===========================================================
# Google Sheets Connection
# ===========================================================
def get_gc():
    """Selalu buat koneksi gspread yang fresh."""
    creds_dict = json.loads(base64.b64decode(encoded_json).decode("utf-8"))
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    return gspread.authorize(creds)

# ===========================================================
# Helpers
# ===========================================================
def parse_amount(s: str) -> int:
    return int(s.replace(",", "").replace(".", "").strip())

def load_kategori_list() -> list[str]:
    try:
        gc = get_gc()
        ks = gc.open(SPREADSHEET_NAME).worksheet(KATEGORI_SHEET)
        return [k.strip().lower() for k in ks.col_values(1)[1:] if k.strip()]
    except Exception as e:
        logging.warning("⚠️ Tidak bisa load kategori: %s", e)
        return []

def load_budget_data() -> dict:
    """Ambil data budget terbaru untuk bulan tertentu."""
    data = {}
    try:
        gc = get_gc()
        sheet = gc.open(SPREADSHEET_NAME).worksheet(BUDGET_SHEET)
        for row in sheet.get_all_values()[1:]:
            if len(row) < 3:
                continue
            bulan    = row[0].strip()
            kategori = row[1].strip().lower()
            nominal  = parse_amount(row[2])
            data[(bulan, kategori)] = nominal
    except Exception as e:
        logging.warning("⚠️ Tidak bisa load budget: %s", e)
    return data

# ===========================================================
# Keep Render Awake
# ===========================================================
def keep_alive():
    url = "https://bot-keuangan-telegram.onrender.com/ping"
    while True:
        try:
            requests.get(url, timeout=6)
            logging.info("🔁 Self-ping...")
        except Exception as e:
            logging.warning("Ping gagal: %s", e)
        time.sleep(240)  # 4 menit (gratis)

# ===========================================================
# Telegram Handlers
# ===========================================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [["/rekapbulan", "/rekapminggu"], ["/kategori"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    await update.message.reply_text(
        "Halo! 👋\n"
        "Gunakan tombol di bawah atau catat pengeluaran:\n"
        "`15000 beli kopi #jajan`",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def kategori_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kategori_list = load_kategori_list()
    if not kategori_list:
        await update.message.reply_text("❌ Tidak dapat memuat kategori.")
        return

    daftar = "\n".join(f"- {k.title()}" for k in kategori_list)
    await update.message.reply_text("*Kategori:*\n" + daftar, parse_mode="Markdown")

async def rekap(update: Update, context: ContextTypes.DEFAULT_TYPE, tipe: str):

    try:
        now = datetime.now()

        if tipe == "mingguan":
            start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0)
            end = now.replace(hour=23, minute=59, second=59)
            bulan_str = None
            budget_data = {}

        elif tipe == "bulanan":
            start = now.replace(day=1, hour=0, minute=0)
            if now.month == 12:
                end = start.replace(year=now.year + 1, month=1)
            else:
                end = start.replace(month=now.month + 1)

            bulan_str = start.strftime("%Y-%m")
            budget_data = load_budget_data()

        else:
            await update.message.reply_text("❌ Jenis rekap tidak dikenal.")
            return

        # selalu gunakan koneksi fresh
        gc = get_gc()
        sheet = gc.open(SPREADSHEET_NAME).worksheet(DATA_SHEET)
        rows = sheet.get_all_values()[1:]

        data = []
        for r in rows:

            raw_date = (
                r[0]
                .strip()
                .replace("'", "")
                .replace("’", "")
                .replace("‘", "")
                .strip()
            )

            parsed = None
            for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d-%m-%Y", "%d/%m/%Y"):
                try:
                    parsed = datetime.strptime(raw_date, fmt)
                    break
                except:
                    pass

            if not parsed:
                logging.warning(f"⚠️ Tidak bisa parse tanggal: {raw_date}")
                continue

            if start <= parsed < end:
                data.append(r)


        if not data:
            await update.message.reply_text("📭 Tidak ada transaksi pada periode ini.")
            return

        per_kat = {}
        total = 0

        for r in data:
            nominal = parse_amount(r[1])
            total += nominal
            key = r[3].strip().lower()
            per_kat[key] = per_kat.get(key, 0) + nominal

        msg = f"📊 Rekap {tipe.capitalize()} (mulai {start.strftime('%Y-%m-%d')}):\n"

        for k, v in per_kat.items():
            if tipe == "bulanan":
                budget = budget_data.get((bulan_str, k))
                if budget:
                    msg += f"- {k.title()}: Rp{v:,} / Rp{budget:,}\n"
                else:
                    msg += f"- {k.title()}: Rp{v:,} (no budget)\n"
            else:
                msg += f"- {k.title()}: Rp{v:,}\n"

        if tipe == "bulanan":
            msg += "\nSisa Anggaran:\n"
            for k, v in per_kat.items():
                budget = budget_data.get((bulan_str, k))
                if budget:
                    msg += f"- {k.title()}: Rp{budget - v:,}\n"

        msg += f"\n💰 Total: Rp{total:,}"

        await update.message.reply_text(msg)

    except Exception as e:
        logging.error("❌ Error rekap", exc_info=e)
        await update.message.reply_text("❌ Terjadi kesalahan saat rekap data.")

async def rekap_mingguan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await rekap(update, context, "mingguan")

async def rekap_bulanan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await rekap(update, context, "bulanan")

async def handle_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):

    try:
        text = update.message.text.strip()
        parts = text.split()

        amount = parse_amount(parts[0])
        hashtag_index = next(i for i, p in enumerate(parts) if p.startswith("#"))
        description = " ".join(parts[1:hashtag_index])
        kategori = " ".join(parts[hashtag_index:])[1:].strip().lower()

        kategori_list = load_kategori_list()
        if kategori not in kategori_list:
            await update.message.reply_text(
                f"❌ Kategori *{kategori}* tidak dikenal.",
                parse_mode="Markdown"
            )
            return

        tanggal = datetime.now().strftime("%Y-%m-%d")

        # always fresh gc & sheet
        gc = get_gc()
        sheet = gc.open(SPREADSHEET_NAME).worksheet(DATA_SHEET)
        sheet.append_row([tanggal, amount, description, kategori])

        await update.message.reply_text("✅ Tersimpan!")

    except Exception as e:
        logging.error("❌ Error handle_msg", exc_info=e)
        await update.message.reply_text(
            "❌ Format salah. Contoh:\n`15000 beli kopi #makan`",
            parse_mode="Markdown"
        )

# ===========================================================
# Telegram Application
# ===========================================================
application = Application.builder().token(BOT_TOKEN).build()
application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("kategori", kategori_cb))
application.add_handler(CommandHandler("rekapminggu", rekap_mingguan))
application.add_handler(CommandHandler("rekapbulan", rekap_bulanan))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_msg))

# ===========================================================
# Run Flask + Polling
# ===========================================================
if __name__ == "__main__":

    def run_flask():
        port = int(os.environ.get("PORT", 10000))
        app.run(host="0.0.0.0", port=port)

    threading.Thread(target=keep_alive, daemon=True).start()
    threading.Thread(target=run_flask, daemon=True).start()

    application.run_polling()
