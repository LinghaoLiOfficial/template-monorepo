#!/usr/bin/env python3
"""Validate manifest and classify template sync impact by zones.

This script keeps zero third-party dependencies and provides:
- Strict manifest structure validation for the expected schema.
- File classification by zones: auto_apply / merge_apply / manual_only.
- Text/JSON outputs for local usage and CI.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

MANIFEST = Path('.template-sync-manifest.yaml')

ALLOWED_TOP_LEVEL = {'version', 'zones', 'rules', 'metadata'}
ALLOWED_ZONES = {'auto_apply', 'merge_apply', 'manual_only'}
ALLOWED_RULES = {'deny_delete', 'require_manual_review_when_changed'}
ALLOWED_METADATA = {'owner', 'default_branch', 'notes'}


@dataclass(slots=True)
class Zones:
    auto_apply: list[str]
    merge_apply: list[str]
    manual_only: list[str]


@dataclass(slots=True)
class ManifestData:
    version: int
    zones: Zones
    rules: dict[str, list[str]]
    metadata: dict[str, object]


def run(cmd: list[str]) -> str:
    result = subprocess.run(cmd, check=True, capture_output=True, text=True)
    return result.stdout.strip()


def get_changed_files(base_ref: str, target_ref: str = 'HEAD') -> list[str]:
    out = run(['git', 'diff', '--name-only', f'{base_ref}..{target_ref}'])
    return [line.strip() for line in out.splitlines() if line.strip()]


def _iter_root_sections(lines: list[str]) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    current: str | None = None

    for raw in lines:
        line = raw.rstrip('\n')
        if not line.strip() or line.lstrip().startswith('#'):
            continue

        if not line.startswith(' '):
            if ':' not in line:
                raise ValueError(f'Invalid root line: {line}')
            key, _, rest = line.partition(':')
            key = key.strip()
            rest = rest.strip()
            if key in sections:
                raise ValueError(f'Duplicate root key: {key}')

            if rest:
                sections[key] = [rest]
                current = None
            else:
                sections[key] = []
                current = key
            continue

        if current is None:
            raise ValueError(f'Unexpected indented line without active section: {line}')
        sections[current].append(line)

    return sections


def _parse_keyed_list_block(block_lines: list[str], indent: int = 2) -> dict[str, list[str]]:
    data: dict[str, list[str]] = {}
    current_key: str | None = None
    key_prefix = ' ' * indent
    item_prefix = ' ' * (indent + 2)

    for line in block_lines:
        if not line.strip() or line.lstrip().startswith('#'):
            continue

        if line.startswith(key_prefix) and not line.startswith(item_prefix):
            stripped = line.strip()
            if not stripped.endswith(':'):
                raise ValueError(f'Invalid keyed block header: {line}')
            key = stripped[:-1].strip()
            if key in data:
                raise ValueError(f'Duplicate key in block: {key}')
            data[key] = []
            current_key = key
            continue

        if line.startswith(item_prefix):
            if current_key is None:
                raise ValueError(f'List item without key: {line}')
            stripped = line.strip()
            if not stripped.startswith('- '):
                raise ValueError(f'Expected list item "- ...": {line}')
            value = stripped[2:].strip().strip('"').strip("'")
            if not value:
                raise ValueError(f'Empty list item under key {current_key}')
            data[current_key].append(value)
            continue

        raise ValueError(f'Unexpected line format in block: {line}')

    return data


def _parse_scalar_map_block(block_lines: list[str], indent: int = 2) -> dict[str, object]:
    data: dict[str, object] = {}
    key_prefix = ' ' * indent
    item_prefix = ' ' * (indent + 2)

    current_list_key: str | None = None

    for line in block_lines:
        if not line.strip() or line.lstrip().startswith('#'):
            continue

        if line.startswith(key_prefix) and not line.startswith(item_prefix):
            stripped = line.strip()
            if ':' not in stripped:
                raise ValueError(f'Invalid metadata line: {line}')
            key, _, rest = stripped.partition(':')
            key = key.strip()
            rest = rest.strip()
            if key in data:
                raise ValueError(f'Duplicate metadata key: {key}')

            if rest:
                value: object
                if rest.isdigit():
                    value = int(rest)
                else:
                    value = rest.strip('"').strip("'")
                data[key] = value
                current_list_key = None
            else:
                data[key] = []
                current_list_key = key
            continue

        if line.startswith(item_prefix):
            if current_list_key is None:
                raise ValueError(f'List item without metadata key: {line}')
            stripped = line.strip()
            if not stripped.startswith('- '):
                raise ValueError(f'Expected metadata list item "- ...": {line}')
            value = stripped[2:].strip().strip('"').strip("'")
            if not value:
                raise ValueError(f'Empty metadata list item under key {current_list_key}')
            list_value = data[current_list_key]
            if not isinstance(list_value, list):
                raise ValueError(f'Metadata key {current_list_key} is not a list')
            list_value.append(value)
            continue

        raise ValueError(f'Unexpected metadata line format: {line}')

    return data


def _ensure_pattern_list(name: str, values: list[str]) -> None:
    if not values:
        raise ValueError(f'{name} must not be empty')
    seen: set[str] = set()
    for value in values:
        if value in seen:
            raise ValueError(f'Duplicate pattern in {name}: {value}')
        seen.add(value)
        if value.startswith('!!'):
            raise ValueError(f'Invalid pattern in {name}: {value}')


def parse_manifest(path: Path) -> ManifestData:
    lines = path.read_text(encoding='utf-8').splitlines()
    sections = _iter_root_sections(lines)

    unknown_keys = set(sections.keys()) - ALLOWED_TOP_LEVEL
    if unknown_keys:
        raise ValueError(f'Unknown top-level keys: {sorted(unknown_keys)}')

    missing = ALLOWED_TOP_LEVEL - set(sections.keys())
    if missing:
        raise ValueError(f'Missing required top-level keys: {sorted(missing)}')

    version_lines = sections['version']
    if len(version_lines) != 1 or not version_lines[0].isdigit():
        raise ValueError('version must be an integer scalar')
    version = int(version_lines[0])
    if version != 1:
        raise ValueError(f'Unsupported manifest version: {version}')

    zones_map = _parse_keyed_list_block(sections['zones'])
    unknown_zones = set(zones_map.keys()) - ALLOWED_ZONES
    if unknown_zones:
        raise ValueError(f'Unknown zone keys: {sorted(unknown_zones)}')
    missing_zones = ALLOWED_ZONES - set(zones_map.keys())
    if missing_zones:
        raise ValueError(f'Missing zone keys: {sorted(missing_zones)}')

    for zone_name, patterns in zones_map.items():
        _ensure_pattern_list(f'zones.{zone_name}', patterns)

    rules_map = _parse_keyed_list_block(sections['rules'])
    unknown_rules = set(rules_map.keys()) - ALLOWED_RULES
    if unknown_rules:
        raise ValueError(f'Unknown rule keys: {sorted(unknown_rules)}')
    missing_rules = ALLOWED_RULES - set(rules_map.keys())
    if missing_rules:
        raise ValueError(f'Missing rule keys: {sorted(missing_rules)}')
    for rule_name, patterns in rules_map.items():
        _ensure_pattern_list(f'rules.{rule_name}', patterns)

    metadata_map = _parse_scalar_map_block(sections['metadata'])
    unknown_metadata = set(metadata_map.keys()) - ALLOWED_METADATA
    if unknown_metadata:
        raise ValueError(f'Unknown metadata keys: {sorted(unknown_metadata)}')
    missing_metadata = ALLOWED_METADATA - set(metadata_map.keys())
    if missing_metadata:
        raise ValueError(f'Missing metadata keys: {sorted(missing_metadata)}')

    if not isinstance(metadata_map['owner'], str) or not metadata_map['owner']:
        raise ValueError('metadata.owner must be a non-empty string')
    if not isinstance(metadata_map['default_branch'], str) or not metadata_map['default_branch']:
        raise ValueError('metadata.default_branch must be a non-empty string')
    notes = metadata_map['notes']
    if not isinstance(notes, list) or not notes:
        raise ValueError('metadata.notes must be a non-empty list')

    zones = Zones(
        auto_apply=zones_map['auto_apply'],
        merge_apply=zones_map['merge_apply'],
        manual_only=zones_map['manual_only'],
    )
    return ManifestData(version=version, zones=zones, rules=rules_map, metadata=metadata_map)


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
    parser.add_argument('base_ref', nargs='?', help='base git ref, e.g. template-v1.2.0')
    parser.add_argument('--target-ref', default='HEAD', help='target git ref, default HEAD')
    parser.add_argument('--output', choices=['text', 'json'], default='text')
    parser.add_argument('--strict', action='store_true', help='return non-zero when unknown files exist')
    parser.add_argument('--validate-only', action='store_true', help='validate manifest only and exit')
    args = parser.parse_args()

    if not MANIFEST.exists():
        print('Error: .template-sync-manifest.yaml not found')
        return 2

    try:
        manifest = parse_manifest(MANIFEST)
    except ValueError as exc:
        print(f'Manifest validation failed: {exc}')
        return 4

    if args.validate_only:
        print('Manifest validation passed')
        return 0

    if not args.base_ref:
        print('Error: base_ref is required unless --validate-only is used')
        return 1

    changed = get_changed_files(args.base_ref, args.target_ref)
    classified = classify_files(changed, manifest.zones)

    if args.output == 'json':
        print(
            json.dumps(
                {
                    'base_ref': args.base_ref,
                    'target_ref': args.target_ref,
                    'manifest_version': manifest.version,
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
