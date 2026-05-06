# Changelog

Semua perubahan yang signifikan pada proyek ini akan didokumentasikan di dalam file ini.

## [v1.3.0] - 2026-05-06

### ✨ Added
- **Custom Multiplication Logic**: Menambahkan *logic* khusus untuk akun Borwita Purwokerto (`NPSYS3000019163`) dan Borwita Tegal (`NPSYS3000018661`). Jika menemukan SKU `8021803` dan `8021804` pada data Distributor, *Quantity* akan otomatis dikalikan 24 sebelum masuk ke tabel komparasi.
- **Pre-Filter Distributor Data**: Menambahkan *auto-filter* saat membaca file Excel distributor. Sistem sekarang hanya akan memproses baris yang memiliki nilai `Export = 1` dan `Nama Gudang = GUDANG UTAMA`.
- **Auto-Logout Sequence**: Bot kini akan otomatis menekan tombol Logout (`id=btnLogout`) di akhir eksekusi dan secara otomatis menyetujui (Accept/Enter) *pop-up confirm logout* bawaan Javascript dari Newspage.
- **Active Account Indicator**: Menambahkan informasi nama distributor dan *User ID* yang sedang dieksekusi pada *header* terminal log (`Log - Active Account: ...`) agar lebih mudah dipantau tanpa harus *scroll* ke atas.
- **Screen Wake Lock API**: Menyelipkan *script Javascript Anti-Sleep* untuk menahan layar agar tetap menyala (*wake lock*). Ini mencegah OS *smartphone* (Android/iOS) mematikan layar atau men-*suspend* tab browser yang dapat memutus koneksi proses *adjustment*.

## [v1.2.0] - 2026-05-06

### ✨ Added
- **UI Enhancement**: Menambahkan header `<div class='box-results'>Results</div>` dengan border aksen biru elegan pada area setelah file ter-upload.
- **Smart Formatting**: Menambahkan *logic* penambahan prefix angka `0` otomatis khusus untuk 27 SKU target tertentu pada saat data Newspage dan Distributor di- *load*.

### 🔄 Changed
- **Reconciliation Logic**: Menghapus aturan `Skip (Dist 0)`. Sekarang, jika barang di Newspage bernilai 0 (atau SKU benar-benar baru/tidak ada di *master*) dan di Distributor terdapat stok, mesin akan tetap memasukkannya ke dalam antrean eksekusi dan meng- *input* selisihnya sesuai data Distributor.
- **Bot Landing Protocol**: Mengubah cara Playwright menutup *browser*. Menambahkan `time.sleep(5)` setelah mengeklik persetujuan *Save* (Yes) untuk mencegah *Race Condition* dan memastikan server Newspage berhasil merekam penyesuaian stok.

### 🛠️ Fixed
- **UI Render Bug**: Memperbaiki *bug* antarmuka di mana tombol "Compare Stock" tidak muncul otomatis setelah file distributor diunggah. Fragment sekarang melacak `file_id` dan secara otomatis memicu *full page rerun* jika bot sedang dalam posisi *idle*.
