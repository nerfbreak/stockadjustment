# 📦 Newspage Stock Compare & Adjustment Engine

Sebuah *automation tools* berbasis web untuk membandingkan dan menyesuaikan data stok antara sistem Newspage dan Distributor secara otomatis. Dibangun menggunakan **Streamlit** untuk antarmuka pengguna dan **Playwright** untuk *headless browser automation*.

**Author**: Muhammad Rizki Firdaus  
**Role**: Newspage L1 Support Lead

---

## 🔒 Security & Authentication

Aplikasi ini menggunakan **bcrypt** untuk pengamanan kata sandi.

### Migrasi Kata Sandi Plaintext (Legacy)

Jika Anda memiliki data pengguna lama dengan kata sandi *plaintext* di tabel `users_auth` Supabase, Anda harus melakukan migrasi ke kata sandi terenkripsi menggunakan skrip migrasi:

1. Pastikan `.streamlit/secrets.toml` Anda memiliki `SUPABASE_URL` dan `SUPABASE_KEY` yang valid.
2. Jalankan skrip migrasi:
   ```bash
   python migrate_passwords.py
   ```
   Skrip ini akan mendeteksi kata sandi yang belum terenkripsi dan memperbaruinya secara otomatis menjadi hash bcrypt yang aman.

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
