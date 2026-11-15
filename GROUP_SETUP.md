# Telegram group: mention-only access (v1.10.0)

This release is based on the publishable GitHub source tree v1.9.1. It **does not** alter the owner-only private-chat authorization scheme.

## 1. Install code / update systemd

Back up the runtime configuration/data first:

```bash
sudo mkdir -p -m 700 /root/tosbot-backups
sudo tar -czf "/root/tosbot-backups/tosbot-before-group-$(date +%Y%m%d-%H%M%S).tar.gz" /etc/tosbot-ai /var/lib/tosbot-ai
```

Use your existing **Git clone** after applying the v1.10.0 source release. Then run `sudo bash install.sh`. The installer copies new Python code to `/opt/tosbot-ai`, not into arbitrary Linux package directories. It preserves private `/etc/tosbot-ai/tosbot.env`, SQLite state and document assets.

## 2. Enable group mode

```bash
sudo nano /etc/tosbot-ai/tosbot.env
```

Add:

```ini
TELEGRAM_GROUPS_ENABLED=true
# For one or more groups: negative IDs separated by commas. Empty permits any group the bot joins.
TELEGRAM_ALLOWED_GROUP_IDS=
```

Set `TELEGRAM_ALLOWED_GROUP_IDS` after discovering your group ID (recommended), then restart:

```bash
sudo systemctl restart tosbot-ai
sudo systemctl status tosbot-ai --no-pager
```

## 3. Configure Telegram

- In **@BotFather** ensure group joining is enabled (`/setjoingroups`).
- Invite the bot to the desired group. **Don't promote it to group administrator.**
- Start with Privacy Mode **enabled**, so Telegram delivers fewer non-target messages.
- Try sending `@your_real_bot_username halo` (select the bot mention in Telegram).
- If normal mentions never reach the bot but `/help@your_real_bot_username` does, check the Telegram Privacy Mode setting. As a last resort disable Privacy Mode using @BotFather `/setprivacy`, then remove and re-add the bot. **Privacy Mode off exposes all group messages to the bot process**, though TosBot's explicit mention filter ignores and does not persist messages without mentions. Disclose this to group members.
- A reply to the bot **without** `@username` must be ignored, as requested.

For groups that include untrusted users, add the group's ID to the allowlist. Discover it with `@your_real_bot_username /groupid` when the allowlist is blank. Then set:

```ini
TELEGRAM_ALLOWED_GROUP_IDS=-1001234567890
```

This is a *group allowlist*, not authentication by individual Telegram member ID. Any normal member of the allowed group can mention the bot.

## 4. Expected behavior

| Input in an allowed group | Expected behavior |
|---|---|
| `halo` | No response |
| Reply to bot `oke` without @mention | No response |
| `/help` | No response |
| `@your_real_bot_username halo` | A reply in the group |
| `@your_real_bot_username cek RAM` | Real server RAM reading |
| `@your_real_bot_username cek disk` | Real server disk reading |
| `@your_real_bot_username cek status VPS` | Read-only status, disk and RAM |
| `/help@your_real_bot_username` | Group-safe help |
| `@your_real_bot_username /groupid` | Group ID |
| `@your_real_bot_username /sudo whoami` | Denied, **no command executed** |
| `@your_real_bot_username /sh ls` | Denied, **no command executed** |
| `@your_real_bot_username buat invoice ...` | Denied, **no document generated** |

Group AI chat uses Groq first with Gemini fallback, with separate bounded history per group/topic/member. Group users cannot access owner's private conversation, files, reminders, finance, invoice, `/sh`, or root. Group requests are rate-limited to limit abuse and cost.

## 5. Troubleshooting

```bash
sudo journalctl -u tosbot-ai -n 40 --no-pager
sudo systemctl status tosbot-ai --no-pager
```

Never paste a live Telegram token, API key, TOTP, or private key into chat. If you shared a bot token earlier, rotate it using BotFather.

**No live Telegram/group test is claimed**: offline regression tests verify routing and isolation; run the above acceptance checks after installing on the actual VPS.
