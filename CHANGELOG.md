# Changelog (TosBot)

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
