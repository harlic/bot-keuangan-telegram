import logging
import os
import json
from datetime import datetime, timedelta
from dotenv import load_dotenv
import gspread
from google.oauth2.service_account import Credentials
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler,
    MessageHandler, ContextTypes, filters
)

# --- Load Environment Variables ---
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
SPREADSHEET_NAME = os.getenv("SPREADSHEET_NAME")
KATEGORI_SHEET = os.getenv("KATEGORI_SHEET", "Kategori")
DATA_SHEET = os.getenv("DATA_SHEET", "Sheet1")
SERVICE_ACCOUNT_JSON = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")

# --- Logging ---
logging.basicConfig(level=logging.INFO)

# --- Google Sheets Setup ---
try:
    SCOPES = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    service_account_info = json.loads(SERVICE_ACCOUNT_JSON)
    creds = Credentials.from_service_account_info(service_account_info, scopes=SCOPES)
    gc = gspread.authorize(creds)

    sheet = gc.open(SPREADSHEET_NAME).worksheet(DATA_SHEET)
    kategori_sheet = gc.open(SPREADSHEET_NAME).worksheet(KATEGORI_SHEET)

    kategori_values = kategori_sheet.col_values(1)[1:]  # Kolom A, skip header
    kategori_list = [k.strip().lower() for k in kategori_values if k.strip()]

except Exception as e:
    logging.error(f"Gagal inisialisasi Google Sheets: {e}")
    raise

# --- Command: /start ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Halo! Kirim catatan keuangan kamu dengan format:\n\n"
        "<jumlah> <deskripsi> #kategori\n\n"
        "Contoh:\n15000 beli kopi #makan"
    )

# --- Command: /kategori ---
async def show_kategori(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if not kategori_list:
            raise ValueError("Daftar kategori kosong.")

        msg_lines = ["*📂 Daftar Kategori:*"]
        msg_lines += [f"- {k.title()}" for k in kategori_list]
        msg = "\n".join(msg_lines)

        await update.message.reply_text(msg, parse_mode="Markdown")
    except Exception as e:
        logging.error(f"Error show kategori: {e}")
        await update.message.reply_text("❌ Gagal mengambil daftar kategori.")

# --- Handle Message ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    try:
        parts = text.strip().split()
        amount = int(parts[0])
        hashtag_index = next(i for i, part in enumerate(parts) if part.startswith("#"))
        description = " ".join(parts[1:hashtag_index])
        category_raw = " ".join(parts[hashtag_index:])[1:].strip().lower()

        if category_raw not in kategori_list:
            await update.message.reply_text(
                f"❌ Kategori *{category_raw}* tidak ditemukan!\n"
                f"Gunakan perintah /kategori untuk melihat daftar yang tersedia.",
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

# --- Rekap Helper ---
async def rekap_periode(update: Update, context: ContextTypes.DEFAULT_TYPE, periode: str):
    try:
        data = sheet.get_all_values()[1:]  # Skip header
        now = datetime.now()

        if periode == 'mingguan':
            start_date = now - timedelta(days=now.weekday())
        elif periode == 'bulanan':
            start_date = now.replace(day=1)
        else:
            await update.message.reply_text("❌ Periode tidak valid.")
            return

        filtered = [row for row in data if datetime.strptime(row[0], "%Y-%m-%d") >= start_date]
        total = sum(int(row[1]) for row in filtered)

        kategori_rekap = {}
        for row in filtered:
            kategori_rekap[row[3]] = kategori_rekap.get(row[3], 0) + int(row[1])

        msg_lines = [f"📊 Rekap {periode.capitalize()} (mulai {start_date.strftime('%Y-%m-%d')}):"]
        for kategori, jumlah in kategori_rekap.items():
            msg_lines.append(f"- {kategori.title()}: Rp{jumlah:,}")
        msg_lines.append(f"\nTotal: Rp{total:,}")

        await update.message.reply_text("\n".join(msg_lines))

    except Exception as e:
        logging.error(f"Error rekap {periode}: {e}")
        await update.message.reply_text("❌ Gagal membuat rekap.")

# --- Command Rekap ---
async def rekap_mingguan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await rekap_periode(update, context, 'mingguan')

async def rekap_bulanan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await rekap_periode(update, context, 'bulanan')

# --- Main Bot Entry ---
if __name__ == '__main__':
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("kategori", show_kategori))
    app.add_handler(CommandHandler("rekapminggu", rekap_mingguan))
    app.add_handler(CommandHandler("rekapbulan", rekap_bulanan))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("🤖 Bot berjalan...")
    app.run_polling()
