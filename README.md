# TosBot AI Agent — Public Source Repository

**Release:** `v1.12.1` (first publishable Git baseline; based on the locally produced TosBot v1.9 package).

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
sudo git checkout v1.11.0
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
sudo git checkout v1.11.0
sudo systemctl stop tosbot-ai
sudo bash install.sh
sudo systemctl start tosbot-ai
```

For a later release, replace the tag. Always read the release notes and review changes affecting sudo, admin broker, and install scripts. Use `sudo git pull --ff-only` if the clone is root-owned, and only on the `main` branch for latest development; **tags are recommended for stable production deployments.** `git pull` inside a folder extracted from ZIP will not work until it becomes a Git clone.

## Mention-only Telegram group mode (v1.11.0)

By default, **group mode is disabled**. To enable it, edit `/etc/tosbot-ai/tosbot.env`:

```ini
TELEGRAM_GROUPS_ENABLED=true
# Optional: limit to chosen group IDs. Empty = any group the bot joins.
TELEGRAM_ALLOWED_GROUP_IDS=
```

Restart with `sudo systemctl restart tosbot-ai`. Add the bot to a group using Telegram. Check with @BotFather (`/setjoingroups`) that it can join groups. **Do not grant it group administrator rights.** Start by keeping BotFather Privacy Mode **enabled**. If plain `@botusername` messages do not reach the bot in your Telegram setup, you may need to disable Group Privacy via BotFather and re-add the bot to the group. In this case Telegram delivers other group messages too, but TosBot *ignores them without responding or storing their contents*. Review this privacy tradeoff with the group.

- `@your_bot_username Halo` → public group chat via Groq/Gemini.
- `@your_bot_username cek RAM`, `cek disk`, or `cek status VPS` → actual VPS read-only metrics.
- `/help@your_bot_username` or `@your_bot_username /help` → group-safe help.
- `@your_bot_username /groupid` → show the group's negative ID for optional allowlisting.
- `halo` without @mention or Reply → **silent**.
- **Reply directly to a message sent by TosBot** → treated as addressed to the bot; useful for answering missing fields, corrections, and confirming a draft with `sudah sesuai`.
- Replies to users or other bots are ignored. Telegram sender ID, group ID and topic are validated. Terminal/shell commands require an explicit @mention; a Reply alone cannot invoke the shell/root broker.
- `@your_bot_username /sh ...`, `/sudo`, root, service changes, invoices, finance, reminders, and file access → **refused**, including when the sender is the owner.

There is **no user-ID authentication within an allowed group**. Group allowlisting, if enabled, is based on the **group ID**, not a person's ID. Group chat context is isolated by group/topic/user, and never mixes with the owner's private chat history. The group is a public, unprivileged assistant—**not a multi-user root shell**.

### Group operational diagnostics (v1.11.0)

If you specifically trust the members of one known group, enable limited **read-only**
diagnostics without manual approval of every sender's user ID:

```ini
TELEGRAM_GROUPS_ENABLED=true
TELEGRAM_ALLOWED_GROUP_IDS=-1003733083844
TELEGRAM_GROUP_OPERATIONS_ENABLED=true
```

**You must explicitly set a group ID**, otherwise the new diagnostics remain disabled.
The allowed commands when addressed with an `@mention` are: `ping google.com`,
`ping -c 4 google.com`, `ping ke google.com sebanyak 4 kali`, `df -h`,
`free -h`, `uptime`, `hostname`, `pwd`, and `status nginx` for units also
allowed in `ADMIN_ALLOWED_SERVICES`. Runs a fixed command without invoking a shell;
network ping has a packet and deadline cap.

This deliberately **does not grant group members `/sh`, `/sudo`, `/auth`, `apt upgrade`,
`mkdir`, `systemctl restart`, or arbitrary root execution**. Allowing all group
members unauthenticated root access would make the entire VPS vulnerable to one
compromised Telegram account. Privileged commands remain in the owner-private flow.


If you want to restrict groups, temporarily leave `TELEGRAM_ALLOWED_GROUP_IDS` blank, ask `@your_bot_username /groupid` in the desired group, and then add that ID to the configuration and restart. Members can use the bot without showing their individual Telegram IDs.

## Development and checks

```bash
python3 scripts/check_public_release.py
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

For a VPS-only systemd/LangGraph audit: `sudo /opt/tosbot-ai/scripts/audit-vps.sh`. Tests do not prove live Groq, Gemini, Telegram, systemd or privileged shell safety.

## Release and publishing

See [PUBLISH.md](PUBLISH.md). Version file: `VERSION`; maintain `CHANGELOG.md` on every release. Never store company identity or signed PDFs in repository history.


## Trusted group administrator mode (v1.12.0)
See `TRUSTED_GROUP_SETUP.md` for explicitly opted-in unrestricted group root access, risks, and setup. Disabled by default.

## Telegram Reply-to-Bot workflow (v1.12.1)

The user can explicitly mention the bot **or** reply to a message posted by the bot. Telegram `reply_to_message.from.id` must match the numeric bot ID obtained via `getMe`, and the message must come from the same group/topic. A quote, forward, or reply to a member is not sufficient. No AI call is used to determine whether a reply is directed to the bot.

Example: `@mustikasaribot buatkan penawaran ...` → TosBot previews draft → a group member presses **Reply** on TosBot's preview and sends `sudah sesuai`. This continues the group's shared draft and finalizes the PDF if the draft is complete.

Because a trusted group shares a single draft, only one current document is active per group. Review the latest preview before finalizing; do not reply to stale previews from older transactions.


## v1.12.2: Dashboard live bridge

Lihat `UPGRADE_V1122.md`. Dashboard memegang kebenaran untuk data pelanggan, tiket servis, dan foto. Chatbot mengakses API dashboard localhost menggunakan token acak dengan izin baca saja; pekerjaan, keuangan, atau dokumen lain tetap mengikuti jalur lama.
