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

import requests, time
from telegram import ReplyKeyboardMarkup

# ================== Load ENV & Logging ==================
load_dotenv()
BOT_TOKEN       = os.getenv("BOT_TOKEN")
SPREADSHEET_NAME= os.getenv("SPREADSHEET_NAME")
KATEGORI_SHEET  = os.getenv("KATEGORI_SHEET", "Kategori")
DATA_SHEET      = os.getenv("DATA_SHEET", "Sheet1")
BUDGET_SHEET    = os.getenv("BUDGET_SHEET", "Budget")
encoded_json    = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON_BASE64")

logging.basicConfig(level=logging.INFO)

# ================== Flask (untuk UptimeRobot) ==================
app = Flask(__name__)

@app.route("/")
def home():
    return "Bot Keuangan Aktif 🚀"

@app.route("/ping")
def ping():
    return "pong"

# ================== Google Sheets Setup ==================
try:
    creds_dict = json.loads(base64.b64decode(encoded_json).decode("utf-8"))
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    gc    = gspread.authorize(creds)

    sheet_data = gc.open(SPREADSHEET_NAME).worksheet(DATA_SHEET)
except Exception as e:
    logging.error("❌ Gagal inisialisasi Google Sheets:", exc_info=e)
    raise SystemExit("❌ Tidak bisa lanjut tanpa Google Credentials!")

# ================== Helper Functions ==================
def parse_amount(s: str) -> int:
    """Ubah string angka (dengan koma/titik) menjadi int."""
    return int(s.replace(",", "").replace(".", "").strip())

def load_kategori_list() -> list[str]:
    """Selalu ambil daftar kategori terbaru dari sheet."""
    ks = gc.open(SPREADSHEET_NAME).worksheet(KATEGORI_SHEET)
    return [k.strip().lower() for k in ks.col_values(1)[1:] if k.strip()]

def load_budget_data() -> dict:
    """Selalu ambil data budget terbaru per (bulan,kategori)."""
    budget_sheet = gc.open(SPREADSHEET_NAME).worksheet(BUDGET_SHEET)
    budget_rows  = budget_sheet.get_all_values()[1:]
    data = {}
    for row in budget_rows:
        if len(row) < 3:
            continue
        bulan    = row[0].strip()
        kategori = row[1].strip().lower()
        try:
            nominal = parse_amount(row[2])
            data[(bulan, kategori)] = nominal
        except ValueError:
            logging.warning("Budget invalid di baris: %s", row)
    return data

def keep_alive():
    url = "https://bot-keuangan-telegram.onrender.com/ping"
    while True:
        try:
            requests.get(url, timeout=10)
            logging.info("🔁 Self-ping sent to keep Render awake.")
        except Exception as e:
            logging.warning(f"Ping gagal: {e}")
        time.sleep(240)  # setiap 4 menit


# ================== Telegram Handlers ==================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        ["/rekapbulan", "/rekapminggu"],
        ["/kategori"]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    await update.message.reply_text(
        "Halo! 👋\n"
        "Gunakan tombol di bawah untuk mulai:\n"
        "- Catat pengeluaran dengan format: `<jumlah> <deskripsi> #kategori`\n"
        "- atau tekan tombol untuk melihat rekap dan kategori.",
        reply_markup=reply_markup
    )

async def kategori_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    daftar = "\n".join(f"- {k.title()}" for k in load_kategori_list())
    await update.message.reply_text("*Kategori:*\n" + daftar, parse_mode="Markdown")

async def rekap(update: Update, context: ContextTypes.DEFAULT_TYPE, tipe: str):
    try:
        now = datetime.now()
        if tipe == "mingguan":
            start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
            end   = now.replace(hour=23, minute=59, second=59, microsecond=999999)  # sampai hari ini
        elif tipe == "bulanan":
            start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            # awal bulan berikutnya
            if start.month == 12:
                end = start.replace(year=start.year + 1, month=1)
            else:
                end = start.replace(month=start.month + 1)
            bulan_str   = start.strftime("%Y-%m")
            budget_data = load_budget_data()
        else:
            await update.message.reply_text("❌ Tipe rekap tidak dikenal.")
            return

        rows = sheet_data.get_all_values()[1:]
        data = []
        for r in rows:
            try:
                tanggal = datetime.strptime(r[0].strip(), "%Y-%m-%d")
                # cek batas akhir
                if tanggal >= start and tanggal < end:
                    data.append(r)
            except Exception:
                continue

        total = sum(parse_amount(r[1]) for r in data)
        per_kat = {}
        for r in data:
            key = r[3].strip().lower()
            per_kat[key] = per_kat.get(key, 0) + parse_amount(r[1])

        start_str = start.strftime("%Y-%m-%d")
        msg = f"📊 Rekap {tipe.capitalize()} (mulai {start_str}):\n"

        for k, v in per_kat.items():
            if tipe == "bulanan":
                budget = budget_data.get((bulan_str, k))
                if budget is not None:
                    msg += f"- {k.title()}: Rp{v:,} / Rp{budget:,}\n"
                else:
                    msg += f"- {k.title()}: Rp{v:,} (no budget)\n"
            else:
                msg += f"- {k.title()}: Rp{v:,}\n"

        if tipe == "bulanan":
            msg += "\nSisa Anggaran:\n"
            for k, v in per_kat.items():
                budget = budget_data.get((bulan_str, k))
                if budget is not None:
                    sisa = budget - v
                    msg += f"- {k.title()}: Rp{sisa:,}\n"

        msg += f"\nTotal Pengeluaran: Rp{total:,}"
        await update.message.reply_text(msg)

    except Exception as e:
        logging.error("❌ Error rekap:", exc_info=e)
        await update.message.reply_text("❌ Gagal ambil data rekap.")

async def rekap_mingguan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await rekap(update, context, "mingguan")

async def rekap_bulanan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await rekap(update, context, "bulanan")

async def handle_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        text   = update.message.text.strip()
        parts  = text.split()
        amount = parse_amount(parts[0])
        hashtag_index = next(i for i, p in enumerate(parts) if p.startswith("#"))
        description   = " ".join(parts[1:hashtag_index])
        kategori      = " ".join(parts[hashtag_index:])[1:].strip().lower()

        if kategori not in load_kategori_list():
            await update.message.reply_text(
                f"❌ Kategori *{kategori}* tidak ditemukan.",
                parse_mode="Markdown"
            )
            return

        tanggal = datetime.now().strftime("%Y-%m-%d")
        sheet_data.append_row([tanggal, amount, description, kategori])
        await update.message.reply_text("✅ Catatan disimpan!")

    except Exception as e:
        logging.error("❌ Error handle_msg:", exc_info=e)
        await update.message.reply_text(
            "❌ Format salah. Contoh:\n`15000 beli kopi #makan`",
            parse_mode="Markdown"
        )

# ================== Telegram Application ==================
application = Application.builder().token(BOT_TOKEN).build()
application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("kategori", kategori_cb))
application.add_handler(CommandHandler("rekapminggu", rekap_mingguan))
application.add_handler(CommandHandler("rekapbulan", rekap_bulanan))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_msg))

# ================== Run Polling + Flask ==================
if __name__ == "__main__":
    def run_flask():
        port = int(os.environ.get("PORT", 10000))
        app.run(host="0.0.0.0", port=port)

    # Jalankan Flask dan self-ping di thread terpisah
    threading.Thread(target=keep_alive, daemon=True).start()
    threading.Thread(target=run_flask, daemon=True).start()
    application.run_polling()

