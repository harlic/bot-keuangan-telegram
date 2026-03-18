import os
import json
import base64
import logging
import threading
import time
import requests
import calendar
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

# ================== Flask ==================
app = Flask(__name__)

@app.route("/")
def home():
    return "✅ Bot Keuangan Aktif"

@app.route("/ping")
def ping():
    return "pong"

# ================== Google Sheets ==================
def init_sheets():
    creds_dict = json.loads(base64.b64decode(encoded_json).decode("utf-8"))
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    return gspread.authorize(creds)

gc = init_sheets()
sheet_data = gc.open(SPREADSHEET_NAME).worksheet(DATA_SHEET)

# ================== Helpers ==================
def parse_amount(s: str) -> int:
    return int(s.replace(",", "").replace(".", "").strip())

def load_kategori_list():
    ks = gc.open(SPREADSHEET_NAME).worksheet(KATEGORI_SHEET)
    return [k.strip().lower() for k in ks.col_values(1)[1:] if k.strip()]

def load_budget_data():
    data = {}
    sheet = gc.open(SPREADSHEET_NAME).worksheet(BUDGET_SHEET)
    for row in sheet.get_all_values()[1:]:
        if len(row) < 3:
            continue
        bulan = row[0].strip()
        kategori = row[1].strip().lower()
        try:
            nominal = parse_amount(row[2])
            data[(bulan, kategori)] = nominal
        except:
            continue
    return data

# ================== ANALYSIS ENGINE ==================
def get_current_month_records():
    now = datetime.now()
    rows = sheet_data.get_all_values()[1:]
    results = []

    for r in rows:
        try:
            d = datetime.strptime(r[0].strip(), "%Y-%m-%d")
            if d.year == now.year and d.month == now.month:
                results.append(r)
        except:
            continue

    return results

def aggregate_by_category(records):
    result = {}
    for r in records:
        kategori = r[3].strip().lower()
        amount = parse_amount(r[1])
        result[kategori] = result.get(kategori, 0) + amount
    return result

def predict_total_spending(total_spent):
    now = datetime.now()
    day = now.day
    days_in_month = calendar.monthrange(now.year, now.month)[1]

    return int((total_spent / day) * days_in_month)

def get_spending_insights(records):
    from collections import defaultdict

    day_map = defaultdict(int)
    for r in records:
        try:
            d = datetime.strptime(r[0].strip(), "%Y-%m-%d")
            day_name = d.strftime("%A")
            day_map[day_name] += parse_amount(r[1])
        except:
            continue

    if not day_map:
        return None

    top_day = max(day_map, key=day_map.get)
    return f"Pengeluaran tertinggi terjadi di hari *{top_day}*"

def generate_alerts(category_data, budget_data, bulan_str):
    alerts = []

    for kategori, spent in category_data.items():
        budget = budget_data.get((bulan_str, kategori))
        if not budget:
            continue

        percent = spent / budget

        if percent >= 1:
            alerts.append(f"🚨 {kategori.title()} overbudget ({percent:.0%})")
        elif percent >= 0.8:
            alerts.append(f"⚠️ {kategori.title()} sudah {percent:.0%} dari budget")

    return alerts

def detect_prediction_risk(category_data, budget_data, bulan_str):
    risks = []

    for kategori, spent in category_data.items():
        budget = budget_data.get((bulan_str, kategori))
        if not budget:
            continue

        predicted = predict_total_spending(spent)

        if predicted > budget:
            risks.append(f"📉 {kategori.title()} diprediksi overbudget (Rp{predicted:,})")

    return risks

# ================== Telegram ==================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [["/rekapbulan", "/rekapminggu"], ["/kategori"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    await update.message.reply_text(
        "Halo! 👋\n\n"
        "Format input:\n"
        "`15000 kopi #makan`\n\n"
        "Gunakan tombol untuk rekap.",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def kategori_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kategori_list = load_kategori_list()
    daftar = "\n".join(f"- {k.title()}" for k in kategori_list)
    await update.message.reply_text("*Kategori:*\n" + daftar, parse_mode="Markdown")

# ================== REKAP ==================
async def rekap_bulanan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        now = datetime.now()
        start = date(now.year, now.month, 1)
        end = date(now.year, now.month + 1, 1) if now.month < 12 else date(now.year + 1, 1, 1)

        rows = sheet_data.get_all_values()[1:]
        data = []

        for r in rows:
            try:
                tanggal = datetime.strptime(r[0].strip(), "%Y-%m-%d").date()
                if start <= tanggal < end:
                    data.append(r)
            except:
                continue

        if not data:
            await update.message.reply_text("📭 Belum ada transaksi.")
            return

        per_kat = {}
        total = 0

        for r in data:
            nominal = parse_amount(r[1])
            total += nominal
            key = r[3].strip().lower()
            per_kat[key] = per_kat.get(key, 0) + nominal

        budget_data = load_budget_data()
        bulan_str = start.strftime("%Y-%m")

        msg = "📊 Rekap Bulanan:\n"
        for k, v in per_kat.items():
            budget = budget_data.get((bulan_str, k))
            if budget:
                msg += f"- {k.title()}: Rp{v:,} / Rp{budget:,}\n"
            else:
                msg += f"- {k.title()}: Rp{v:,}\n"

        msg += f"\n💰 Total: Rp{total:,}"

        # ===== ADVANCED =====
        predicted = predict_total_spending(total)
        msg += f"\n🔮 Prediksi: Rp{predicted:,}"

        insight = get_spending_insights(data)
        if insight:
            msg += f"\n📈 {insight}"

        alerts = generate_alerts(per_kat, budget_data, bulan_str)
        risks = detect_prediction_risk(per_kat, budget_data, bulan_str)

        if alerts or risks:
            msg += "\n\n⚠️ Peringatan:\n"
            for a in alerts:
                msg += f"- {a}\n"
            for r in risks:
                msg += f"- {r}\n"

        await update.message.reply_text(msg)

    except Exception as e:
        logging.error(e)
        await update.message.reply_text("❌ Error rekap.")

# ================== INPUT ==================
async def handle_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        text = update.message.text.strip()
        parts = text.split()

        amount = parse_amount(parts[0])
        hashtag_index = next(i for i, p in enumerate(parts) if p.startswith("#"))

        description = " ".join(parts[1:hashtag_index])
        kategori = " ".join(parts[hashtag_index:])[1:].lower()

        kategori_list = load_kategori_list()
        if kategori not in kategori_list:
            await update.message.reply_text("❌ Kategori tidak valid.")
            return

        tanggal = datetime.now().strftime("%Y-%m-%d")
        sheet_data.append_row([tanggal, amount, description, kategori])

        await update.message.reply_text("✅ Tersimpan")

        # ===== REAL-TIME ANALYSIS =====
        records = get_current_month_records()
        per_kat = aggregate_by_category(records)
        budget_data = load_budget_data()
        bulan_str = datetime.now().strftime("%Y-%m")

        alerts = generate_alerts(per_kat, budget_data, bulan_str)
        risks = detect_prediction_risk(per_kat, budget_data, bulan_str)

        if alerts or risks:
            msg = "⚠️ Update Keuangan:\n"
            for a in alerts:
                msg += f"- {a}\n"
            for r in risks:
                msg += f"- {r}\n"

            await update.message.reply_text(msg)

    except Exception as e:
        logging.error(e)
        await update.message.reply_text("❌ Format salah.\nContoh: `15000 kopi #makan`", parse_mode="Markdown")

# ================== RUN ==================
application = Application.builder().token(BOT_TOKEN).build()

application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("kategori", kategori_cb))
application.add_handler(CommandHandler("rekapbulan", rekap_bulanan))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_msg))

if __name__ == "__main__":
    import asyncio

    async def main():
        await application.initialize()
        await application.start()
        await application.updater.start_polling()
        await asyncio.Event().wait()

    asyncio.run(main())
