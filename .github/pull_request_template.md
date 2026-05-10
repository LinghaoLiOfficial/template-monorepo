## Summary

- What changed?
- Why is this change needed?

## Validation

- [ ] Backend checks passed (`ruff/mypy/pytest` when applicable)
- [ ] Frontend checks passed (`lint/type-check/build` when applicable)
- [ ] Project map synced (`python3 scripts/generate_project_map.py` and `python3 scripts/check_project_map.py`)

## Template Sync Checklist (when applicable)

- [ ] Sync range documented (`--from template-vX.Y.Z --to template-vA.B.C`)
- [ ] `scripts/sync_template.sh --dry-run` output reviewed
- [ ] `manual_only` files reviewed and manually merged if needed
- [ ] `scripts/post_sync_verify.sh` executed successfully
- [ ] Risk and rollback plan documented
