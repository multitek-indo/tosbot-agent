# TosBot v1.12.2 — live dashboard bridge

- Query CRM, order servis, status, foto mesin, ringkasan finance, serta total dokumen kini mengambil data **langsung** dari Dashboard v0.3.0.
- Pengiriman foto melalui Telegram sendPhoto multipart, maksimal 3 gambar per permintaan, tanpa mengunggah foto baru ke server luar selain Telegram yang digunakan pengguna.
- Untuk multiple job matching bot memberi daftar ID; tidak memilih foto secara acak.
- Tidak mengubah alur PDF, root broker, grup mention-only, ataupun data SQLite TosBot.
- Data read-only. Order dan pelanggan baru tetap dimasukkan lewat dashboard.
- Membutuhkan `TOSBOT_DASHBOARD_BRIDGE_TOKEN` di `/etc/tosbot-ai/tosbot.env`; konfigurasi ini dibuat oleh skrip `sudo bash /opt/tosbot-dashboard/scripts/connect_telegram.sh` setelah dashboard v0.3.0 dipasang.
- Gunakan `dashboard-v0.3.0/UPGRADE_V030.md` untuk instruksi pemasangan lengkap.

Perlu diketahui: hanya chat pribadi pemilik dan trusted group yang telah diizinkan bisa membaca data/foto bridge. Data keuangan yang berasal dari database Telegram masih melalui snapshot sinkronisasi tiap ±2 menit.
