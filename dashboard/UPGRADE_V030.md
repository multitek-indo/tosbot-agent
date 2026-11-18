# Upgrade TosBot Dashboard v0.3.0 + Telegram Bridge

Fitur: unggah foto barang/mesin berdasarkan **nomor pekerjaan servis**; tampilkan foto di browser; chatbot Telegram mencari pekerjaan, menampilkan foto yang tepat, dan memberikan hitungan pelanggan/servis/keuangan dari sumber data yang sama.

## Instalasi tanpa menghapus data lama

Dari laptop, unggah kedua ZIP ke `/home/tosbot/script/ai-agent/` pada VPS:
- `tosbot-dashboard-v0.3.0.zip`
- `tosbot-agent-v1.12.2.zip`

Di VPS:

```bash
cd /home/tosbot/script/ai-agent
unzip -o tosbot-dashboard-v0.3.0.zip
unzip -o tosbot-agent-v1.12.2.zip -d tosbot-agent-public

# Dashboard installer melakukan backup terlebih dahulu.
cd tosbot-dashboard-v0.3.0
sudo bash install.sh

# Source agent di Git tree sekarang menjadi v1.12.2 (belum dipush GitHub).
cd ../tosbot-agent-public
python3 scripts/check_public_release.py
sudo bash install.sh

# Menghasilkan satu key rahasia untuk koneksi internal localhost.
# Key masuk ke masing-masing env tanpa ditampilkan, TIDAK ke source Git.
sudo bash /opt/tosbot-dashboard/scripts/connect_telegram.sh

curl -fsS http://127.0.0.1:8765/healthz
sudo systemctl status tosbot-dashboard tosbot-ai --no-pager
```

**Jangan** menghapus `/var/lib/tosbot-dashboard` atau `/var/lib/tosbot-ai`: data dan pengguna tetap ada. Installer tidak mengubah aset logo PDF dan tanda tangan. File foto baru di `/var/lib/tosbot-dashboard/job_photos/`; sertakan direktori ini saat membuat backup. Perubahan baru di source Git TosBot akan terlihat melalui `git status` tetapi **belum otomatis dipush**.

Jika `connect_telegram.sh` gagal, periksa **tanpa menampilkan token**: `sudo journalctl -u tosbot-dashboard -n 40 --no-pager` dan `sudo journalctl -u tosbot-ai -n 40 --no-pager` (jangan kirim log yang mengandung kredensial).

## Upload foto barang

1. Login dashboard > **Pekerjaan servis**.
2. Cari tiket (misalnya **#2**) untuk pelanggan/mesin yang sesuai.
3. Klik **📷 0 Foto** > **Pilih file** > opsional isi keterangan > **Unggah foto**.
4. JPG, PNG, dan WebP didukung. Maksimum 5 MB per file, 8 foto per tiket. File disimpan sebagai JPEG tanpa EXIF.
5. Foto dapat dibuka dan dihapus oleh semua admin dashboard.

## Tanya ke TosBot

Dalam chat pribadi pemilik atau grup trusted (gunakan `@mustikasaribot` jika tidak sedang Reply):

```
@mustikasaribot berapa jumlah pelanggan yang tercatat?
@mustikasaribot daftar pelanggan
@mustikasaribot ada berapa pekerjaan servis nya?
@mustikasaribot status servis #2
@mustikasaribot foto servis #2
@mustikasaribot kirim foto barang PT ANUGERAH ALFA LESTARI
@mustikasaribot cek keuangan hari ini
@mustikasaribot jumlah invoice
```

TosBot tidak memanggil AI untuk mengarang angka/foto tersebut; ia membaca API lokal dashboard. Bila ada beberapa tiket untuk pelanggan yang sama, bot mengembalikan pilihan **#ID**. Foto diambil dan dikirim sebagai pesan Telegram **asli**, bukan URL web. Maksimum 3 foto sekali meminta. Data chatbot bersifat read-only: membuat/edit pelanggan dan order tetap melalui dashboard. Keuangan bot menyertakan data Telegram berdasarkan snapshot yang diperbarui timer sekitar 2 menit; nilainya bukan saldo bank.

## Model akses

Dashboard menggunakan sesi web + CSRF untuk foto. Bot menggunakan kunci acak 48-byte di dua file env root-managed. Endpoints `/api/bridge/*` tidak menerima request tanpa kunci ini. Service dashboard tetap di `127.0.0.1:8765`. Hak untuk melihat foto dari Telegram dibatasi ke chat pribadi pemilik dan **trusted group** yang sudah diizinkan: anggota trusted group lain dapat melihat foto pekerjaan. Jangan unggah foto yang berisi data rahasia yang tidak boleh dibaca mereka. Folder foto dan database harus masuk rencana backup.

## Verifikasi

- `curl http://127.0.0.1:8765/healthz` mengembalikan versi `0.3.0`.
- `cat /home/tosbot/script/ai-agent/tosbot-agent-public/VERSION` menghasilkan `1.12.2`.
- Unggah satu foto ke pekerjaan #2 dan ketik `@mustikasaribot foto servis #2`.
- Bandingkan jumlah pelanggan/pekerjaan di **Ringkasan** dengan chat TosBot.

## Pemulihan

Dashboard installer membuat snapshot pra-upgrade di `/root/tosbot-dashboard-backups/`. Backup manual konfigurasi/data TosBot sebelum reinstall bot juga disarankan. Untuk mengembalikan versi lama, hentikan service terkait, pulihkan source aplikasi dan direktori database dari backup konsisten, lalu mulai kembali service. Jangan mengganti database yang sedang dipakai.
