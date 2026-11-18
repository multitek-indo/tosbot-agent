> **Versi 0.2.1**: memperbaiki halaman Pengaturan serta menambahkan sidebar desktop auto-hide dan menu mobile. Panduan khusus di [`UPGRADE_V021.md`](UPGRADE_V021.md).

# MULTITEK Operations Hub — TosBot Dashboard v0.2.1

**Upgrade langsung dari v0.1.0**, tanpa instal ulang database, tanpa reset password, dan tanpa mengubah service `tosbot-ai`.

> **Klarifikasi penting:** logo yang diunggah melalui menu Pengaturan hanya untuk tampilan dashboard. Logo resmi dokumen PDF tidak berubah.

## Yang baru

| Permintaan | Realisasi |
|---|---|
| Upload/ganti logo | Menu **Pengaturan → Logo dashboard**, PNG/JPEG ≤2 MB; **hanya** untuk sidebar dan halaman login, **tidak** memengaruhi PDF |
| Ganti nama perusahaan | Menu **Pengaturan → Identitas perusahaan**; otomatis dipakai pada dokumen PDF baru |
| Password minimal 10 karakter | **Pengaturan → Ganti password saya**; wajib memasukkan password lama; logout seluruh sesi setelah perubahan |
| Tambah admin setara | **Pengaturan → Administrator dashboard**; tambah, reset password, dan hapus akun lain; setiap user bisa mengakses seluruh menu |
| Warna biru muda | Tema Sky Blue, sidebar terang dan tombol biru; responsif desktop/HP |

Semua administrator memiliki **hak akses aplikasi yang sama**, termasuk mengelola admin lain. Tidak ada akses shell/root Linux melalui dashboard; pengaturan web terpisah dari trusted group Telegram.

## Upgrade yang aman di VPS TosBos

Jangan hapus direktori `/var/lib/tosbot-dashboard` dan `/etc/tosbot-dashboard`. Letakkan ZIP di `/home/tosbot/script/ai-agent/` dan jalankan:

```bash
cd /home/tosbot/script/ai-agent
unzip -o tosbot-dashboard-v0.2.1.zip
cd tosbot-dashboard-v0.2.1
sudo bash install.sh
```

Installer akan menghentikan **hanya** `tosbot-dashboard`, menyimpan backup sebelum mengganti kode di `/root/tosbot-dashboard-backups/` (izin root-only), mempertahankan database lama dan `dashboard.env`, menginstal file baru ke `/opt/tosbot-dashboard`, lalu memulai ulang dashboard. `tosbot-ai` tidak disentuh. Struktur tabel lama tetap, tabel `settings` ditambahkan secara idempotent.

Cek:

```bash
curl -fsS http://127.0.0.1:8765/healthz
sudo systemctl status tosbot-dashboard --no-pager
sudo journalctl -u tosbot-dashboard -n 40 --no-pager
```

Respon `healthz` harus memuat `"version":"0.2.1"`. Buka kembali alamat dashboard via HTTPS; gunakan tombol **Ctrl+Shift+R** jika browser masih menampilkan stylesheet lama. Password `admin` lama tetap berlaku.

## Penggunaan fitur baru

1. Login dengan akun `admin` yang ada. Pilih **Pengaturan** di sidebar.
2. Di bagian **Identitas perusahaan**, ubah nama. Perubahan ini tidak otomatis mengubah nama rekening, alamat atau histori PDF yang sudah diterbitkan. PDF **baru** menggunakan nama terbaru.
3. Di **Logo dashboard**, pilih PNG/JPEG yang valid ≤2 MB. Logo khusus web disimpan di `/var/lib/tosbot-dashboard/branding/dashboard-logo.png`. Logo invoice/penawaran/PDF, baik lama maupun baru, **tetap dari aset `COMPANY_LOGO_PATH`** pada `/etc/tosbot-dashboard/dashboard.env`.
4. Di **Ganti password saya**, isi password saat ini dan password baru minimal 10 karakter dua kali. Anda otomatis keluar, lalu login ulang.
5. Di **Administrator dashboard**, masukkan username baru, password pengguna minimal 10 karakter, dan password admin Anda saat ini. Setiap akun baru dapat login dengan username tersebut dan memperoleh hak admin yang sama. Administrator bisa mereset password akun lain dan menghapus akun lain, tetapi tidak menghapus diri sendiri.

**Keamanan**: Password minimal 10 karakter adalah batas teknis, bukan jaminan kekuatan. Gunakan password panjang dan unik serta Cloudflare Access/MFA. Jangan bagikan password antar pengguna; buat akun terpisah agar audit log menampilkan pengelola yang beroperasi.

## Database dan kompatibilitas

- Database web tetap `/var/lib/tosbot-dashboard/dashboard.sqlite3`; data pelanggan, servis, invoice, transaksi, dan password lama dipertahankan.
- Konfigurasi sensitif tetap `/etc/tosbot-dashboard/dashboard.env` dan tidak dimasukkan ZIP.
- Nama perusahaan yang disimpan di dashboard kini menjadi prioritas dibanding `COMPANY_NAME` di `dashboard.env`; field invoice lain tetap dari env.
- Logo yang diunggah ke dashboard **tidak pernah** dipakai untuk PDF. `COMPANY_LOGO_PATH` dari `dashboard.env` tetap menjadi sumber logo resmi invoice/penawaran; tanda tangan tetap memakai aset asli yang dikonfigurasi.
- Sinkronisasi bisnis Telegram → dashboard tetap **satu arah**, kira-kira setiap 2 menit. Perubahan pelanggan dan servis web belum dapat ditanyakan langsung lewat bot Telegram.
- Tidak ada akun default baru atau password default.

## Restore dari backup installer jika upgrade gagal

Lihat nama backup yang tersedia:

```bash
sudo ls -lh /root/tosbot-dashboard-backups/
```

Sebelum memulihkan, hentikan dashboard, salin arsip backup ke lokasi lain, dan periksa isi arsipnya. Restore database dari arsip akan **menimpa perubahan setelah backup**, jadi jangan langsung ekstrak tanpa memastikan file yang ingin dipulihkan.

## Pengujian lokal

Dengan dependensi di `requirements.txt` terpasang dan `pytest` tersedia:

```bash
python -m pytest -q tests/
```

Layanan bind `127.0.0.1:8765`, gunakan Cloudflare Access + MFA untuk domain HTTPS publik. Jangan mengekspos port ke `0.0.0.0` tanpa perlindungan. Lihat `README.md` versi lama untuk rincian sinkronisasi, template PDF, dan konfigurasi perusahaan.


## v0.3.0: Foto servis + integrasi Telegram

Lihat `UPGRADE_V030.md` untuk upgrade dua aplikasi dan aktivasi kunci bridge lokal. Fitur foto tersedia di menu Pekerjaan servis, data foto ada di `/var/lib/tosbot-dashboard/job_photos/` dan bukan pada PDF maupun logo dokumen.
