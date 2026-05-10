#!/usr/bin/env python3
"""Classify template sync impact by manifest zones.

Phase 2:
- Uses a stricter parser for the limited manifest structure we define.
- Supports text and JSON outputs for downstream scripts/CI.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

MANIFEST = Path('.template-sync-manifest.yaml')


@dataclass(slots=True)
class Zones:
    auto_apply: list[str]
    merge_apply: list[str]
    manual_only: list[str]


def run(cmd: list[str]) -> str:
    result = subprocess.run(cmd, check=True, capture_output=True, text=True)
    return result.stdout.strip()


def get_changed_files(base_ref: str, target_ref: str = 'HEAD') -> list[str]:
    out = run(['git', 'diff', '--name-only', f'{base_ref}..{target_ref}'])
    return [line.strip() for line in out.splitlines() if line.strip()]


def _section(lines: list[str], header: str) -> list[str]:
    in_section = False
    rows: list[str] = []
    for line in lines:
        if line.strip() == f'{header}:':
            in_section = True
            continue
        if in_section:
            if line and not line.startswith(' '):
                break
            rows.append(line)
    return rows


def _list_under(section_rows: list[str], key: str) -> list[str]:
    rows: list[str] = []
    in_key = False
    for line in section_rows:
        if line.strip() == f'{key}:':
            in_key = True
            continue
        if in_key:
            # Next sibling key under same indentation level.
            if line.startswith('  ') and line.strip().endswith(':') and not line.startswith('    - '):
                break
            stripped = line.strip()
            if stripped.startswith('- '):
                rows.append(stripped[2:].strip().strip('"').strip("'"))
    return rows


def parse_manifest(path: Path) -> Zones:
    text = path.read_text(encoding='utf-8')
    lines = text.splitlines()
    zones_rows = _section(lines, 'zones')

    auto_apply = _list_under(zones_rows, 'auto_apply')
    merge_apply = _list_under(zones_rows, 'merge_apply')
    manual_only = _list_under(zones_rows, 'manual_only')

    if not (auto_apply or merge_apply or manual_only):
        raise ValueError('No zones parsed from manifest. Check format.')

    return Zones(
        auto_apply=auto_apply,
        merge_apply=merge_apply,
        manual_only=manual_only,
    )


def classify(path: str, patterns: list[str]) -> bool:
    matched = False
    for p in patterns:
        is_neg = p.startswith('!')
        pattern = p[1:] if is_neg else p
        if fnmatch.fnmatch(path, pattern):
            matched = not is_neg
    return matched


def classify_files(files: list[str], zones: Zones) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {
        'auto_apply': [],
        'merge_apply': [],
        'manual_only': [],
        'unknown': [],
    }

    for f in files:
        if classify(f, zones.auto_apply):
            out['auto_apply'].append(f)
        elif classify(f, zones.merge_apply):
            out['merge_apply'].append(f)
        elif classify(f, zones.manual_only):
            out['manual_only'].append(f)
        else:
            out['unknown'].append(f)

    return out


def print_text(base_ref: str, target_ref: str, classified: dict[str, list[str]]) -> None:
    changed_count = sum(len(v) for v in classified.values())
    print(f'Base ref: {base_ref}')
    print(f'Target ref: {target_ref}')
    print(f'Changed files: {changed_count}')

    def group(name: str) -> None:
        items = classified[name]
        print(f'\n[{name.upper()}] ({len(items)})')
        for item in items:
            print(f'- {item}')

    group('auto_apply')
    group('merge_apply')
    group('manual_only')
    group('unknown')


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('base_ref', help='base git ref, e.g. template-v1.2.0')
    parser.add_argument('--target-ref', default='HEAD', help='target git ref, default HEAD')
    parser.add_argument('--output', choices=['text', 'json'], default='text')
    parser.add_argument('--strict', action='store_true', help='return non-zero when unknown files exist')
    args = parser.parse_args()

    if not MANIFEST.exists():
        print('Error: .template-sync-manifest.yaml not found')
        return 2

    zones = parse_manifest(MANIFEST)
    changed = get_changed_files(args.base_ref, args.target_ref)
    classified = classify_files(changed, zones)

    if args.output == 'json':
        print(
            json.dumps(
                {
                    'base_ref': args.base_ref,
                    'target_ref': args.target_ref,
                    'changed_count': len(changed),
                    **classified,
                },
                ensure_ascii=False,
            )
        )
    else:
        print_text(args.base_ref, args.target_ref, classified)

    if args.strict and classified['unknown']:
        return 3
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
