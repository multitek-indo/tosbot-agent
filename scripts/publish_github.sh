#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
REMOTE="git@github.com:multitek-indo/tosbot-agent.git"
VERSION="$(cat VERSION)"
[[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo 'Invalid VERSION'; exit 1; }
[[ ! -e .git ]] || { echo 'A Git checkout already exists. Follow PUBLISH.md for next releases.'; exit 1; }
python3 scripts/check_public_release.py
command -v git >/dev/null || { echo 'Install git first'; exit 1; }
[[ -n "$(git config user.name || :)" && -n "$(git config user.email || :)" ]] || { echo 'Configure git user.name and user.email'; exit 1; }
# GitHub repo is expected empty. Do not overwrite existing history.
if ! git ls-remote --exit-code "$REMOTE" >/dev/null 2>&1; then
  echo 'SSH access failed or remote has no refs. Checking GitHub authentication...'
  # Git ls-remote can succeed against an empty repository with no refs; verify connection separately.
  git ls-remote "$REMOTE" >/dev/null || { echo 'Cannot access GitHub remote. Configure SSH key first.'; exit 1; }
fi
if [[ -n "$(git ls-remote "$REMOTE" 2>/dev/null)" ]]; then
  echo 'Remote is not empty. Stop: reconcile existing history before push.'
  exit 1
fi
git init -b main
git remote add origin "$REMOTE"
git add -A
if [[ "$(git diff --cached --name-only | wc -l)" -eq 0 ]]; then echo 'No files to commit'; exit 1; fi
git commit -m "release: TosBot v${VERSION} public baseline"
git tag -a "v${VERSION}" -m "TosBot v${VERSION}"
echo 'Pushing main and annotated release tag (no force)...'
git push -u origin main
git push origin "v${VERSION}"
echo "PUBLISHED: $REMOTE, tag v${VERSION}"
