# Security policy

**This public repository can operate a VPS via Telegram, including potentially full root control when the optional administrator helper is enabled.** Review the code before deploying; keep Tailscale/SSH recovery available. Disable root mode unless necessary.

- Never commit `/etc/tosbot-ai`, `.env`, Telegram bot tokens, Groq/Gemini keys, TOTP seeds, private keys, database files, generated invoices/offer PDFs, bank details, signature images, or customer data.
- Configure the Telegram owner ID and use a private chat. Enable Telegram account 2FA and rotate any token previously shown in logs.
- `/sudo` is powerful and not made safe merely by an OTP. Use the restricted shell for routine checks.
- Use a unique low-privilege deployment key for the GitHub repository, not the server root key.
- Before publishing future changes run `python3 scripts/check_public_release.py`.
- Git history preserves deleted secrets; never push first and delete later. Rotate compromised secrets, then rewrite history only if necessary.
- A public repo can be read or modified by others through pull requests: do not automatically deploy unreviewed commits to a privileged VPS.

## Telegram group mode (v1.10.0)
- Group mode is opt-in and mention-only; messages without an explicit @mention receive no reply.
- Never route a group member's text to `Engine.handle`, `Terminal.handle`, or the administrator broker.
- Group members may invoke only chat and limited read-only RAM/disk/uptime. No finance, documents, reminders, VPS files, shell, sudo, or credential access.
- Restrict `TELEGRAM_ALLOWED_GROUP_IDS` to your own groups to avoid uninvited groups consuming AI quota.
- When Telegram Privacy Mode is disabled, Telegram sends more group messages to TosBot; application-level filtering is not a substitute for Telegram-level privacy.
- For sensitive server monitoring, disable group mode entirely or avoid adding the bot to untrusted groups.


## Optional trusted-group root mode (v1.12.0)
This dangerous mode is OFF by default. It bypasses per-user TOTP/approval for everyone who can message the allowlisted Telegram group. Enable only with explicit root-owned `/etc/tosbot-ai/trusted-groups.json` **and** `TELEGRAM_TRUSTED_GROUP_ADMIN=true`. Any compromised group member is equivalent to an attacker with VPS root. See `TRUSTED_GROUP_SETUP.md`.
