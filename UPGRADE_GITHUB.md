# Publish v1.10.0 to multitek-indo/tosbot-agent

This ZIP contains the complete publishable source, **without** `.git` or private credentials/assets. It does **not** push to GitHub by itself.

## Existing Git clone already tracking `main`

1. Go to your actual Git checkout (the directory containing `.git`), **not** a previous extracted ZIP folder. Verify with `git rev-parse --is-inside-work-tree`.
2. Ensure `git status --short` is clean and that you have correct GitHub SSH access.
3. On branch `main`, run `git pull --ff-only origin main` **before unpacking the release**.
4. Extract `tosbot-agent-v1.10.0-telegram-group.zip` **into the root of that clone** (ZIP paths are relative to the repo root).
5. Run the public release check and tests, then commit/tag/push.

Example, when the release ZIP is in `/home/tosbot/script/ai-agent/` and your Git checkout is `/home/tosbot/script/ai-agent/tosbot-agent-public`:

```bash
cd /home/tosbot/script/ai-agent/tosbot-agent-public
git status --short
git checkout main
git pull --ff-only origin main
unzip -o ../tosbot-agent-v1.10.0-telegram-group.zip -d .
python3 scripts/check_public_release.py
PYTHONPATH=src python3 -m unittest discover -s tests -v
git status --short
# Review all changes and test results BEFORE staging.
git add .env.example VERSION CHANGELOG.md README.md SECURITY.md PUBLISH.md GROUP_SETUP.md UPGRADE_GITHUB.md src/tosbot_ai/ai.py src/tosbot_ai/bot.py src/tosbot_ai/config.py src/tosbot_ai/group.py tests/test_telegram_group.py
git commit -m 'feat: mention-only Telegram groups v1.10.0'
git tag -a v1.10.0 -m 'TosBot v1.10.0 Telegram group support'
git push origin main
git push origin v1.10.0
```

If `git status --short` was NOT clean initially, **stop and reconcile** before pulling or overwriting files. If tag `v1.10.0` already exists, do not overwrite it; inspect its history instead. Do not force-push.

## If GitHub is still empty and the source directory is not a Git checkout

Run `git status` to confirm no Git checkout exists. After applying v1.10.0 source, you may run `bash scripts/publish_github.sh` from the **public source root**; it creates an initial commit/tag **v1.10.0** only if the remote is empty and GitHub authentication works. It must NOT be used inside an existing Git repo.

## Upgrade running VPS

Once your clone contains the v1.10.0 source, make the private data backup described in `GROUP_SETUP.md`, run:

```bash
sudo systemctl stop tosbot-ai
sudo bash install.sh
sudo nano /etc/tosbot-ai/tosbot.env
# Add TELEGRAM_GROUPS_ENABLED=true, optionally allowlist group IDs.
sudo systemctl restart tosbot-ai
```

To deploy another VPS later, clone the repository and `git checkout v1.10.0` before `sudo bash install.sh`. Configure that server's private credentials in `/etc/tosbot-ai/tosbot.env`; no credential is in GitHub.
