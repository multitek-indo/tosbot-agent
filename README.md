# TosBot AI Agent + MULTITEK Operations Dashboard

**Rilis terintegrasi:** TosBot AI Agent **v1.12.3** · Dashboard Web **v0.3.0**

**Repository:** [multitek-indo/tosbot-agent](https://github.com/multitek-indo/tosbot-agent)  
**Platform:** Ubuntu VPS · Telegram · Python · SQLite

TosBot adalah asisten operasional berbasis Telegram untuk mengelola VPS dan pekerjaan bisnis. Dashboard web menyediakan tampilan untuk pelanggan, pekerjaan servis, foto barang/mesin, dokumen, keuangan, dan monitoring VPS. **Data pelanggan, tiket servis, dan foto yang dijawab TosBot diambil dari Dashboard melalui API lokal dengan akses baca saja**, sehingga bot tidak perlu menebak informasi tersebut.

> **Status:** README ini menjelaskan source **v1.12.3/v0.3.0**. Fitur integrasi membutuhkan **kedua aplikasi** terpasang dan dihubungkan menggunakan `connect_telegram.sh`. Kode yang sudah di-push ke GitHub tidak otomatis memasang pembaruan pada VPS lain.

## Daftar isi

- [Fitur](#fitur)
- [Struktur repository](#struktur-repository)
- [Persyaratan](#persyaratan)
- [Instalasi baru di Ubuntu VPS](#instalasi-baru-di-ubuntu-vps)
- [Upgrade instalasi lama](#upgrade-instalasi-lama)
- [Integrasi Dashboard dan Telegram](#integrasi-dashboard-dan-telegram)
- [Penggunaan Telegram dan foto servis](#penggunaan-telegram-dan-foto-servis)
- [Mode grup Telegram dan izin administrator](#mode-grup-telegram-dan-izin-administrator)
- [Lokasi konfigurasi dan data](#lokasi-konfigurasi-dan-data)
- [Backup, keamanan, dan troubleshooting](#backup-keamanan-dan-troubleshooting)
- [Pengujian dan rilis](#pengujian-dan-rilis)

## Fitur

| Komponen | Kemampuan |
|---|---|
| **TosBot AI Agent v1.12.3** | Chat natural Bahasa Indonesia, Groq sebagai utama, Gemini cadangan, checkpoint LangGraph, perintah server, pengingat, keuangan, penawaran dan invoice PDF |
| **Telegram grup** | Mention `@bot` dan Reply langsung ke pesan bot; diagnostik grup terbatas; mode trusted group opsional |
| **Dashboard v0.3.0** | Login multi-admin, pengaturan identitas perusahaan, logo *khusus web*, password minimal 10 karakter, sidebar auto-hide dan tema biru muda |
| **Pelanggan & servis** | Pelanggan/PIC, mesin, kerusakan, teknisi, jadwal, status, estimasi pekerjaan |
| **Foto pekerjaan** | Maksimal 8 foto per tiket; JPG/PNG/WebP hingga 5 MB/file; disimpan ulang sebagai JPEG tanpa metadata EXIF |
| **Live bridge** | TosBot membaca pelanggan, tiket, status, foto, dokumen, dan ringkasan keuangan via API lokal yang dilindungi token; foto dikirim dengan `sendPhoto` Telegram |
| **Sinkronisasi lama** | Transaksi/dokumen/pengingat dari database TosBot disalin ke dashboard secara periodik (sekitar 2 menit), bukan sinkron dua arah penuh |

**Batasan saat ini:** pembuatan/perubahan data pelanggan dan pekerjaan servis dilakukan di dashboard; jembatan Telegram v1.12.2 untuk data tersebut **hanya-baca**. Transaksi yang berasal dari TosBot dapat tampil di dashboard setelah proses sinkronisasi, sehingga pembaruan tidak selalu seketika.

## Struktur repository

```text
tosbot-agent/
├── README.md                  # Dokumentasi utama ini
├── VERSION                    # Versi agent: 1.12.3
├── CHANGELOG.md
├── .env.example               # Contoh, tanpa kredensial nyata
├── install.sh                 # Installer TosBot
├── src/tosbot_ai/             # Source TosBot, termasuk business_bridge.py
├── scripts/                   # Pemeriksaan dan alat administrasi
├── tests/
├── assets/README.md           # Cara memasang logo/tanda tangan dokumen secara privat
├── UPGRADE_V1122.md           # Panduan perubahan agent 1.12.2
├── TRUSTED_GROUP_SETUP.md     # Peringatan dan setup trusted group
└── dashboard/
    ├── VERSION                # Versi dashboard: 0.3.0
    ├── install.sh             # Installer dashboard terpisah
    ├── app/                   # Backend FastAPI dan antarmuka web
    ├── scripts/
    │   ├── connect_telegram.sh
    │   ├── set_password.py
    │   └── sync_tosbot.py
    ├── tests/
    └── UPGRADE_V030.md        # Panduan integrasi terbaru
```

Tag Git: **`v1.12.3`** untuk agent dan **`dashboard-v0.3.0`** untuk dashboard. Jika kedua tag diterbitkan pada commit yang sama, keduanya mereferensikan paket source terintegrasi yang sama. File dalam `dashboard/` **bukan** bagian dari instalasi service `tosbot-ai`; dashboard dipasang dan dijalankan sebagai service terpisah.

## Persyaratan

- VPS Ubuntu dengan `sudo`, Python 3, dan akses Internet untuk memasang dependensi.
- Token bot Telegram, ID pemilik, serta API key Groq; Gemini dapat digunakan sebagai cadangan.
- Domain HTTPS + Cloudflare Access/MFA (disarankan) jika dashboard diakses melalui Internet. Alternatif: SSH/Tailscale tunnel.
- Logo/tanda tangan asli untuk dokumen PDF, bila diperlukan. Aset privat ini disediakan **terpisah** dari repository publik.

## Instalasi baru di Ubuntu VPS

Contoh ini menginstal repository ke **`/home/tosbot/script/ai-agent/tosbot-agent-public`**, sehingga kompatibel dengan struktur pada VPS TosBos. Untuk VPS baru, pastikan folder target belum berisi instalasi lain.

### A. Unduh source pada tag yang ditentukan

```bash
sudo apt-get update
sudo apt-get install -y git
sudo mkdir -p /home/tosbot/script/ai-agent
sudo git clone https://github.com/multitek-indo/tosbot-agent.git \
  /home/tosbot/script/ai-agent/tosbot-agent-public
cd /home/tosbot/script/ai-agent/tosbot-agent-public
sudo git fetch --tags
sudo git checkout v1.12.3
cat VERSION                     # 1.12.3
cat dashboard/VERSION           # 0.3.0
```

`git checkout` pada tag menghasilkan **detached HEAD**, dan ini normal untuk deployment versi tetap. Jangan menjalankan `git pull` ketika berada pada tag; gunakan alur upgrade di bawah.

### B. Instal TosBot Telegram

```bash
sudo bash install.sh
sudo nano /etc/tosbot-ai/tosbot.env
```

Isi variabel nyata sesuai kebutuhan (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_OWNER_ID`, `GROQ_API_KEY`, opsional `GEMINI_API_KEY`, identitas perusahaan, dan pengaturan grup). **Jangan menaruh API key asli di source Git.** Contoh variabel ada di [`.env.example`](.env.example).

```bash
sudo systemctl start tosbot-ai
sudo systemctl status tosbot-ai --no-pager
```

### C. Instal Dashboard Web

```bash
cd /home/tosbot/script/ai-agent/tosbot-agent-public/dashboard
sudo bash install.sh

# Buat password admin awal jika belum pernah dibuat:
sudo -u tosbot-dashboard /opt/tosbot-dashboard/venv/bin/python \
  /opt/tosbot-dashboard/scripts/set_password.py

curl -fsS http://127.0.0.1:8765/healthz
sudo systemctl status tosbot-dashboard --no-pager
```

Endpoint kesehatan seharusnya menampilkan versi dashboard `0.3.0`. Buka melalui SSH tunnel/Tailscale, atau sambungkan **Cloudflare Tunnel** ke `http://127.0.0.1:8765` dengan akses HTTPS yang dilindungi.

> **Password dashboard:** minimal **10 karakter** untuk pengaturan akun versi terkini. Setiap administrator dashboard mempunyai izin aplikasi yang sama; itu **tidak** sama dengan akses root Linux.

### D. Hubungkan kedua layanan

```bash
sudo bash /opt/tosbot-dashboard/scripts/connect_telegram.sh
curl -fsS http://127.0.0.1:8765/healthz
sudo systemctl status tosbot-dashboard tosbot-ai --no-pager
```

Skrip tersebut membuat/menyamakan kunci privat di dua file konfigurasi dan menyalakan ulang service. Karena service mungkin belum siap segera setelah restart, pesan `curl: (7) ... port 8765` bisa terjadi meskipun service berhasil hidup. **Periksa status dan ulangi health check**; jangan menganggap API bridge berhasil hanya berdasarkan status `active`. Periksa jawaban nyata dari bot pada bagian [Penggunaan Telegram dan foto servis](#penggunaan-telegram-dan-foto-servis).

## Upgrade instalasi lama

**Backup data terlebih dahulu.** Untuk backup konsisten yang sederhana, hentikan kedua service sebelum membuat arsip direktori data dan konfigurasi (atau gunakan mekanisme online-backup SQLite yang konsisten). Sertakan folder foto. Contoh penghentian sementara:

```bash
sudo systemctl stop tosbot-ai tosbot-dashboard
sudo mkdir -p -m 700 /root/tosbot-backups
sudo tar -C / -czf \
  "/root/tosbot-backups/tosbot-full-$(date +%Y%m%d-%H%M%S).tar.gz" \
  etc/tosbot-ai etc/tosbot-dashboard var/lib/tosbot-ai var/lib/tosbot-dashboard
sudo systemctl start tosbot-ai tosbot-dashboard
```

Di clone Git yang sudah ada, periksa perubahan lokal **sebelum** beralih versi. Jangan memakai `git reset --hard` untuk mengatasi konflik karena dapat menghapus pekerjaan yang belum di-commit.

```bash
cd /home/tosbot/script/ai-agent/tosbot-agent-public
sudo git status --short
sudo git fetch origin --tags
sudo git checkout v1.12.3
sudo bash install.sh
sudo bash dashboard/install.sh
sudo bash /opt/tosbot-dashboard/scripts/connect_telegram.sh
sudo systemctl restart tosbot-ai tosbot-dashboard
```

Jika `git checkout` ditolak karena perubahan lokal, tinjau dan simpan perubahan tersebut terlebih dahulu. **Source baru tidak otomatis mengubah konfigurasi produksi**, sehingga periksa pengaturan pada file `.env` pribadi setelah upgrade.

## Integrasi Dashboard dan Telegram

Dashboard bertindak sebagai sumber data utama untuk pelanggan, tiket servis, dan foto. TosBot memanggil API **read-only** di `127.0.0.1:8765` dengan token internal yang disimpan di:

- `/etc/tosbot-dashboard/dashboard.env` → `DASHBOARD_BRIDGE_TOKEN`
- `/etc/tosbot-ai/tosbot.env` → `TOSBOT_DASHBOARD_BRIDGE_TOKEN` dan `TOSBOT_DASHBOARD_URL`

**Jangan menampilkan, menyalin ke chat, atau commit nilai token tersebut.** API bridge tidak memerlukan password akun dashboard, tetapi hanya melayani request yang memiliki token yang sesuai. Semua administrator web dapat mengelola data di aplikasi; akses bot ke foto/data bisnis tetap dibatasi pada **chat pribadi pemilik dan trusted group yang disetujui**.

**Pemisahan identitas:** logo yang diunggah dari halaman Pengaturan hanya memengaruhi **logo tampilan dashboard** (login/sidebar), **bukan** logo resmi penawaran/invoice. Logo PDF berasal dari aset yang ditentukan oleh `COMPANY_LOGO_PATH`; perubahan **nama perusahaan** di dashboard dapat memengaruhi dokumen PDF baru yang dibuat dari dashboard.

## Penggunaan Telegram dan foto servis

Contoh dari **chat pribadi pemilik** (di grup trusted, awali dengan `@mustikasaribot`):

```text
berapa jumlah pelanggan yang tercatat?
daftar pelanggan
ada berapa pekerjaan servis?
status servis #2
foto servis #2
kirim foto barang PT ANUGERAH ALFA LESTARI
cek keuangan hari ini
jumlah invoice
```

Untuk mengunggah foto:

1. Masuk dashboard → **Pekerjaan servis**.
2. Buka tiket yang benar (contoh `#2`) → **Foto barang**.
3. Unggah foto JPG/PNG/WebP (maksimum 5 MB/file dan 8 foto/tiket), lalu simpan keterangan bila diperlukan.
4. Kirim `foto servis #2` ke TosBot. Bot mengirim maksimal **3 foto per permintaan** sebagai lampiran Telegram.

Jika pencarian cocok dengan beberapa tiket, bot meminta ID tiket yang spesifik. Foto tetap disimpan sebagai file bisnis privat; **tidak masuk repository GitHub**. Foto yang dikirim ke grup dapat dilihat anggota grup tersebut.

Reply langsung ke pesan bot dapat digunakan untuk percakapan lanjutan atau konfirmasi draft PDF (`sudah sesuai`). Reply ke pengguna lain tidak memanggil bot. **Perintah `/sh` dan `/sudo` tetap memerlukan mention eksplisit di grup.**

## Mode grup Telegram dan izin administrator

Grup **nonaktif secara default**. Konfigurasi melalui `/etc/tosbot-ai/tosbot.env`:

```ini
TELEGRAM_GROUPS_ENABLED=true
TELEGRAM_ALLOWED_GROUP_IDS=-1001234567890
TELEGRAM_GROUP_OPERATIONS_ENABLED=true
```

Angka tersebut hanya **contoh**; ganti dengan ID grup yang benar. Gunakan allowlist grup agar bot tidak melayani grup lain secara tidak sengaja. Perilaku dasar: percakapan AI dan pemeriksaan VPS tertentu; **tidak ada root shell bebas**. Anggota dapat melakukan mention, dan Reply ke pesan bot yang sesuai juga didukung.

**Mode trusted group administrator bersifat opsional dan berisiko sangat tinggi.** Semua anggota grup yang diizinkan dapat mengakses fitur bisnis dan mengirim perintah root tanpa OTP. Keamanan seluruh VPS bergantung pada setiap akun anggota dan siapa pun yang bisa ditambahkan ke grup. Jangan aktifkan pada grup yang tidak sepenuhnya Anda kelola. Mode ini membutuhkan **dua konfigurasi eksplisit**: `TELEGRAM_TRUSTED_GROUP_ADMIN=true` pada `.env` dan file root-owned `/etc/tosbot-ai/trusted-groups.json` berizin `0600`. Ikuti [TRUSTED_GROUP_SETUP.md](TRUSTED_GROUP_SETUP.md), bukan hanya mengubah satu flag.

> **Rekomendasi keamanan:** pertahankan perintah root berisiko pada jalur dengan persetujuan eksplisit. Grup Telegram bukan pengganti autentikasi server. Jangan mengirim token atau data pelanggan rahasia ke grup.

## Lokasi konfigurasi dan data

| Komponen | Lokasi produksi |
|---|---|
| Source Git | `/home/tosbot/script/ai-agent/tosbot-agent-public/` |
| Agent terpasang | `/opt/tosbot-ai/` |
| Konfigurasi agent | `/etc/tosbot-ai/tosbot.env` |
| Database dan dokumen TosBot | `/var/lib/tosbot-ai/` |
| Aset PDF privat | `/opt/tosbot-ai/assets/` |
| Dashboard terpasang | `/opt/tosbot-dashboard/` |
| Konfigurasi dashboard | `/etc/tosbot-dashboard/dashboard.env` |
| Database/dashboard PDF/foto | `/var/lib/tosbot-dashboard/` |
| Foto servis | `/var/lib/tosbot-dashboard/job_photos/` |
| Service Telegram | `tosbot-ai.service` |
| Service web | `tosbot-dashboard.service` |
| Timer sinkronisasi | `tosbot-dashboard-sync.timer` |

Jangan menghapus folder produksi saat upgrade. Installer dimaksudkan mempertahankan data dan konfigurasi. Tetap buat backup dan uji restore secara berkala.

## Backup, keamanan, dan troubleshooting

**Yang tidak boleh di-commit:** `.env` asli, `dashboard.env`, `trusted-groups.json`, token Telegram/Groq/Gemini, database SQLite, data pelanggan, PDF bisnis, foto servis, logo/tanda tangan asli, dan kunci SSH/TOTP. Cek `git status` dan `git diff --cached` sebelum push.

**Pemeriksaan service:**

```bash
sudo systemctl status tosbot-ai tosbot-dashboard --no-pager
sudo systemctl status tosbot-dashboard-sync.timer --no-pager
curl -fsS http://127.0.0.1:8765/healthz
sudo journalctl -u tosbot-ai -n 40 --no-pager
sudo journalctl -u tosbot-dashboard -n 40 --no-pager
```

Sanitasi log sebelum membagikannya: baris error dapat mengandung ID pelanggan, path internal, atau konfigurasi. Cegah port web terbuka langsung ke Internet; aplikasi dibatasi ke `127.0.0.1:8765`. Gunakan HTTPS, Cloudflare Access/MFA, dan akun admin berbeda untuk setiap orang. Untuk akses web lokal via HTTP, periksa pengaturan `DASHBOARD_COOKIE_SECURE` (jangan mematikannya untuk HTTPS publik).

Jika bot menjawab informasi berbeda dari dashboard, periksa service, kunci bridge dan apakah data yang ditanyakan merupakan **data live pelanggan/servis** atau **salinan transaksi/dokumen yang baru disinkronkan setiap ±2 menit**.

## Pengujian dan rilis

Dari root repository:

```bash
python3 scripts/check_public_release.py
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Untuk dashboard, dari folder `dashboard/` dengan environment pengujian dan dependensi yang sesuai:

```bash
python3 -m pytest -q tests/
```

Pengujian lokal tidak membuktikan Telegram, Groq/Gemini, akses privileged, dan Cloudflare benar-benar bekerja pada VPS produksi. Selalu uji koneksi langsung setelah deploy.

- [CHANGELOG.md](CHANGELOG.md): riwayat agent.
- [UPGRADE_V1122.md](UPGRADE_V1122.md): pembaruan agent.
- [dashboard/UPGRADE_V030.md](dashboard/UPGRADE_V030.md): foto servis dan jembatan dashboard.
- [PUBLISH.md](PUBLISH.md): proses publikasi Git.
- [TRUSTED_GROUP_SETUP.md](TRUSTED_GROUP_SETUP.md): izin grup berisiko tinggi.

**Lisensi:** belum dicantumkan pada repository ini; jangan mengasumsikan source publik otomatis memberikan izin pemakaian ulang dengan lisensi tertentu.
