#!/usr/bin/env bash
# Read-only diagnostics; does not print passwords, tokens or API key values.
set -u
if [[ "$EUID" -ne 0 ]]; then
  echo 'Jalankan dari SSH/Tailscale: sudo bash /opt/tosbot-ai/scripts/audit-vps.sh'
  exit 2
fi
printf '\n=== TOSBOT VPS AUDIT (read-only) ===\n'
printf 'UTC: '; date -u '+%F %T'
for unit in tosbot-ai tailscaled cloudflared; do
  if systemctl cat "$unit.service" >/dev/null 2>&1; then
    printf 'SERVICE %-14s %s\n' "$unit" "$(systemctl is-active "$unit.service" 2>/dev/null || true)"
  else
    printf 'SERVICE %-14s not-installed-as-systemd-unit\n' "$unit"
  fi
done
printf '\n--- TosBot sandbox properties ---\n'
systemctl show tosbot-ai.service --no-pager -p User -p Group -p ProtectHome -p ProtectSystem -p PrivateTmp -p MemoryMax -p TasksMax 2>/dev/null || true
printf '\n--- File permissions (not contents) ---\n'
for p in /etc/tosbot-ai/tosbot.env /etc/tosbot-ai/admin-auth.json /etc/sudoers.d/tosbot-ai /var/lib/tosbot-ai /var/lib/tosbot-ai-admin /run/tosbot-ai-admin; do
  if [[ -e "$p" ]]; then
    stat -c '%a %U:%G %n' "$p"
  else
    printf 'MISSING/INACTIVE %s\n' "$p"
  fi
done
printf '\n--- Sudoers syntax ---\n'
visudo -cf /etc/sudoers.d/tosbot-ai 2>&1 | sed -E 's@/etc/sudoers.d/tosbot-ai.*@sudoers: parsed OK@' || true
printf '\n--- Disk / RAM ---\n'
df -h / | tail -1
free -h | grep -E '^(Mem|Swap):' || true
printf '\n--- LangGraph persistence with real service identity (no live APIs) ---\n'
if id -u tosbot-ai >/dev/null 2>&1 && [[ -x /opt/tosbot-ai/venv/bin/python ]]; then
  runuser -u tosbot-ai -g tosbot-ai -- env \
    PYTHONPATH=/opt/tosbot-ai/src \
    LANGGRAPH_STRICT_MSGPACK=true \
    /opt/tosbot-ai/venv/bin/python /opt/tosbot-ai/scripts/check_langgraph.py \
    --state-dir /var/lib/tosbot-ai || true
else
  echo 'FAIL: tosbot-ai account or venv missing'
fi
printf '\nAudit finished; no API credentials displayed.\n'
