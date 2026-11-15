# Publishing this source to GitHub (owner action required)

**Destination:** `git@github.com:multitek-indo/tosbot-agent.git` (public and initially empty, per owner screenshot). This archive is prepared locally; no GitHub push has occurred.

## First push

1. Unzip this release into a **new empty folder**, e.g. `/home/tosbot/script/tosbot-public-release`. Do **not** run `git add .` in the old `/home/tosbot/script/ai-agent`, which may contain old ZIPs, private PDFs, config and customer files.
2. Verify GitHub SSH permissions: `ssh -T git@github.com` (GitHub SSH access must already be configured).
3. Configure Git author identity (`git config --global user.name ...` and `git config --global user.email ...`).
4. Run `bash scripts/publish_github.sh` from the release folder. The script preflights source safety, creates a Git repo on main, commits the source, creates an annotated tag, and pushes main + tag. It refuses force-push and does not create old historical tags.

The remote must be empty or ready to fast-forward from your local repository. If it contains unrelated commits, stop and reconcile; do not force push.

## Next release (`v1.9.2`, `v1.10.0`, etc.)

Make a commit on `main`, update `VERSION` and `CHANGELOG.md`, pass CI/checks, and create an **annotated** tag, for example:

```bash
git checkout main
git pull --ff-only origin main
python3 scripts/check_public_release.py
PYTHONPATH=src python3 -m unittest discover -s tests -v
git add -A
git commit -m 'fix: explain change'
git tag -a v1.9.2 -m 'TosBot v1.9.2'
git push origin main
git push origin v1.9.2
```

Only tag a version when code and release notes actually correspond to that version. Never amend/tag a published release to point to different code.
