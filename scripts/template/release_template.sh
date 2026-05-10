#!/usr/bin/env bash
set -euo pipefail

# Release a new template version tag and generate simple release notes.
# Usage:
#   scripts/template/release_template.sh v1.2.0

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 <version-tag-like-v1.2.0>"
  exit 1
fi

VERSION="$1"
if [[ ! "$VERSION" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "Error: version must match v<MAJOR>.<MINOR>.<PATCH>"
  exit 1
fi

TAG="template-${VERSION}"
DATE_UTC="$(date -u +%Y-%m-%d)"
OUT_DIR="docs/template-releases"
OUT_FILE="${OUT_DIR}/${TAG}.md"

mkdir -p "$OUT_DIR"

if git rev-parse "$TAG" >/dev/null 2>&1; then
  echo "Error: tag ${TAG} already exists"
  exit 1
fi

LAST_TAG="$(git tag --list 'template-v*' --sort=-v:refname | head -n 1 || true)"

{
  echo "# ${TAG}"
  echo
  echo "- Release Date (UTC): ${DATE_UTC}"
  if [[ -n "$LAST_TAG" ]]; then
    echo "- Previous Template Tag: ${LAST_TAG}"
    echo
    echo "## Changes"
    git log --oneline "${LAST_TAG}..HEAD"
  else
    echo "- Previous Template Tag: none"
    echo
    echo "## Changes"
    git log --oneline
  fi
} > "$OUT_FILE"

git tag -a "$TAG" -m "Template release ${TAG}"

echo "Created tag: ${TAG}"
echo "Release notes: ${OUT_FILE}"
echo "Next: git push origin ${TAG}"
