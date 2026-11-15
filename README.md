# TosBot AI Agent — Public Source Repository

**Release:** `v1.9.1` (first publishable Git baseline; based on the locally produced TosBot v1.9 package).

Telegram-based VPS assistant with Groq (primary), Gemini (fallback), LangGraph checkpoint support, finance tracking, reminders, invoice/offer PDF generation, and optional privileged administration.

## Important: what is not published
Real `.env` files, API keys, customer data, invoice/offer PDFs, company bank details, logo and signature **are not in this repository**. You must configure them privately on each VPS. If deploying over an existing installation, the installer is designed to preserve `/etc/tosbot-ai/tosbot.env`, `/var/lib/tosbot-ai`, and existing installed assets under `/opt/tosbot-ai/assets`.

## Install on a new Ubuntu VPS

```bash
sudo apt-get update
sudo apt-get install -y git
sudo mkdir -p /home/tosbot/script
sudo git clone https://github.com/multitek-indo/tosbot-agent.git /home/tosbot/script/ai-agent
cd /home/tosbot/script/ai-agent
sudo git fetch --tags
sudo git checkout v1.9.1
sudo bash install.sh
sudo nano /etc/tosbot-ai/tosbot.env
sudo systemctl start tosbot-ai
sudo systemctl status tosbot-ai --no-pager
```

The new VPS must have its own Telegram/AI credentials and private document assets. For logo/signature installation, see `assets/README.md`. The bot starts only after credentials are configured. On a VPS already running TosBot, **back up** `/etc/tosbot-ai` and `/var/lib/tosbot-ai` before upgrading.

## Existing VPS: upgrade to a tagged version

In the **Git clone** (not an old ZIP-extracted folder):

```bash
sudo git fetch origin --tags
sudo git checkout v1.9.1
sudo systemctl stop tosbot-ai
sudo bash install.sh
sudo systemctl start tosbot-ai
```

For a later release, replace the tag. Always read the release notes and review changes affecting sudo, admin broker, and install scripts. Use `sudo git pull --ff-only` if the clone is root-owned, and only on the `main` branch for latest development; **tags are recommended for stable production deployments.** `git pull` inside a folder extracted from ZIP will not work until it becomes a Git clone.

## Development and checks

```bash
python3 scripts/check_public_release.py
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

For a VPS-only systemd/LangGraph audit: `sudo /opt/tosbot-ai/scripts/audit-vps.sh`. Tests do not prove live Groq, Gemini, Telegram, systemd or privileged shell safety.

## Release and publishing

See [PUBLISH.md](PUBLISH.md). Version file: `VERSION`; maintain `CHANGELOG.md` on every release. Never store company identity or signed PDFs in repository history.
