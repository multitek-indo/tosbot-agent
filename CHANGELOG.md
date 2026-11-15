## v1.12.1 — Telegram reply-to-bot fix

- Accept direct replies to TosBot's own group messages without requiring an extra @mention.
- Verify the replied-to sender's numeric Telegram bot ID returned by `getMe`, and the group/topic identity.
- Keep ordinary group messages, replies to other accounts/bots, and other groups ignored.
- Restore natural follow-ups for invoice/quotation review and `sudah sesuai` PDF confirmation.
- Require explicit @mention for Bash/root terminal commands, even if sent as a Reply.
- Add regression tests for reply routing and group document finalization.
- No changes to Telegram admin permissions, Groq/Gemini, server terminal, database schema, or the existing root-admin opt-in.

## v1.12.0 — Trusted Group Administrator (opt-in, high risk)
- Add group-wide full application access (separate workspace per group).
- Add root-broker access for explicit root-owned trusted group ID list, without per-user TOTP.
- Add per-group shell directory and job listing.
- Keep private owner mode and default restricted groups unchanged.

## [1.11.0] — Group-scoped read-only operations
- Introduce opt-in group operational diagnostics without per-user ID enrollment.
- Require explicit Telegram group ID allowlist before enabling operational commands.
- Ping runs as argv (no shell), bounded to four packets and a short deadline; adds fixed RAM/disk/uptime/hostname/service-status tools.
- No anonymous `/sh`, sudo, root, apt, filesystem mutation, finance or private-document capabilities are exposed.
- Previous private owner administration and group mention gating remain unchanged.

# Changelog (TosBot)

## [1.10.0] — Mention-only Telegram groups
- Add optional group/supergroup mode with **strict @username mention gating**. No reply without a mention, even for replies and generic slash commands.
- Any normal member in an enabled group may use public-safe Q&A, RAM, disk, uptime and help without owner-ID authentication.
- Maintain a hard separation: group messages never reach private owner engine, Bash terminal, TOTP broker, reminders, finance, file tools, customer documents or sudo.
- Isolate bounded group chat context by group, topic and sender; add rate limiting and optional group-ID allowlist.
- Detect the real bot @username using Telegram getMe, handle /help@bot, reply in the original thread.
- No production secret/configuration or signed PDF assets are part of the public release.
- Offline regression tests added; Telegram/Groq/Gemini live tests still required.

## [1.9.1] — Public-source preparation (first Git tag)
- Import current v1.9 application source code from the tested offline archive.
- Remove signed document assets, generated PDFs, company/bank details, and production configuration from publishable source.
- Preserve existing private `/opt/tosbot-ai/assets/` files on upgrade.
- Add Git ignore rules, secret preflight, CI, documentation, and versioned deployment process.
- No assertion that live GitHub push or VPS integration tests have run.

## Previous package milestones (historical notes, not Git tags)
- v1.1: Groq as main AI provider; Gemini fallback.
- v1.2–v1.3: API diagnosis and document-template improvements.
- v1.4: Context handling and LangGraph checkpoint integration.
- v1.5: Filesystem directory inspection tool.
- v1.6: Safe ping/directory creation and virtual working-directory operations.
- v1.7: Limited Bash console and separately authenticated administrator jobs.
- v1.8: Root-confirmation and history-sanitization changes, runtime audits.
- v1.9: Natural language `ping` normalization.

**Git history starts with v1.9.1.** Previous milestones are based on archived local release packages, and are not represented as fictitious Git commits/tags.
