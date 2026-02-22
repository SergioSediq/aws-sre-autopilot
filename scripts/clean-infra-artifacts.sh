#!/bin/bash
# Remove infra test artifacts from git tracking (files already in .gitignore)
# Run: git rm --cached infra/response*.json 2>/dev/null; git status
cd "$(dirname "$0")/.."
git rm --cached infra/response*.json 2>/dev/null || true
echo "If any files were untracked, run: git commit -m 'chore: stop tracking infra response artifacts'"
