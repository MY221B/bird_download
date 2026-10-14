#!/usr/bin/env python3
"""Build a reproducible location map from legacy report-index CSVs."""

import argparse
import csv
import hashlib
import json
from pathlib import Path

from birdreport_location_mapping import DEFAULT_MAP_PATH, LOCATION_FIELDS, LocationMapper


ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('inputs', nargs='*', help='Legacy report CSVs; defaults to repository data')
    parser.add_argument('--output', type=Path, default=DEFAULT_MAP_PATH)
    args = parser.parse_args()
    paths = sorted(Path(p) for p in args.inputs) if args.inputs else sorted(
        (ROOT / '城市记录抓取' / 'data').glob('*_报告索引.csv')
    )
    if not paths:
        raise SystemExit('No source report CSVs found')
    locations, sources = set(), []
    skipped = 0
    for path in paths:
        with path.open(encoding='utf-8-sig', newline='') as fp:
            for row in csv.DictReader(fp):
                parts = tuple((row.get(field) or '').strip() for field in LOCATION_FIELDS)
                if all(parts):
                    locations.add(parts)
                else:
                    skipped += 1
        sources.append({'file': path.name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
    if not locations:
        raise SystemExit('No complete legacy locations found; existing map was not replaced')
    mapper = LocationMapper(locations)
    ambiguous = sorted(address for address, parts in mapper.addresses.items() if len(parts) > 1)
    # Keep one compact, readable row per location; no user or report identifiers.
    metadata = {'schemaVersion': 1, 'fields': list(LOCATION_FIELDS), 'sources': sources}
    text = json.dumps(metadata, ensure_ascii=False, indent=2)[:-2] + ',\n  "locations": [\n'
    text += ',\n'.join('    ' + json.dumps(parts, ensure_ascii=False) for parts in sorted(locations))
    text += '\n  ]\n}\n'
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(text, encoding='utf-8')
    print(f'Locations: {len(locations)}; source files: {len(paths)}; incomplete rows skipped: {skipped}')
    print(f'Ambiguous addresses (left unresolved): {len(ambiguous)}')
    print(f'Output: {args.output}')


if __name__ == '__main__':
    main()
