# Changelog

Semua perubahan yang signifikan pada proyek ini akan didokumentasikan di dalam file ini.

## [v1.2.0] - 2026-05-06

### ✨ Added
- **UI Enhancement**: Menambahkan header `<div class='box-results'>Results</div>` dengan border aksen biru elegan pada area setelah file ter-upload.
- **Smart Formatting**: Menambahkan *logic* penambahan prefix angka `0` otomatis khusus untuk 27 SKU target tertentu pada saat data Newspage dan Distributor di- *load*.

### 🔄 Changed
- **Reconciliation Logic**: Menghapus aturan `Skip (Dist 0)`. Sekarang, jika barang di Newspage bernilai 0 (atau SKU benar-benar baru/tidak ada di *master*) dan di Distributor terdapat stok, mesin akan tetap memasukkannya ke dalam antrean eksekusi dan meng- *input* selisihnya sesuai data Distributor.
- **Bot Landing Protocol**: Mengubah cara Playwright menutup *browser*. Menambahkan `time.sleep(5)` setelah mengeklik persetujuan *Save* (Yes) untuk mencegah *Race Condition* dan memastikan server Newspage berhasil merekam penyesuaian stok.

### 🛠️ Fixed
- **UI Render Bug**: Memperbaiki *bug* antarmuka di mana tombol "Compare Stock" tidak muncul otomatis setelah file distributor diunggah. Fragment sekarang melacak `file_id` dan secara otomatis memicu *full page rerun* jika bot sedang dalam posisi *idle*.
