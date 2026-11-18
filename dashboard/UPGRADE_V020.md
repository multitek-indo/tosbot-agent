# Upgrade TosBot Dashboard v0.1.0 → v0.2.0

Versi ini memperbarui dashboard web saja. Bot Telegram `tosbot-ai`, database chat, dan logo resmi invoice/penawaran tidak dimodifikasi.

## Lima fitur baru

1. **Logo dashboard** — unggah PNG/JPEG maksimal 2 MB melalui menu Pengaturan. Hanya tampil pada sidebar dan halaman login. Disimpan di `/var/lib/tosbot-dashboard/branding/dashboard-logo.png`.
2. **Nama perusahaan** — ubah melalui halaman Pengaturan. Nama tampil pada dashboard; **nama pada PDF yang dibuat setelah perubahan juga mengikuti nama baru**. PDF lama tetap seperti semula.
3. **Password minimal 10 karakter** — ganti password sendiri melalui Pengaturan menggunakan password lama; sesi akan dicabut setelah perubahan.
4. **Multi-user administrator** — tambah pengguna baru dengan hak akses dashboard yang sama. Bisa reset password dan menghapus akun lain dengan memverifikasi password sendiri.
5. **Warna biru muda** — sidebar, tombol, grafik dan halaman login bertema sky-blue.

## Penting: logo PDF tidak berubah

Logo dokumen tetap diambil dari `COMPANY_LOGO_PATH` pada `/etc/tosbot-dashboard/dashboard.env` dan digunakan oleh renderer PDF yang ada. Mengunggah logo dashboard **tidak** menyalin, mengganti, atau memodifikasi file tersebut, termasuk untuk PDF baru. Tanda tangan, rekening, logo, dan dokumen yang sudah ada tetap dipertahankan.

## Instalasi

Unggah `tosbot-dashboard-v0.2.0.zip` ke `/home/tosbot/script/ai-agent/`, lalu:

```bash
cd /home/tosbot/script/ai-agent
unzip -o tosbot-dashboard-v0.2.0.zip
cd tosbot-dashboard-v0.2.0
sudo bash install.sh
curl -fsS http://127.0.0.1:8765/healthz
sudo systemctl status tosbot-dashboard --no-pager
```

Installer otomatis mencadangkan direktori data dashboard dan konfigurasi ke `/root/tosbot-dashboard-backups/` sebelum mengganti file aplikasi. Database, akun `admin`, password lama, transaksi, dokumen, dan konfigurasi Cloudflared tetap dipakai. `tosbot-ai` tidak di-restart.

Sesudah login, buka **Pengaturan**. Jika warna lama masih tampil, gunakan `Ctrl+Shift+R` agar browser mengambil CSS/JS terbaru.

## Pemulihan / troubleshooting

```bash
sudo journalctl -u tosbot-dashboard -n 60 --no-pager
sudo ls -lh /root/tosbot-dashboard-backups/
```

Untuk reset akun admin melalui SSH (jika diperlukan):

```bash
sudo -u tosbot-dashboard /opt/tosbot-dashboard/venv/bin/python /opt/tosbot-dashboard/scripts/set_password.py
```

Jangan mengekstrak backup ke direktori produksi tanpa terlebih dahulu memastikan file dan tanggalnya: pemulihan dapat menimpa perubahan yang dibuat setelah backup. Gunakan HTTPS dan Cloudflare Access/MFA untuk dashboard yang dipublikasikan.
