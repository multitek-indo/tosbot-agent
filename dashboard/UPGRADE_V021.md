# Upgrade TosBot Dashboard v0.2.0 → v0.2.1

## Perubahan

1. **Pengaturan diperbaiki**: `rows.join is not a function` tidak lagi terjadi. Daftar admin ditampilkan sebagai tabel.
2. **Sidebar auto-hide**: desktop default rel ikon; hover atau fokus keyboard untuk membuka; klik ☰ di header agar tetap terbuka atau kembali otomatis. Pilihan pin disimpan di browser pengguna.
3. **Sidebar HP**: klik ☰ membuka menu geser; ketuk di luar, tekan Escape, atau pilih menu untuk menutup.
4. Logo dashboard hanya mengubah antarmuka web; logo resmi di invoice/penawaran tetap menggunakan file yang sama.

## Instalasi

Upload `tosbot-dashboard-v0.2.1.zip` ke `/home/tosbot/script/ai-agent/`, lalu dari SSH:

```bash
cd /home/tosbot/script/ai-agent
unzip -o tosbot-dashboard-v0.2.1.zip
cd tosbot-dashboard-v0.2.1
sudo bash install.sh
curl -fsS http://127.0.0.1:8765/healthz
sudo systemctl status tosbot-dashboard --no-pager
```

Installer secara otomatis membuat backup lokal di `/root/tosbot-dashboard-backups/` sebelum mengganti kode. Database v0.2.0 disimpan di `/var/lib/tosbot-dashboard/` dan tidak dihapus. Service Telegram `tosbot-ai` tidak diubah.

**Setelah upgrade**, tekan `Ctrl+Shift+R` sekali untuk memastikan aset browser baru aktif. Login menggunakan akun lama. Buka **Pengaturan** untuk menguji daftar administrator dan nama perusahaan.

Jika gagal, periksa `sudo journalctl -u tosbot-dashboard -n 60 --no-pager` dan jangan hapus database.
