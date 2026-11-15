# TosBot v1.11.0 — Group operations upgrade

This update allows **group members to invoke read-only operational diagnostics** without registering individual Telegram IDs. It does **not** enable arbitrary shell, root/sudo, apt upgrade, service restarts, documents, or financial actions from a group.

## Install on existing TosBot VPS

1. Copy `tosbot-agent-v1.11.0-group-ops.zip` to `/home/tosbot/script/ai-agent`.
2. Back up `/etc/tosbot-ai`, `/var/lib/tosbot-ai`.
3. Stop the service and unzip **into the existing Git checkout** only if you intentionally accept changes and `git status --short` is clean.

```bash
sudo systemctl stop tosbot-ai
sudo mkdir -p -m 700 /root/tosbot-backups
sudo tar -czf "/root/tosbot-backups/tosbot-before-v111-$(date +%Y%m%d-%H%M%S).tar.gz" /etc/tosbot-ai /var/lib/tosbot-ai
cd /home/tosbot/script/ai-agent/tosbot-agent-public
unzip -o ../tosbot-agent-v1.11.0-group-ops.zip -d .
python3 scripts/check_public_release.py
sudo bash install.sh
```

If your Git checkout has local changes, back them up or commit them first. Do not run `git reset --hard` to force this update.

Edit `/etc/tosbot-ai/tosbot.env` and set:

```ini
TELEGRAM_GROUPS_ENABLED=true
TELEGRAM_ALLOWED_GROUP_IDS=-1003733083844
TELEGRAM_GROUP_OPERATIONS_ENABLED=true
```

The sample group ID came from your test group. **Confirm it matches the correct trusted group.** Do not leave the group ID allowlist empty when you enable group operations.

```bash
sudo systemctl restart tosbot-ai
sudo systemctl status tosbot-ai --no-pager
```

Test with actual bot username:

```
@mustikasaribot ping google.com
@mustikasaribot ping ke google.com sebanyak 4 kali
@mustikasaribot df -h
@mustikasaribot free -h
@mustikasaribot uptime
@mustikasaribot status nginx
```

`status nginx` works only when `nginx` is permitted in `ADMIN_ALLOWED_SERVICES`. The Telegram group cannot run `/sh`, `/sudo`, `sudo su`, `apt upgrade`, `mkdir`, or unrestricted Linux commands.

## GitHub versioning

The ZIP contains source files, not Git history. After reviewing `git diff` and running tests, publish from your authenticated Git checkout:

```bash
git status --short
PYTHONPATH=src python3 -m unittest discover -s tests -q
git add .
git commit -m "feat(group): add group-scoped read-only operations"
git tag -a v1.11.0 -m "TosBot v1.11.0 group operations"
git push origin main
git push origin v1.11.0
```

Do not push if this repository has unreviewed local files or secrets. If SSH key authentication fails, fix it before pushing. Avoid using root SSH credentials directly on an untrusted server if a deploy key or separate GitHub account can be used.
