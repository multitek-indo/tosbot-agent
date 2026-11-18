#!/usr/bin/env bash
set -Eeuo pipefail
[[ ${EUID} -eq 0 ]] || { echo 'Jalankan: sudo bash install.sh'; exit 1; }
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends python3 python3-venv python3-pip fonts-liberation fonts-dejavu-core ca-certificates
if ! id -u tosbot-dashboard >/dev/null 2>&1; then
  useradd --system --home /var/lib/tosbot-dashboard --shell /usr/sbin/nologin tosbot-dashboard
fi
install -d -o root -g root -m 0755 /opt/tosbot-dashboard
install -d -o root -g root -m 0755 /opt/tosbot-dashboard/app /opt/tosbot-dashboard/app/static /opt/tosbot-dashboard/vendor /opt/tosbot-dashboard/scripts
install -d -o root -g tosbot-dashboard -m 0750 /etc/tosbot-dashboard
install -d -o tosbot-dashboard -g tosbot-dashboard -m 0700 /var/lib/tosbot-dashboard /var/lib/tosbot-dashboard/pdf /var/lib/tosbot-dashboard/import /var/lib/tosbot-dashboard/import/pdf /var/lib/tosbot-dashboard/job_photos
# Upgrade-safe: stop only the dashboard web service. TosBot Telegram stays running.
if systemctl is-active --quiet tosbot-dashboard 2>/dev/null; then
  systemctl stop tosbot-dashboard
fi
if [[ -f /var/lib/tosbot-dashboard/dashboard.sqlite3 ]]; then
  install -d -o root -g root -m 0700 /root/tosbot-dashboard-backups
  BACKUP="/root/tosbot-dashboard-backups/pre-v030-$(date -u +%Y%m%dT%H%M%SZ).tar.gz"
  tar -C / -czf "$BACKUP" var/lib/tosbot-dashboard etc/tosbot-dashboard
  chmod 0600 "$BACKUP"
  echo "Backup upgrade: $BACKUP"
fi
cp -a "$SRC/app/." /opt/tosbot-dashboard/app/
cp -a "$SRC/vendor/." /opt/tosbot-dashboard/vendor/
install -o root -g root -m 0755 "$SRC/scripts/set_password.py" /opt/tosbot-dashboard/scripts/set_password.py
install -o root -g root -m 0755 "$SRC/scripts/sync_tosbot.py" /opt/tosbot-dashboard/scripts/sync_tosbot.py
install -o root -g root -m 0755 "$SRC/scripts/connect_telegram.sh" /opt/tosbot-dashboard/scripts/connect_telegram.sh
chown -R root:root /opt/tosbot-dashboard/app /opt/tosbot-dashboard/vendor /opt/tosbot-dashboard/scripts
python3 -m venv /opt/tosbot-dashboard/venv
/opt/tosbot-dashboard/venv/bin/pip install --disable-pip-version-check -r "$SRC/requirements.txt"
if [[ ! -e /etc/tosbot-dashboard/dashboard.env ]]; then
  cat > /etc/tosbot-dashboard/dashboard.env <<'ENV'
DASHBOARD_DATA_DIR=/var/lib/tosbot-dashboard
DASHBOARD_COOKIE_SECURE=true
COMPANY_NAME=PT IMA MULTITEK INDONESIA
COMPANY_CITY=Salatiga
# Isi sesuai surat perusahaan Anda bila diperlukan.
COMPANY_ADDRESS=
COMPANY_PHONE=
COMPANY_EMAIL=
COMPANY_BANK=
COMPANY_ACCOUNT=
COMPANY_ACCOUNT_NAME=
COMPANY_SIGNER=
COMPANY_LOGO_PATH=/opt/tosbot-ai/assets/logo.png
COMPANY_SIGNATURE_PATH=/opt/tosbot-ai/assets/offer-signature.png
ENV
  # Only safe business identity keys; NEVER copy Telegram/Groq/Gemini secrets.
  if [[ -f /etc/tosbot-ai/tosbot.env ]]; then
    grep -E '^COMPANY_(NAME|CITY|ADDRESS|PHONE|EMAIL|BANK|ACCOUNT|ACCOUNT_NAME|SIGNER)=' /etc/tosbot-ai/tosbot.env >> /etc/tosbot-dashboard/dashboard.env || true
  fi
fi
chown root:tosbot-dashboard /etc/tosbot-dashboard/dashboard.env
chmod 0640 /etc/tosbot-dashboard/dashboard.env
cat >/etc/systemd/system/tosbot-dashboard.service <<'UNIT'
[Unit]
Description=TosBot Operations Dashboard
Wants=network-online.target
After=network-online.target
[Service]
Type=simple
User=tosbot-dashboard
Group=tosbot-dashboard
WorkingDirectory=/opt/tosbot-dashboard
EnvironmentFile=/etc/tosbot-dashboard/dashboard.env
Environment=PYTHONPATH=/opt/tosbot-dashboard
ExecStart=/opt/tosbot-dashboard/venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8765 --workers 1 --no-access-log
Restart=on-failure
RestartSec=5
UMask=0077
NoNewPrivileges=true
PrivateTmp=true
PrivateDevices=true
ProtectSystem=strict
ProtectHome=true
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
ProtectClock=true
RestrictSUIDSGID=true
RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6
ReadWritePaths=/var/lib/tosbot-dashboard
MemoryMax=450M
TasksMax=60
[Install]
WantedBy=multi-user.target
UNIT
cat >/etc/systemd/system/tosbot-dashboard-sync.service <<'UNIT'
[Unit]
Description=Sanitized one-way TosBot to Dashboard business snapshot
[Service]
Type=oneshot
User=root
Group=root
WorkingDirectory=/opt/tosbot-dashboard
ExecStart=/opt/tosbot-dashboard/venv/bin/python /opt/tosbot-dashboard/scripts/sync_tosbot.py
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadOnlyPaths=/var/lib/tosbot-ai
ReadWritePaths=/var/lib/tosbot-dashboard/import
UNIT
cat >/etc/systemd/system/tosbot-dashboard-sync.timer <<'UNIT'
[Unit]
Description=Refresh TosBot Dashboard snapshot every 2 minutes
[Timer]
OnBootSec=1min
OnUnitActiveSec=2min
Persistent=true
Unit=tosbot-dashboard-sync.service
[Install]
WantedBy=timers.target
UNIT
systemctl daemon-reload
systemctl enable --now tosbot-dashboard-sync.timer
systemctl enable --now tosbot-dashboard
systemctl restart tosbot-dashboard
systemctl start tosbot-dashboard-sync.service || true
cat <<'MSG'

INSTALASI DASHBOARD SELESAI.
1. Password lama v0.1.0 tetap berlaku; pengguna dapat menggantinya melalui menu Pengaturan.
   Untuk pemulihan admin melalui SSH, jalankan:
   sudo -u tosbot-dashboard /opt/tosbot-dashboard/venv/bin/python /opt/tosbot-dashboard/scripts/set_password.py
2. Cek service: sudo systemctl status tosbot-dashboard --no-pager
3. Akses via Cloudflare Tunnel atau SSH tunnel pada 127.0.0.1:8765.
4. Jika hanya memakai http://localhost via SSH tunnel, set DASHBOARD_COOKIE_SECURE=false
   di /etc/tosbot-dashboard/dashboard.env lalu restart service; aktifkan lagi sebelum HTTPS.
5. Kode TosBot dan layanan tosbot-ai tidak diubah.
6. Untuk multi-user, logo, dan nama perusahaan: buka menu Pengaturan.
7. Sidebar desktop auto-hide; arahkan mouse ke deretan ikon untuk membuka, klik ☰ untuk menyematkan.
MSG

echo "Dashboard v0.3.0 siap. Untuk integrasi chatbot, setelah upgrade TosBot jalankan: sudo bash /opt/tosbot-dashboard/scripts/connect_telegram.sh"
