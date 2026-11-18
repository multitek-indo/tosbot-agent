#!/usr/bin/env bash
set -Eeuo pipefail
if [[ "$EUID" -ne 0 ]]; then echo 'Gunakan: sudo bash scripts/connect_telegram.sh'; exit 1; fi
DASH_ENV=/etc/tosbot-dashboard/dashboard.env
BOT_ENV=/etc/tosbot-ai/tosbot.env
if [[ ! -f "$DASH_ENV" || ! -f "$BOT_ENV" ]]; then
  echo 'Dashboard dan TosBot harus sudah terinstal. Konfigurasi belum lengkap.'; exit 1
fi
install -d -m 0700 -o root -g root /root/tosbot-bridge-backups
NOW=$(date -u +%Y%m%dT%H%M%SZ)
cp -p "$DASH_ENV" "/root/tosbot-bridge-backups/dashboard.env.$NOW"
cp -p "$BOT_ENV" "/root/tosbot-bridge-backups/tosbot.env.$NOW"
python3 - "$DASH_ENV" "$BOT_ENV" <<'PY'
import os,sys,secrets,tempfile
from pathlib import Path
from stat import S_IMODE

dash,bot=map(Path,sys.argv[1:])
lines=dash.read_text().splitlines()
existing=next((x.split('=',1)[1].strip() for x in lines if x.startswith('DASHBOARD_BRIDGE_TOKEN=')), '')
token=existing if len(existing)>=32 else secrets.token_urlsafe(48)

def update(path, key, value):
    data=path.read_text().splitlines()
    matched=False
    for i,row in enumerate(data):
        if row.startswith(key+'='):
            if not matched:data[i]=key+'='+value;matched=True
            else:data[i]='# duplicate '+key+' removed during bridge migration'
    if not matched:data.append(key+'='+value)
    stat=path.stat()
    fd,name=tempfile.mkstemp(prefix=path.name+'.tmp-',dir=path.parent)
    try:
        with os.fdopen(fd,'w') as f:
            f.write('\n'.join(data)+'\n')
            f.flush();os.fsync(f.fileno())
        os.chown(name,stat.st_uid,stat.st_gid)
        os.chmod(name,S_IMODE(stat.st_mode))
        os.replace(name,path)
    finally:
        if os.path.exists(name):os.unlink(name)
update(dash,'DASHBOARD_BRIDGE_TOKEN',token)
update(bot,'TOSBOT_DASHBOARD_BRIDGE_TOKEN',token)
update(bot,'TOSBOT_DASHBOARD_URL','http://127.0.0.1:8765')
print('Kunci integrasi dibuat/disinkronkan di kedua layanan (nilai tidak ditampilkan).')
PY
systemctl restart tosbot-dashboard
systemctl restart tosbot-ai
systemctl is-active --quiet tosbot-dashboard
systemctl is-active --quiet tosbot-ai
curl -fsS http://127.0.0.1:8765/healthz
printf '\nIntegrasi siap. Uji dari Telegram: berapa jumlah pelanggan yang tercatat?\n'
