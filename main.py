import logging
from datetime import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters

# --- Google Sheets Setup ---
SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
CREDS = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", SCOPE)
client = gspread.authorize(CREDS)

# Ganti dengan nama spreadsheet
sheet = client.open("Catatan Keuangan Harli").sheet1

# --- Bot Telegram ---
BOT_TOKEN = "7759992217:AAHer8egteWU0yPTyOCMzBuKw8CHEqnfeYI"

logging.basicConfig(level=logging.INFO)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Halo! Kirim catatan keuangan kamu dengan format:\n\n<jumlah> <deskripsi> #kategori\n\nContoh:\n15000 beli kopi #makan")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    try:
        parts = text.strip().split()
        amount = int(parts[0])
        hashtag_index = next(i for i, part in enumerate(parts) if part.startswith("#"))
        description = " ".join(parts[1:hashtag_index])
        category = parts[hashtag_index][1:]  # hilangkan tanda #

        tanggal = datetime.now().strftime("%Y-%m-%d")

        sheet.append_row([tanggal, amount, description, category])

        await update.message.reply_text("✅ Tersimpan!")

    except Exception as e:
        print(e)
        await update.message.reply_text("❌ Format salah! Gunakan format:\n<jumlah> <deskripsi> #kategori\nContoh:\n15000 beli kopi #makan")

if __name__ == '__main__':
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Bot berjalan...")
    app.run_polling()
