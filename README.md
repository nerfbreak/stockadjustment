# 📦 Automated Stock Adjustment

Aplikasi web berbasis Python dan Streamlit yang dirancang untuk mengotomatisasi proses rekonsiliasi stok antara sistem **Newspage** dan **Distributor**, sekaligus mengeksekusi penyesuaian stok (*Stock Adjustment*) secara otomatis menggunakan Robotic Process Automation (RPA).

Terinspirasi dari alur kerja efisien ("Inspired by Kopi Mang Toni"), *tool* ini menghilangkan kebutuhan input data manual yang memakan waktu dan rentan *human error*.

## ✨ Key Features

- 📊 **Smart Reconciliation Engine:** Membandingkan data stok dari file CSV, Excel, atau ZIP secara otomatis, mencari selisih (mismatch), dan memfilter item yang tidak ada di master data.
- 🤖 **Headless RPA Bot:** Terintegrasi dengan **Playwright** untuk melakukan navigasi, login, dan injeksi data otomatis ke dalam sistem web secara *headless* (tanpa membuka jendela browser UI).
- ⚡ **Real-time Monitoring & Cyberpunk Log:** Dilengkapi dengan UI log terminal berdesain *dark mode/cyberpunk* yang melacak eksekusi bot hingga hitungan milidetik (*micro-timing*).
- 🛡️ **Auto-correction & Validation:** Mendukung *auto-formatting* nama kolom dan penanganan tipe data dinamis agar angka SKU yang diawali nol tidak hilang.
- ☁️ **Cloud-Ready:** Mendukung *deployment* penuh ke Streamlit Community Cloud.

## 🛠️ Tech Stack

- **[Python 3.9+](https://www.python.org/):** Core engine.
- **[Streamlit](https://streamlit.io/):** Frontend UI & State Management.
- **[Pandas](https://pandas.pydata.org/):** Data manipulation & aggregation.
- **[Playwright](https://playwright.dev/python/):** Web browser automation.

## 📂 Project Structure

```text
├── .streamlit/
│   └── config.toml          # Konfigurasi tema UI (Dark Mode + Custom Fonts)
├── static/                  # Folder aset statis
│   └── *.ttf                # Custom Fonts (Inter & JetBrains Mono)
├── app.py                   # Main script aplikasi
├── requirements.txt         # Library Python
├── packages.txt             # Dependensi OS Linux (libnss3, libasound2, dll)
└── users_2.csv              # Template kredensial akun
