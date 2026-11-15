# TosBot v1.12.1 — Perbaikan Reply pesan grup

## Penyebab

Pada v1.12.0, bot hanya menganggap `@username_bot` dan `/command@username_bot` sebagai pemanggilan dalam grup. Karena itu, pesan `sudah sesuai` yang dikirim sebagai **Reply** ke pesan rancangan penawaran TosBot diabaikan sebelum sampai ke Engine.

## Perbaikan

- `@mustikasaribot pesan` tetap didukung.
- **Reply langsung** ke pesan TosBot sekarang juga diterima tanpa tambahan @mention.
- Identitas bot divalidasi berdasarkan `getMe.id` dari Telegram; tidak berdasarkan teks kutipan atau username yang bisa ditiru.
- Balasan ke anggota/bot lain, grup lain, atau topik forum yang berbeda tidak diproses.
- Perintah terminal dan root (`/sudo`, `/sh`, `apt`, dll.) tetap memerlukan @mention eksplisit; Reply saja untuk kelanjutan percakapan/dokumen.
- Alur `sudah sesuai` menggunakan draft yang sedang aktif di ruang kerja grup. Pastikan membalas **rancangan terbaru** (bukan penawaran lama), karena satu grup memakai satu draft bersama.

## Upgrade dari v1.12.0 di VPS

Unggah `tosbot-agent-v1.12.1-reply-fix.zip` ke `/home/tosbot/script/ai-agent` (bukan ke folder Git). Lalu:

```bash
sudo systemctl stop tosbot-ai
sudo mkdir -p -m 700 /root/tosbot-backups
sudo tar -czf "/root/tosbot-backups/tosbot-before-v1121-$(date +%Y%m%d-%H%M%S).tar.gz" /etc/tosbot-ai /var/lib/tosbot-ai
cd /home/tosbot/script/ai-agent/tosbot-agent-public
unzip -o ../tosbot-agent-v1.12.1-reply-fix.zip -d .
python3 scripts/check_public_release.py
PYTHONPATH=src python3 -m unittest discover -s tests
sudo bash install.sh
sudo systemctl restart tosbot-ai
sudo systemctl status tosbot-ai --no-pager
```

Pembaruan tidak mengubah file `/etc/tosbot-ai/tosbot.env`, database, atau izin grup. Installer harus dijalankan dalam checkout yang telah dibackup; jangan `git reset --hard` pada perubahan belum di-commit.

## Pengujian di grup

1. Kirim `@mustikasaribot buatkan penawaran untuk PT ABC, ...` sampai pratinjau penawaran lengkap muncul.
2. Tekan menu **Reply** pada pesan pratinjau yang dikirim oleh TosBot (bukan pada pesan pengguna).
3. Kirim **`sudah sesuai` tanpa mention**. Jika draft lengkap, TosBot seharusnya membuat PDF dan mengirimkannya ke grup.
4. Kirim `halo semua` tanpa mention dan tanpa Reply: TosBot harus diam.
5. Balas pesan anggota lain dengan `halo`: TosBot harus diam.

Jika Reply belum bekerja, jalankan `sudo journalctl -u tosbot-ai -n 80 --no-pager` dan samarkan token/API key jika muncul.

## Versioning GitHub

Rilis ini menamai `VERSION` sebagai `1.12.1`. Setelah pengujian berhasil di VPS, lakukan `git diff`, `git status`, dan review isi yang akan dipublikasi sebelum `git add`, `git commit`, `git tag v1.12.1`, dan `git push`. Jangan `git push --force` atau menyertakan konfigurasi/credential privat dalam repo publik.
