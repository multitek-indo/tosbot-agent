# Security policy

**This public repository can operate a VPS via Telegram, including potentially full root control when the optional administrator helper is enabled.** Review the code before deploying; keep Tailscale/SSH recovery available. Disable root mode unless necessary.

- Never commit `/etc/tosbot-ai`, `.env`, Telegram bot tokens, Groq/Gemini keys, TOTP seeds, private keys, database files, generated invoices/offer PDFs, bank details, signature images, or customer data.
- Configure the Telegram owner ID and use a private chat. Enable Telegram account 2FA and rotate any token previously shown in logs.
- `/sudo` is powerful and not made safe merely by an OTP. Use the restricted shell for routine checks.
- Use a unique low-privilege deployment key for the GitHub repository, not the server root key.
- Before publishing future changes run `python3 scripts/check_public_release.py`.
- Git history preserves deleted secrets; never push first and delete later. Rotate compromised secrets, then rewrite history only if necessary.
- A public repo can be read or modified by others through pull requests: do not automatically deploy unreviewed commits to a privileged VPS.
