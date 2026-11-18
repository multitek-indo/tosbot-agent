#!/usr/bin/env bash
set -Eeuo pipefail
# Source should be in /home/tosbot/script/ai-agent ; runtime is installed in FHS dirs.
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
[[ "$EUID" -eq 0 ]] || { echo "Jalankan: sudo bash install.sh"; exit 1; }
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends python3 python3-venv python3-pip fonts-dejavu-core fonts-liberation sudo ca-certificates iputils-ping tree
if ! id -u tosbot-ai >/dev/null 2>&1; then
  useradd --system --home /var/lib/tosbot-ai --shell /usr/sbin/nologin tosbot-ai
fi
# Isolated shell account: NOT a sudoer and cannot read /etc/tosbot-ai/tosbot.env.
if ! id -u tosbot-terminal >/dev/null 2>&1; then
  useradd --system --home /var/lib/tosbot-terminal --shell /usr/sbin/nologin tosbot-terminal
fi
install -d -o tosbot-terminal -g tosbot-terminal -m 0700 /var/lib/tosbot-terminal
# Both directories must have ROOT-OWNED parents, never be children of a bot-writable dir.
install -d -o root -g root -m 0700 /var/lib/tosbot-ai-admin /var/lib/tosbot-ai-admin/jobs
cat > /etc/tmpfiles.d/tosbot-ai-admin.conf <<'TMP'
d /run/tosbot-ai-admin 0700 root root -
TMP
systemd-tmpfiles --create /etc/tmpfiles.d/tosbot-ai-admin.conf
install -d -o root -g root -m 0755 /opt/tosbot-ai /opt/tosbot-ai/src /opt/tosbot-ai/assets /opt/tosbot-ai/scripts
install -d -o root -g tosbot-ai -m 0750 /etc/tosbot-ai
install -d -o tosbot-ai -g tosbot-ai -m 0750 /var/lib/tosbot-ai /var/lib/tosbot-ai/documents
install -d -o tosbot-ai -g tosbot-ai -m 0750 /var/log/tosbot-ai
rm -rf /opt/tosbot-ai/src/tosbot_ai
cp -a "$SRC/src/tosbot_ai" /opt/tosbot-ai/src/
# Private logos are deliberately NOT part of the public repository.
# If already installed, preserve them across upgrades.
if [[ -f "$SRC/assets/logo.png" ]]; then
  install -o root -g root -m 0644 "$SRC/assets/logo.png" /opt/tosbot-ai/assets/logo.png
fi
# Tanda tangan asli hanya untuk surat penawaran (tidak ditambah ke invoice).
# Private signature must be provisioned separately on a trusted VPS.
if [[ -f "$SRC/assets/offer-signature.png" ]]; then
  install -o root -g root -m 0644 "$SRC/assets/offer-signature.png" /opt/tosbot-ai/assets/offer-signature.png
fi
install -o root -g root -m 0755 "$SRC/scripts/doctor.py" /opt/tosbot-ai/scripts/doctor.py
install -o root -g root -m 0755 "$SRC/scripts/check_langgraph.py" /opt/tosbot-ai/scripts/check_langgraph.py
install -o root -g root -m 0755 "$SRC/scripts/audit-vps.sh" /opt/tosbot-ai/scripts/audit-vps.sh
chown -R root:root /opt/tosbot-ai/src /opt/tosbot-ai/assets
python3 -m venv /opt/tosbot-ai/venv
/opt/tosbot-ai/venv/bin/python -m pip install --no-cache-dir --upgrade pip
/opt/tosbot-ai/venv/bin/python -m pip install --no-cache-dir -r "$SRC/requirements.txt"
if [[ ! -e /etc/tosbot-ai/tosbot.env ]]; then
  cp "$SRC/.env.example" /etc/tosbot-ai/tosbot.env
  echo 'Edit /etc/tosbot-ai/tosbot.env dan isi 4 setting penting.'
fi
chown root:tosbot-ai /etc/tosbot-ai/tosbot.env
chmod 0640 /etc/tosbot-ai/tosbot.env
# Whitelist never populated implicitly, even when .env has services.
if [[ ! -e /etc/tosbot-ai/allowed-services.txt ]]; then
  printf '# Satu nama unit systemd per baris. Harus dikelola root.\n' > /etc/tosbot-ai/allowed-services.txt
fi
chown root:root /etc/tosbot-ai/allowed-services.txt
chmod 0644 /etc/tosbot-ai/allowed-services.txt
# Read-only directory tool: never grant a shell or arbitrary path access.
install -o root -g root -m 0755 "$SRC/scripts/tosbot-ai-fs-ctl" /usr/local/sbin/tosbot-ai-fs-ctl
# Only root holds TOTP secrets and job records. Never store them in .env.
install -o root -g root -m 0755 "$SRC/scripts/tosbot-ai-admin-ctl" /usr/local/sbin/tosbot-ai-admin-ctl
install -o root -g root -m 0755 "$SRC/scripts/tosbot-ai-service-ctl" /usr/local/sbin/tosbot-ai-service-ctl
cat > /etc/sudoers.d/tosbot-ai <<'SUDO'
tosbot-ai ALL=(root) NOPASSWD: /usr/local/sbin/tosbot-ai-service-ctl
tosbot-ai ALL=(root) NOPASSWD: /usr/local/sbin/tosbot-ai-fs-ctl
tosbot-ai ALL=(root) NOPASSWD: /usr/local/sbin/tosbot-ai-admin-ctl
SUDO
chown root:root /etc/sudoers.d/tosbot-ai
chmod 0440 /etc/sudoers.d/tosbot-ai
visudo -cf /etc/sudoers.d/tosbot-ai
cat > /etc/systemd/system/tosbot-ai.service <<'UNIT'
[Unit]
Description=TosBot AI Agent - Telegram personal assistant
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
User=tosbot-ai
Group=tosbot-ai
WorkingDirectory=/opt/tosbot-ai
EnvironmentFile=/etc/tosbot-ai/tosbot.env
Environment=PYTHONPATH=/opt/tosbot-ai/src
Environment=TOSBOT_DB_PATH=/var/lib/tosbot-ai/tosbot.sqlite3
Environment=TOSBOT_OUTPUT_DIR=/var/lib/tosbot-ai/documents
Environment=TOSBOT_LOGO_PATH=/opt/tosbot-ai/assets/logo.png
Environment=TOSBOT_OFFER_SIGNATURE_PATH=/opt/tosbot-ai/assets/offer-signature.png
Environment=LANGGRAPH_STRICT_MSGPACK=true
ExecStart=/opt/tosbot-ai/venv/bin/python -m tosbot_ai
Restart=on-failure
RestartSec=8
UMask=0077
ProtectSystem=strict
ProtectHome=true
# Bind home only into private namespace; root-owned tool validates every path.
# It can make one new folder directly under /home/tosbot or /home/tosbot/script.
BindPaths=/home/tosbot:/run/tosbot-home
PrivateTmp=true
PrivateDevices=true
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
ProtectClock=true
RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6
ReadWritePaths=/var/lib/tosbot-ai /var/lib/tosbot-ai-admin /var/log/tosbot-ai /run/tosbot-home /run/tosbot-ai-admin
MemoryMax=850M
TasksMax=70

[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable tosbot-ai.service
# Do not launch with unconfigured credentials; caller starts explicitly after editing env.
echo 'Instalasi selesai. Isi /etc/tosbot-ai/tosbot.env lalu jalankan systemctl start tosbot-ai.'
echo 'App: /opt/tosbot-ai; config: /etc/tosbot-ai; state: /var/lib/tosbot-ai; logs: journalctl -u tosbot-ai'
echo 'Terminal pengguna terbatas tersedia; akses root NONAKTIF sampai admin menjalankan:'
echo '  sudo /usr/local/sbin/tosbot-ai-admin-ctl setup'
echo 'Simpan TOTP di authenticator. Jangan kirim rahasia TOTP ke Telegram.'
