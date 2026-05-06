# 📦 Newspage Stock Compare & Adjustment Engine

Sebuah *automation tools* berbasis web untuk membandingkan dan menyesuaikan data stok antara sistem Newspage dan Distributor secara otomatis. Dibangun menggunakan **Streamlit** untuk antarmuka pengguna dan **Playwright** untuk *headless browser automation*.

**Author**: Muhammad Rizki Firdaus  
**Role**: Newspage L1 Support Lead

---

## 🚀 Fitur Utama
1. **Auto-Extraction**: Ekstraksi *Inventory Master* langsung dari server Newspage tanpa campur tangan manual.
2. **Smart Compare**: Rekonsiliasi instan antara stok Newspage dan stok fisik/sistem Distributor.
3. **Target SKU Auto-Formatting**: Otomatis mendeteksi dan menambahkan *prefix* `0` pada 27 SKU khusus agar sinkron saat komparasi.
4. **Auto-Adjustment Bot**: Menjalankan koreksi selisih stok (Mismatch) ke dalam modul *Stock Adjustment* Newspage secara otomatis menggunakan *headless Chromium*.
5. **Audit Trail**: Pencatatan riwayat eksekusi dan *credential vault* menggunakan **Supabase**.

## 🛠️ Tech Stack
- **Frontend**: Streamlit, Pandas
- **Automation**: Playwright (Sync API)
- **Database/Vault**: Supabase
- **Language**: Python 3.x

## ⚙️ Persiapan (Setup)
Pastikan Anda memiliki *secrets* Streamlit yang dikonfigurasi pada `.streamlit/secrets.toml`:
```toml
admin_user = "admin"
admin_pass = "password_anda"
SUPABASE_URL = "[https://url-supabase-anda.supabase.co](https://url-supabase-anda.supabase.co)"
SUPABASE_KEY = "kunci-anon-supabase-anda"
