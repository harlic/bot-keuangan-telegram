# 🤖 Bot Telegram Pencatat Pengeluaran

Bot Telegram sederhana yang mencatat pengeluaran harian ke Google Spreadsheet menggunakan Python + Google Sheets API.

---

## 📌 Fitur

- Kirim pengeluaran via Telegram bot:
15000 beli kopi #makan

markdown
Copy
Edit
- Bot akan menyimpan ke Google Spreadsheet:
- Tanggal (otomatis)
- Amount
- Deskripsi
- Kategori
- Perintah khusus:
- `/start` – petunjuk penggunaan
- `/minggu` – total pengeluaran minggu ini
- `/bulan` – total pengeluaran bulan ini

---

## 🚀 Cara Menjalankan

### 1. Siapkan Google Spreadsheet
- Buat file Google Sheet dengan nama: `Catatan Keuangan Harli`
- Tambahkan header di baris 1: `Tanggal | Amount | Deskripsi | Kategori`

### 2. Buat kredensial Google API
- Aktifkan Google Sheets API & Google Drive API
- Buat **Service Account** dan download file `credentials.json`
- Share Spreadsheet ke email service account (akses Editor)

### 3. Siapkan Bot Telegram
- Buat bot lewat [@BotFather](https://t.me/BotFather)
- Salin **API Token**

### 4. Jalankan Bot
Install dependensi:
```bash
pip install python-telegram-bot gspread oauth2client
Jalankan:

bash
Copy
Edit
python main.py
⚠️ Keamanan
Pastikan file credentials.json tidak diupload ke GitHub. Sudah diabaikan lewat .gitignore.

📄 Contoh Input ke Bot
arduino
Copy
Edit
12000 beli pulsa #komunikasi
Bot akan otomatis simpan ke spreadsheet.

📚 Teknologi
Python

python-telegram-bot

gspread

Google Sheets API + Drive API

yaml
Copy
Edit
