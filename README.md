# 💰 Bot Keuangan Telegram - Versi 1.0

Bot Keuangan ini adalah **asisten pribadi pencatat pengeluaran harian berbasis Telegram** yang otomatis mencatat transaksi kamu ke Google Spreadsheet.

🚀 Proyek ini cocok untuk:
- Siapa saja yang ingin mencatat pengeluaran harian dengan praktis lewat Telegram.
- Developer yang ingin belajar integrasi antara Telegram Bot dan Google Sheets API.


## ✨ Fitur Utama

✅ **Pencatatan Pengeluaran via Chat**  
Cukup kirim pesan ke bot dengan format: 
"15000 beli kopi #jajan"
Bot akan otomatis mencatat ke Google Sheet dengan tanggal hari ini.

✅ **Validasi Kategori Otomatis**  
Kategori diambil langsung dari kolom tertentu di Google Spreadsheet. Bot akan menolak input jika kategori tidak sesuai.

✅ **Case Insensitive dan Mendukung Spasi**  
Kategori bisa ditulis tanpa memperhatikan huruf besar kecil, dan mendukung nama kategori dengan spasi.  
Contoh: #Listrik & Gas

✅ **Command Pendukung**
- `/start` – Menjelaskan cara penggunaan bot
- `/kategori` – Menampilkan daftar kategori yang tersedia
- `/rekapminggu` – Menampilkan rekap pengeluaran minggu ini per kategori
- `/rekapbulan` – Menampilkan rekap pengeluaran bulan ini per kategori

✅ **Integrasi Google Sheets**  
Semua transaksi dicatat secara real-time ke Google Spreadsheet milik kamu. Data tidak tersimpan di server pihak ketiga.


---

## 📦 Teknologi yang Digunakan

- Python 3.11
- [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot)
- [gspread](https://github.com/burnash/gspread)
- Google Service Account JSON
- Google Sheets API
- Replit (opsional untuk development)


---

## ⚙️ Setup dan Konfigurasi

Lihat [panduan lengkap di Wiki](https://github.com/harlic/bot-keuangan-telegram/wiki) atau ikuti langkah singkat berikut:

1. Buat **Google Spreadsheet** dan siapkan **Service Account JSON**.
2. Encode file JSON ke base64, lalu masukkan ke `.env` sebagai `GOOGLE_SERVICE_ACCOUNT_JSON_BASE64`.
3. Tambahkan juga `BOT_TOKEN` dan `SPREADSHEET_NAME` ke `.env`.
4. Jalankan `main.py` dan biarkan bot kamu bekerja!

---

## 📄 Contoh Format Spreadsheet

Sheet:
- `Sheet1` → tempat mencatat transaksi (`Tanggal`, `Amount`, `Deskripsi`, `Kategori`)
- `Kategori` → tempat mendefinisikan daftar kategori (bisa di kolom D)

---

## 🔒 Keamanan

⚠️ Jangan pernah upload `.env` atau `service_account.json` ke GitHub publik. Gunakan `.env.example` sebagai template untuk berbagi format variabel lingkungan.

---

# 📌 Status

🔖 Versi: **1.0 (stable)**  
📅 Rilis: Juli 2025  
👤 Author: [@harlic](https://github.com/harlic)

---

## 📸 Screenshot (opsional)

<img width="1387" height="907" alt="image" src="https://github.com/user-attachments/assets/1b4eba6e-78b0-4ef4-81ab-89bc8ba4994a" />

<img width="1360" height="357" alt="image" src="https://github.com/user-attachments/assets/4aab6d9e-123f-4bd6-8e07-ae1b60276bbb" />

<img width="863" height="441" alt="image" src="https://github.com/user-attachments/assets/dfe91d16-3f76-4e61-9da4-faebff60b549" />

<img width="896" height="570" alt="image" src="https://github.com/user-attachments/assets/8fcb8b7d-047a-4991-993b-a01191bd7df9" />


---

## 💬 Lisensi

Silakan gunakan, modifikasi, dan sebarkan sesuai kebutuhan.
