## v0.3.0 — Foto barang & Telegram live bridge

- Upload/lihat/hapus foto berdasarkan tiket pekerjaan, maksimal 8 foto per tiket (JPG/PNG/WebP).
- Konversi JPEG tanpa EXIF, akses terlindungi sesi web + CSRF.
- API bridge live read-only dengan kunci acak untuk chatbot.
- Tidak mengubah logo PDF, tanda tangan, atau dokumen lama.
- Upgrade mempertahankan data dan seluruh akun.

# Changelog

## 0.2.1 — 18 November 2026
- Fix halaman Pengaturan gagal dengan `rows.join is not a function` akibat string yang dikirim ke helper tabel (seharusnya array).
- Sidebar desktop auto-hide: tampil sebagai rel ikon, buka otomatis pada hover/fokus keyboard, serta tombol ☰ untuk menyematkan atau melepas.
- Sidebar mobile: slide-in menu dengan backdrop, tombol menu, dan penutupan melalui Escape/navigasi.
- Pembaruan query versi CSS/JS agar cache browser lama tidak menyebabkan mismatch.
- Perubahan hanya frontend dan versi aplikasi; database, akun, logo dokumen, PDF, dan TosBot tidak diubah.

# Changelog

## v0.2.0 — 18 November 2026

- **Pengaturan**: ganti nama perusahaan; otomatis berlaku untuk judul dashboard, halaman login, dan PDF baru.
- **Logo**: unggah PNG/JPEG maksimal 2 MB, divalidasi dan disimpan sebagai PNG normalisasi, dipakai **hanya** di sidebar dan halaman login. Logo resmi PDF tetap dari `COMPANY_LOGO_PATH`, tidak ikut berubah.
- **Password**: minimal 10 karakter; perubahan melalui UI dengan verifikasi password lama; semua sesi pengguna tersebut dicabut.
- **Multi-admin**: tambah administrator dengan hak akses setara; daftar akun, reset password akun lain, hapus akun lain, dan audit tindakan sensitif.
- **Tema**: palet biru muda dengan sidebar terang, aksen biru, kompatibel layar HP.
- **Pemisahan aset**: logo dashboard di `branding/dashboard-logo.png`, tidak digunakan oleh renderer PDF.
- **Migrasi**: tabel settings baru dibuat tanpa mengubah data lama atau hash password lama.
- **Installer**: membuat backup data & konfigurasi root-only sebelum mengganti kode dan restart hanya layanan dashboard.
- **Keamanan**: tetap memakai CSRF, sesi HttpOnly, hash scrypt; operasi pengelolaan pengguna perlu verifikasi password admin saat ini; normalisasi logo.

## v0.1.0

Versi dashboard awal (CRM, order servis, dokumen, keuangan, monitoring, sinkronisasi satu arah).
