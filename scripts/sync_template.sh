#!/usr/bin/env bash
set -euo pipefail

# Consumer-side sync entrypoint (Phase 3 hardening).
# Usage:
#   scripts/sync_template.sh --from template-v1.2.0 --to template-v1.3.0

FROM_TAG=""
TO_TAG=""
DRY_RUN="false"
FAIL_ON_UNKNOWN="false"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --from)
      FROM_TAG="$2"
      shift 2
      ;;
    --to)
      TO_TAG="$2"
      shift 2
      ;;
    --dry-run)
      DRY_RUN="true"
      shift 1
      ;;
    --fail-on-unknown)
      FAIL_ON_UNKNOWN="true"
      shift 1
      ;;
    *)
      echo "Unknown argument: $1"
      exit 1
      ;;
  esac
done

if [[ -z "$FROM_TAG" || -z "$TO_TAG" ]]; then
  echo "Usage: $0 --from <template-tag> --to <template-tag> [--dry-run] [--fail-on-unknown]"
  exit 1
fi

for tag in "$FROM_TAG" "$TO_TAG"; do
  if ! git rev-parse "$tag" >/dev/null 2>&1; then
    echo "Error: tag not found: $tag"
    exit 1
  fi
done

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

IMPACT_JSON="$TMP_DIR/impact.json"
AUTO_LIST="$TMP_DIR/auto_apply.txt"
MERGE_LIST="$TMP_DIR/merge_apply.txt"
MANUAL_LIST="$TMP_DIR/manual_only.txt"
UNKNOWN_COUNT_FILE="$TMP_DIR/unknown_count.txt"

echo "[1/6] Analyze sync impact"
python3 scripts/template/check_sync_impact.py "$FROM_TAG" --target-ref "$TO_TAG" --output json > "$IMPACT_JSON"
python3 - <<'PY' "$IMPACT_JSON" "$AUTO_LIST" "$MERGE_LIST" "$MANUAL_LIST" "$UNKNOWN_COUNT_FILE"
import json
import sys
from pathlib import Path

impact = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
for key, path in [
    ('auto_apply', Path(sys.argv[2])),
    ('merge_apply', Path(sys.argv[3])),
    ('manual_only', Path(sys.argv[4])),
]:
    path.write_text("\n".join(impact.get(key, [])), encoding='utf-8')

unknown_count = len(impact.get('unknown', []))
Path(sys.argv[5]).write_text(str(unknown_count), encoding='utf-8')

print(f"AUTO_APPLY: {len(impact.get('auto_apply', []))}")
print(f"MERGE_APPLY: {len(impact.get('merge_apply', []))}")
print(f"MANUAL_ONLY: {len(impact.get('manual_only', []))}")
print(f"UNKNOWN: {unknown_count}")
if impact.get('unknown'):
    print("\nUnknown files (need manual policy update):")
    for item in impact['unknown']:
      print(f"- {item}")
PY

UNKNOWN_COUNT="$(cat "$UNKNOWN_COUNT_FILE")"
if [[ "$FAIL_ON_UNKNOWN" == "true" && "$UNKNOWN_COUNT" != "0" ]]; then
  echo "Error: unknown files detected (${UNKNOWN_COUNT}), aborting due to --fail-on-unknown."
  echo "Action: update .template-sync-manifest.yaml zones before syncing."
  exit 3
fi

echo "[2/6] Build patch bundle"
scripts/template/build_patch_bundle.sh "$FROM_TAG" "$TO_TAG"

if [[ "$DRY_RUN" == "true" ]]; then
  echo "[3/6] Dry-run mode: no file modification"
  echo "Suggested next: rerun without --dry-run"
  exit 0
fi

apply_zone() {
  local zone_name="$1"
  local list_file="$2"

  echo "Applying ${zone_name}"
  if [[ ! -s "$list_file" ]]; then
    echo "No ${zone_name} files"
    return 0
  fi

  local -a files=()
  while IFS= read -r line; do
    [[ -n "$line" ]] && files+=("$line")
  done < "$list_file"

  if [[ ${#files[@]} -eq 0 ]]; then
    echo "No ${zone_name} files"
    return 0
  fi

  git diff --binary "$FROM_TAG" "$TO_TAG" -- "${files[@]}" | git apply --3way
}

echo "[3/6] Apply AUTO_APPLY files"
apply_zone "AUTO_APPLY" "$AUTO_LIST"

echo "[4/6] Apply MERGE_APPLY files"
apply_zone "MERGE_APPLY" "$MERGE_LIST"

echo "[5/6] Report MANUAL_ONLY files"
if [[ -s "$MANUAL_LIST" ]]; then
  echo "Manual review required for:"
  sed 's/^/- /' "$MANUAL_LIST"
else
  echo "No MANUAL_ONLY files"
fi

echo "[6/6] Done. Run verification: scripts/post_sync_verify.sh"
