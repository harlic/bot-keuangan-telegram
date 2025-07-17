import logging
from datetime import datetime
import os
from dotenv import load_dotenv
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters

    # --- Load Environment Variables ---
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
SPREADSHEET_NAME = os.getenv("SPREADSHEET_NAME")
KATEGORI_SHEET = os.getenv("KATEGORI_SHEET", "Kategori")
DATA_SHEET = os.getenv("DATA_SHEET", "Sheet1")

    # --- Logging ---
logging.basicConfig(level=logging.INFO)

    # --- Google Sheets Setup ---
SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
CREDS = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", SCOPE)
client = gspread.authorize(CREDS)

sheet = client.open(SPREADSHEET_NAME).worksheet(DATA_SHEET)
kategori_sheet = client.open(SPREADSHEET_NAME).worksheet(KATEGORI_SHEET)
kategori_list = [row[0].lower() for row in kategori_sheet.get_all_values()]

    # --- Bot Commands ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "Halo! Kirim catatan keuangan kamu dengan format:\n\n<jumlah> <deskripsi> #kategori\n\n"
            "Contoh:\n15000 beli kopi #makan"
        )

    # --- Handle User Input ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
        text = update.message.text

        try:
            parts = text.strip().split()
            amount = int(parts[0])
            hashtag_index = next(i for i, part in enumerate(parts) if part.startswith("#"))
            description = " ".join(parts[1:hashtag_index])
            category = parts[hashtag_index][1:].lower()

            if category not in kategori_list:
                await update.message.reply_text(
                    f"❌ Kategori *{category}* tidak ditemukan!\n"
                    f"Pastikan sesuai dengan kategori yang tersedia.",
                    parse_mode="Markdown"
                )
                return

            tanggal = datetime.now().strftime("%Y-%m-%d")
            sheet.append_row([tanggal, amount, description, category])
            await update.message.reply_text("✅ Tersimpan!")

        except ValueError:
            await update.message.reply_text("❌ Jumlah harus berupa angka di awal.")
        except StopIteration:
            await update.message.reply_text("❌ Format salah! Gunakan tanda `#kategori` di akhir.", parse_mode="Markdown")
        except Exception as e:
            logging.error(f"Error: {e}")
            await update.message.reply_text("❌ Terjadi kesalahan. Coba lagi ya!")

    # --- Main ---
    if __name__ == '__main__':
        app = ApplicationBuilder().token(BOT_TOKEN).build()

        app.add_handler(CommandHandler("start", start))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

        print("🤖 Bot berjalan...")
        app.run_polling()
