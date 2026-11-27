# Upgrade TosBot v1.13.0

Rilis ini berfokus pada dokumen. Tidak mengubah model Groq/Gemini, konfigurasi Telegram, dashboard, izin admin/terminal, atau template PDF. Tabel SQLite `document_memory` dibuat otomatis pada startup; tabel lama tidak dihapus. Snapshot tersimpan pada database runtime, bukan GitHub. Akses mengikuti scope owner/chat yang sudah digunakan draft, sehingga anggota grup yang diizinkan dapat menggunakan data grup tersebut. Jangan gunakan grup umum untuk dokumen rahasia.

## Contoh

1. Buat invoice atau penawaran biasa dan konfirmasi PDF.
2. `buat invoice terakhir` atau `buat invoice untuk PT Contoh seperti kemarin, barangnya sama tapi jumlahnya 3 unit, PO baru PO-123`.
3. Periksa draft. Koreksi jika diperlukan. Balas `sudah sesuai, buat PDF`.

Memori menyimpan nama, PIC, alamat, produk, satuan, jumlah, harga dari dokumen final. Referensi memilih dokumen terakhir yang cocok pada jenis dan chat yang sama, bukan pencarian lintas chat atau katalog global. Nama perusahaan/PIC dicocokkan secara tepat setelah normalisasi kapitalisasi/tanda baca/honorifik; PIC di beberapa perusahaan ditolak. Jika banyak item, salin dahulu lalu koreksi per nomor item. Harga, alamat dan jumlah lama mungkin tidak berlaku lagi. PO, nomor, diskon, syarat, tanggal PO dan catatan lama tidak disalin; pembayaran menggunakan default. Perubahan jumlah/harga/PO pada perintah salin harus dipisahkan koma atau titik koma (gunakan harga bulat seperti 1500000 atau 1.500.000). Gunakan `/batal` jika ingin membuang draft aktif. Dukungan typo dan Jawa terbatas pada pola yang diuji; tidak ada perubahan pada NLU admin, keuangan, pengingat.

Dokumen sebelum upgrade tidak otomatis terisi ke memori karena tabel dokumen lama hanya menyimpan metadata ringkas, bukan item dan harga. Buat dokumen baru yang benar-benar diperlukan; jangan menerbitkan ulang invoice lama hanya untuk mengisi memori. Memori merupakan salinan historis yang tersimpan sampai dikelola administrator pada database; kebijakan retensi mengikuti backup lokal. Tidak ada penghapusan riwayat melalui Telegram pada rilis ini.

## Deploy

Untuk instalasi dari release, checkout tag `v1.13.0` di clone bersih setelah tag resmi tersedia; ikuti README. Untuk VPS v1.12.3 yang sudah menerima hotfix, paket upgrade terpisah dapat mengganti hanya modul runtime yang berubah, dengan checksum, tes sementara, backup dan rollback. Periksa `systemctl status tosbot-ai -l --no-pager`, `journalctl -u tosbot-ai -n 50 --no-pager`, kemudian uji Telegram. Tidak perlu upgrade dashboard. Jangan upload database, PDF, logo, tanda tangan, token atau konfigurasi privat ke GitHub.

## Pengujian

`PYTHONPATH=src python -m unittest discover -s tests -v`

`python scripts/check_public_release.py`

Pengujian lokal tanpa Telegram/Groq/Gemini aktif; tes LangGraph dapat dilewati jika dependency tidak tersedia. Jalankan ulang pada VPS dengan venv TosBot sebelum deploy. Verifikasi manual sebelum rilis publik.
