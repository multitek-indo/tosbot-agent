# TosBot v1.13.1 — kompatibilitas Gemini fallback

Perubahan kecil dari v1.13.0: default Gemini menjadi `gemini-3.1-flash-lite` pada runtime, `.env.example`, dan doctor. Groq tetap utama (`openai/gpt-oss-120b`); endpoint, mekanisme fallback, schema, dashboard, dan izin tidak berubah.

## VPS lama

Installer mempertahankan konfigurasi produksi. Jika `GEMINI_MODEL` sudah diperbarui dan `doctor.py --test-api` berhasil, tidak ada kebutuhan mendesak untuk restart atau upgrade runtime hanya demi model. Untuk menyamakan versi source, gunakan tag v1.13.1 setelah dipublikasikan, backup konsisten, dan ikuti [panduan teknisi](docs/TECHNICIAN_GUIDE_ID.md#9-upgrade-dan-rollback).

Jika model belum diperbarui: backup file env dengan izin terbatas, edit `/etc/tosbot-ai/tosbot.env` menggunakan `sudoedit`, pastikan hanya satu entri `GEMINI_MODEL=gemini-3.1-flash-lite`, dan jangan ubah key atau `AI_PRIMARY=groq`. Jalankan:

```bash
sudo /opt/tosbot-ai/venv/bin/python /opt/tosbot-ai/scripts/doctor.py --test-api
# Periksa output kedua provider secara manual (doctor exit code saja tidak cukup).
sudo systemctl restart tosbot-ai
sudo systemctl status tosbot-ai -l --no-pager
sudo journalctl -u tosbot-ai --since '2 minutes ago' --no-pager
```

Restart hanya bila kedua provider yang dikonfigurasi memberikan hasil yang diharapkan. Jika gagal, pulihkan env dari backup privat, lalu verifikasi service. Gemini opsional; jangan sengaja mengganggu Groq produksi untuk menguji fallback.

## HTTP 404 dan pengujian

List Models dapat berhasil walau Chat Completions gagal untuk model tertentu. Pada satu audit VPS (27 November 2026), `gemini-2.5-flash` dan `gemini-2.5-flash-lite` memberi HTTP 404, sedangkan `gemini-3.1-flash-lite` memberi HTTP 200 dan JSON invoice yang benar (3,5 detik). Setelah konfigurasi diubah, doctor memberi HTTP 200 pada kedua provider. Ini bukan jaminan ketersediaan model atau latensi permanen. Uji dengan key dan endpoint aktual; 429 berarti kuota/rate limit, bukan bukti model dihapus. Gunakan data fiktif dan jangan mencetak key.

Tes unit memeriksa urutan provider dan fallback dengan mock. Doctor menguji masing-masing provider, bukan perpindahan otomatis saat Groq gagal. Pengujian fallback live yang terisolasi tetap diperlukan untuk verifikasi menyeluruh.
