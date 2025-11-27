import os
import json
import base64
import logging
import threading
import time
import requests
from datetime import datetime, timedelta, date
from flask import Flask
from dotenv import load_dotenv
import gspread
from google.oauth2.service_account import Credentials
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler,
    MessageHandler, ContextTypes, filters
)

# ================== ENV & LOGGING ==================
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

# ================== Flask App ==================
app = Flask(__name__)

@app.route("/")
def home():
    return "✅ Bot Keuangan Aktif"

@app.route("/ping")
def ping():
    return "pong"

# ================== Google Sheets Setup ==================
def init_sheets():
    try:
        creds_dict = json.loads(base64.b64decode(encoded_json).decode("utf-8"))
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        return gspread.authorize(creds)
    except Exception as e:
        logging.error("❌ Gagal inisialisasi Google Sheets", exc_info=e)
        raise SystemExit("❌ Tidak bisa lanjut tanpa Google Credentials!")

gc = init_sheets()
sheet_data = gc.open(SPREADSHEET_NAME).worksheet(DATA_SHEET)

# ================== Helper Functions ==================
def parse_amount(s: str) -> int:
    return int(s.replace(",", "").replace(".", "").strip())

def load_kategori_list() -> list[str]:
    try:
        ks = gc.open(SPREADSHEET_NAME).worksheet(KATEGORI_SHEET)
        return [k.strip().lower() for k in ks.col_values(1)[1:] if k.strip()]
    except Exception as e:
        logging.warning("⚠️ Tidak bisa load kategori: %s", e)
        return []

def load_budget_data() -> dict:
    data = {}
    try:
        budget_sheet = gc.open(SPREADSHEET_NAME).worksheet(BUDGET_SHEET)
        for row in budget_sheet.get_all_values()[1:]:
            if len(row) < 3:
                continue
            bulan = row[0].strip()
            kategori = row[1].strip().lower()
            try:
                nominal = parse_amount(row[2])
                data[(bulan, kategori)] = nominal
            except ValueError:
                logging.warning(f"⚠️ Budget invalid: {row}")
    except Exception as e:
        logging.warning("⚠️ Tidak bisa load budget: %s", e)
    return data

def keep_alive():
    url = "https://bot-keuangan-telegram.onrender.com/ping"
    while True:
        try:
            res = requests.get(url, timeout=8)
            if res.status_code == 200:
                logging.info("🔁 Self-ping sukses.")
            else:
                logging.warning("⚠️ Self-ping gagal (%s)", res.status_code)
        except Exception as e:
            logging.warning("Ping error: %s", e)
        time.sleep(240)  # setiap 4 menit

# ================== Telegram Handlers ==================
async def notify_admin(context: ContextTypes.DEFAULT_TYPE, message: str):
    if ADMIN_CHAT_ID:
        try:
            await context.bot.send_message(chat_id=int(ADMIN_CHAT_ID), text=message)
        except Exception as e:
            logging.warning("❌ Gagal kirim notifikasi admin: %s", e)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [["/rekapbulan", "/rekapminggu"], ["/kategori"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(
        "Halo! 👋\nGunakan tombol di bawah untuk mulai.\n\n"
        "Catat pengeluaran:\n`15000 beli kopi #jajan`\n\n"
        "Atau tekan tombol untuk rekap & lihat kategori.",
        reply_markup=reply_markup,
        parse_mode="Markdown",
    )

async def kategori_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kategori_list = load_kategori_list()
    if not kategori_list:
        await update.message.reply_text("❌ Gagal ambil daftar kategori.")
        return
    daftar = "\n".join(f"- {k.title()}" for k in kategori_list)
    await update.message.reply_text("*Kategori:*\n" + daftar, parse_mode="Markdown")

# ================== Bulan Helpers ==================
BULAN_MAP = {
    "jan": 1, "januari": 1,
    "feb": 2, "februari": 2,
    "mar": 3, "maret": 3,
    "apr": 4, "april": 4,
    "mei": 5,
    "jun": 6, "juni": 6,
    "jul": 7, "juli": 7,
    "agu": 8, "agustus": 8,
    "sep": 9, "sept": 9, "september": 9,
    "okt": 10, "oktober": 10,
    "nov": 11, "november": 11,
    "des": 12, "desember": 12,
}

def extract_available_months() -> list[str]:
    """Ambil daftar bulan unik dari Sheet1 dalam format YYYY-MM."""
    months = set()
    rows = sheet_data.get_all_values()[1:]
    for r in rows:
        try:
            d = datetime.strptime(r[0].strip(), "%Y-%m-%d")
            months.add(d.strftime("%Y-%m"))
        except:
            pass
    return sorted(months, reverse=True)

def parse_month_arg(arg: str) -> str | None:
    """Konversi input bulan menjadi YYYY-MM."""
    arg = arg.lower().strip()

    if arg.count("-") == 1:  # sudah YYYY-MM
        try:
            datetime.strptime(arg, "%Y-%m")
            return arg
        except:
            return None

    parts = arg.split()
    if len(parts) == 1:
        bulan = BULAN_MAP.get(parts[0][:3])
        if bulan:
            year = datetime.now().year
            return f"{year}-{bulan:02d}"
    elif len(parts) == 2:
        bulan = BULAN_MAP.get(parts[0][:3])
        if bulan and parts[1].isdigit():
            return f"{parts[1]}-{bulan:02d}"

    return None

async def rekap(update: Update, context: ContextTypes.DEFAULT_TYPE, tipe: str, bulan_override: str = None):
    try:
        now = datetime.now()
        if tipe == "mingguan":
            start = (now - timedelta(days=now.weekday())).date()
            end = now.date() + timedelta(days=1)
            bulan_str = None
        elif tipe == "bulanan":
            if bulan_override:  # rekap bulan tertentu
                tahun, bulan = bulan_override.split("-")
                tahun, bulan = int(tahun), int(bulan)
                start = date(tahun, bulan, 1)
                if bulan == 12:
                end = date(tahun + 1, 1, 1)
                else:
                end = date(tahun, bulan + 1, 1)
                bulan_str = bulan_override
            else:  # bulan berjalan
                start = date(now.year, now.month, 1)
                if now.month == 12:
                end = date(now.year + 1, 1, 1)
                else:
                end = date(now.year, now.month + 1, 1)
                bulan_str = start.strftime("%Y-%m")
            budget_data = load_budget_data()

        else:
            await update.message.reply_text("❌ Jenis rekap tidak dikenal.")
            return

        rows = sheet_data.get_all_values()[1:]
        data = []
        for r in rows:
            try:
                tanggal = datetime.strptime(r[0].strip(), "%Y-%m-%d").date()
                if start <= tanggal < end:
                    data.append(r)
            except Exception:
                continue

        if not data:
            await update.message.reply_text("📭 Belum ada transaksi untuk periode ini.")
            return

        per_kat = {}
        total = 0
        for r in data:
            nominal = parse_amount(r[1])
            total += nominal
            key = r[3].strip().lower()
            per_kat[key] = per_kat.get(key, 0) + nominal

        msg = f"📊 Rekap {tipe.capitalize()} (mulai {start}):\n"
        for k, v in per_kat.items():
            if tipe == "bulanan":
                budget = budget_data.get((bulan_str, k))
                if budget is not None:
                    msg += f"- {k.title()}: Rp{v:,} / Rp{budget:,}\n"
                else:
                    msg += f"- {k.title()}: Rp{v:,} (no budget)\n"
            else:
                msg += f"- {k.title()}: Rp{v:,}\n"

        if tipe == "bulanan" and budget_data:
            msg += "\nSisa Anggaran:\n"
            for k, v in per_kat.items():
                budget = budget_data.get((bulan_str, k))
                if budget is not None:
                    sisa = budget - v
                    msg += f"- {k.title()}: Rp{sisa:,}\n"

        msg += f"\n💰 Total Pengeluaran: Rp{total:,}"
        await update.message.reply_text(msg)

    except Exception as e:
        logging.error("❌ Error rekap", exc_info=e)
        await update.message.reply_text("❌ Terjadi kesalahan saat rekap data.")

async def rekap_mingguan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await rekap(update, context, "mingguan")

async def rekap_bulanan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args

    # Jika ada argumen → rekap bulan tertentu
    if args:
        bulan_arg = " ".join(args)
        bulan_str = parse_month_arg(bulan_arg)

        if not bulan_str:
            await update.message.reply_text("❌ Format bulan tidak dikenali.\nContoh:\n`/rekapbulan 2025-09`\n`/rekapbulan november`")
            return

        await rekap(update, context, "bulanan", bulan_override=bulan_str)
        return

    # Jika tanpa argumen → tampilkan daftar bulan
    months = extract_available_months()
    if not months:
        await update.message.reply_text("📭 Belum ada data bulan.")
        return

    daftar = "\n".join(f"- `/rekapbulan {m}`" for m in months)
    await update.message.reply_text(
        "📅 Pilih bulan untuk rekap:\n" + daftar,
        parse_mode="Markdown"
    )


async def handle_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        text = update.message.text.strip()
        parts = text.split()
        amount = parse_amount(parts[0])
        hashtag_index = next(i for i, part in enumerate(parts) if part.startswith("#"))
        description = " ".join(parts[1:hashtag_index])
        kategori = " ".join(parts[hashtag_index:])[1:].strip().lower()

        kategori_list = load_kategori_list()
        if kategori not in kategori_list:
            await update.message.reply_text(f"❌ Kategori *{kategori}* tidak ditemukan.", parse_mode="Markdown")
            return

        tanggal = datetime.now().strftime("%Y-%m-%d")
        sheet_data.append_row([tanggal, amount, description, kategori])
        await update.message.reply_text("✅ Catatan disimpan!")

    except Exception as e:
        logging.error("❌ Error handle_msg", exc_info=e)
        await update.message.reply_text(
            "❌ Format salah.\nContoh: `15000 beli kopi #makan`",
            parse_mode="Markdown"
        )

# ================== Telegram Application ==================
application = Application.builder().token(BOT_TOKEN).build()
application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("kategori", kategori_cb))
application.add_handler(CommandHandler("rekapminggu", rekap_mingguan))
application.add_handler(CommandHandler("rekapbulan", rekap_bulanan))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_msg))

# ================== Run Flask + Polling ==================
if __name__ == "__main__":
    def run_flask():
        port = int(os.environ.get("PORT", 10000))
        app.run(host="0.0.0.0", port=port)

    threading.Thread(target=keep_alive, daemon=True).start()
    threading.Thread(target=run_flask, daemon=True).start()

    import asyncio
    async def main():
        await application.initialize()
        await application.start()
        logging.info("🤖 Bot polling dimulai...")
        await application.updater.start_polling()
        await asyncio.Event().wait()

    asyncio.run(main())
