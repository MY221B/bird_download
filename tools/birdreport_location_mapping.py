"""Resolve current BirdReport addresses using documented historical locations."""

import json
from collections import defaultdict
from functools import lru_cache
from pathlib import Path


LOCATION_FIELDS = ('province_name', 'city_name', 'district_name', 'point_name')
DEFAULT_MAP_PATH = Path(__file__).resolve().parents[1] / 'config' / 'birdreport_location_map.json'


def parse_ranking_location(label):
    """Separate ranking-only geographic labels from actual point search terms."""
    label = (label or '').strip()
    point, separator, suffix = label.rpartition('【')
    if separator and suffix.endswith('】'):
        regions = suffix[:-1].split('/')
        if point and len(regions) == 3 and all(regions):
            return dict(zip(LOCATION_FIELDS, (*regions, point)))
    return {'point_name': label}


class LocationMapper:
    def __init__(self, locations):
        addresses = defaultdict(set)
        prefixes = defaultdict(set)
        for location in locations:
            if len(location) != 4 or not all(isinstance(x, str) and x.strip() for x in location):
                raise ValueError('Location map entries must contain four nonempty names')
            parts = tuple(x.strip() for x in location)
            addresses[''.join(parts)].add(parts)
            prefixes[''.join(parts[:3])].add(parts[:3])
        self.addresses = addresses
        # Longer district names take precedence over shorter matching prefixes.
        self.prefixes = sorted(prefixes.items(), key=lambda item: (-len(item[0]), item[0]))

    def resolve(self, address):
        address = (address or '').strip()
        candidates = self.addresses.get(address)
        if candidates is not None:
            return dict(zip(LOCATION_FIELDS, next(iter(candidates)))) if len(candidates) == 1 else None
        for prefix, regions in self.prefixes:
            if address.startswith(prefix):
                point = address[len(prefix):].strip()
                if not point or len(regions) != 1:
                    return None
                return dict(zip(LOCATION_FIELDS, (*next(iter(regions)), point)))
        return None

    def normalize(self, row):
        result = dict(row)
        point = (row.get('point_name') or '').strip()
        # A legacy short name with geographic fields is already authoritative.
        if point and any(row.get(key) for key in LOCATION_FIELDS[:3]):
            return result
        address = (row.get('address') or point or '').strip()
        mapped = self.resolve(address)
        if mapped and all(not row.get(key) or row[key] == mapped[key] for key in LOCATION_FIELDS[:3]):
            result.update(mapped)
        else:
            # Preserve unknown or ambiguous addresses, rather than inventing a
            # short name or replacing the actual location with a query filter.
            result['point_name'] = point or address
        return result


@lru_cache(maxsize=4)
def load_location_mapper(path=DEFAULT_MAP_PATH):
    with Path(path).open(encoding='utf-8') as fp:
        data = json.load(fp)
    if data.get('schemaVersion') != 1 or data.get('fields') != list(LOCATION_FIELDS):
        raise ValueError('Unsupported BirdReport location map schema')
    return LocationMapper(data['locations'])
