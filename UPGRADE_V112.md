# Upgrade v1.12.0 — GitHub-ready

See `TRUSTED_GROUP_SETUP.md` for installation, root-owned allowlist and risks. The source is not automatically pushed to GitHub.

```bash
cd /home/tosbot/script/ai-agent/tosbot-agent-public
git status --short
# Stop and back up the service before overwriting source (see setup guide).
unzip -o ../tosbot-agent-v1.12.0-trusted-group.zip -d .
python3 scripts/check_public_release.py
PYTHONPATH=src /opt/tosbot-ai/venv/bin/python -m unittest discover -s tests -q
sudo bash install.sh
```

Publish after reviewing changes:

```bash
git add .
git diff --cached --stat
git diff --cached --check
git commit -m 'feat: trusted Telegram group administration v1.12.0'
git tag v1.12.0
git push origin main
git push origin v1.12.0
```

If `git push` fails due to SSH key, use your configured private deploy key with `GIT_SSH_COMMAND`. Never commit the real `/etc/tosbot-ai/tosbot.env`, user databases, or keys.
