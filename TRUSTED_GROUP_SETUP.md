# TosBot v1.12.0: Trusted Group Root (SANGAT BERISIKO)

Rilis ini mengizinkan **semua anggota** grup yang telah di-allowlist untuk menjalankan perintah Linux sebagai root lewat `@mustikasaribot /sudo ...`, tanpa OTP/TOTP, dan memakai fitur bisnis (penawaran, invoice, keuangan, pengingat). Tidak ada validasi ID individu. Pesan tanpa mention diabaikan. Bot hanya memproses pengirim Telegram nyata, bukan admin anonim/channel/bot.

**RISIKO:** siapa pun yang ditambahkan ke grup, atau mengambil alih akun salah satu anggota, dapat membaca rahasia, menghapus data, mencabut akses admin lain, dan mengambil alih server sepenuhnya. Grup Telegram BUKAN pengganti SSH aman dan tidak memiliki enkripsi ujung-ke-ujung. Aktifkan HANYA bila semua anggota adalah administrator VPS yang benar-benar tepercaya, dan backup sudah diverifikasi.

## 1. Backup dan upgrade (SSH)

```bash
sudo systemctl stop tosbot-ai
sudo mkdir -p -m 700 /root/tosbot-backups
sudo tar -czf "/root/tosbot-backups/tosbot-before-v112-$(date +%Y%m%d-%H%M%S).tar.gz" /etc/tosbot-ai /var/lib/tosbot-ai
cd /home/tosbot/script/ai-agent/tosbot-agent-public
unzip -o ../tosbot-agent-v1.12.0-trusted-group.zip -d .
python3 scripts/check_public_release.py
sudo bash install.sh
```

## 2. Opt-in root oleh pengelola server (sekali saja, dari SSH)

Edit `/etc/tosbot-ai/tosbot.env`:
```ini
TELEGRAM_GROUPS_ENABLED=true
TELEGRAM_ALLOWED_GROUP_IDS=-1003733083844
TELEGRAM_TRUSTED_GROUP_ADMIN=true
```

Root broker sengaja memerlukan izin **dua lapis konfigurasi**. Buat file root-only, hanya sekali sebagai administrator VPS:

```bash
sudo install -o root -g root -m 0600 /dev/null /etc/tosbot-ai/trusted-groups.json
printf '%s\n' '{"enabled":true,"group_ids":[-1003733083844]}' | sudo tee /etc/tosbot-ai/trusted-groups.json >/dev/null
sudo chown root:root /etc/tosbot-ai/trusted-groups.json
sudo chmod 0600 /etc/tosbot-ai/trusted-groups.json
sudo systemctl restart tosbot-ai
```

`/etc/tosbot-ai/trusted-groups.json` **jangan dimasukkan ke GitHub** dan jangan dibagikan ke chat. Disabling: set `TELEGRAM_TRUSTED_GROUP_ADMIN=false` AND set `enabled:false` in root config, then restart.

## 3. Uji lewat Telegram, mention setiap kali

```
@mustikasaribot whoami
@mustikasaribot /sudo id
@mustikasaribot /sh df -h
@mustikasaribot /sudo apt-get update
@mustikasaribot /job <ID>
@mustikasaribot buat penawaran untuk PT ABC
```

`/sh` juga dijalankan sebagai root di trusted group (tidak di chat pribadi). `sudo su` mengaktifkan tampilan admin virtual; bukan shell interaktif. Perintah root tidak memerlukan approve, tidak bisa dibatalkan setelah dikirim. Jika command sedang berjalan, output dilaporkan saat job selesai. Seluruh anggota grup dapat melihat perintah maupun hasilnya. Token dan password yang muncul pada stdout dapat bocor kepada semua anggota.

## 4. GitHub

Setelah memeriksa `git diff` dan tes, commit kemudian buat tag baru `v1.12.0` di repo Anda, bukan mengubah tag rilis lama. Jangan push konfigurasi private, data pengguna, token, atau TOTP.

### Balasan (Reply) di grup — v1.12.1

Pesan grup biasa tetap diabaikan tanpa mention. Balasan langsung (*Reply*) ke pesan asli TosBot diperlakukan sebagai panggilan bot tanpa memerlukan `@mustikasaribot` lagi. Pastikan Anda memilih balasan ke pesan TosBot, bukan ke pesan anggota lain. Contohnya untuk pratinjau penawaran, gunakan Reply → `sudah sesuai`. Konfirmasi tersebut dapat menghasilkan PDF jika draft aktif sudah lengkap.
