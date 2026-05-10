#!/usr/bin/env bash
set -euo pipefail

# Build patch bundle between two template tags.
# Usage:
#   scripts/template/build_patch_bundle.sh template-v1.2.0 template-v1.3.0

if [[ $# -ne 2 ]]; then
  echo "Usage: $0 <from-tag> <to-tag>"
  exit 1
fi

FROM_TAG="$1"
TO_TAG="$2"
OUT_DIR="artifacts/template-patches"
mkdir -p "$OUT_DIR"

for tag in "$FROM_TAG" "$TO_TAG"; do
  if ! git rev-parse "$tag" >/dev/null 2>&1; then
    echo "Error: tag not found: $tag"
    exit 1
  fi
done

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
PATCH_FILE="${OUT_DIR}/${FROM_TAG}_to_${TO_TAG}_${STAMP}.patch"
SUMMARY_FILE="${OUT_DIR}/${FROM_TAG}_to_${TO_TAG}_${STAMP}.summary.txt"

git diff --binary "$FROM_TAG" "$TO_TAG" > "$PATCH_FILE"

{
  echo "Template patch bundle"
  echo "from: ${FROM_TAG}"
  echo "to:   ${TO_TAG}"
  echo "created_at_utc: ${STAMP}"
  echo
  echo "Changed files:"
  git diff --name-status "$FROM_TAG" "$TO_TAG"
} > "$SUMMARY_FILE"

echo "Patch:   $PATCH_FILE"
echo "Summary: $SUMMARY_FILE"
