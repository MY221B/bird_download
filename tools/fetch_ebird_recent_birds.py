#!/usr/bin/env python3
"""
Fetch recent bird observations for a park using the eBird API.

Defaults target William O'Brien State Park in Minnesota, but the tool can be
reused for any park if you provide either an eBird locId or coordinates.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Iterable, List, Optional


API_BASE = "https://api.ebird.org/v2"
DEFAULT_LAT = 45.21917
DEFAULT_LNG = -92.76583
DEFAULT_HOTSPOT_NAME = "William O'Brien State Park"


class EbirdError(RuntimeError):
    pass


def require_token() -> str:
    token = os.environ.get("EBIRD_TOKEN", "").strip()
    if not token:
        raise EbirdError(
            "Missing EBIRD_TOKEN. Create an eBird API key at "
            "https://ebird.org/api/keygen and export EBIRD_TOKEN=..."
        )
    return token


def ebird_get(path: str, params: Dict[str, Any], token: str) -> Any:
    query = urllib.parse.urlencode(
        {key: value for key, value in params.items() if value is not None}
    )
    url = f"{API_BASE}{path}"
    if query:
        url = f"{url}?{query}"
    request = urllib.request.Request(
        url,
        headers={
            "X-eBirdApiToken": token,
            "User-Agent": "bird-download-ebird-recent/1.0",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise EbirdError(f"eBird API returned HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise EbirdError(f"Failed to reach eBird API: {exc}") from exc


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    radius_km = 6371.0088
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lng2 - lng1)
    a = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    )
    return radius_km * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def normalize_name(value: str) -> str:
    return "".join(ch.lower() for ch in value if ch.isalnum())


def get_hotspots(
    lat: float,
    lng: float,
    radius_km: float,
    days: Optional[int],
    token: str,
) -> List[Dict[str, Any]]:
    params: Dict[str, Any] = {
        "lat": lat,
        "lng": lng,
        "dist": radius_km,
        "fmt": "json",
    }
    if days:
        params["back"] = days
    hotspots = ebird_get("/ref/hotspot/geo", params, token)
    for hotspot in hotspots:
        hotspot["distanceKm"] = haversine_km(
            lat, lng, float(hotspot["lat"]), float(hotspot["lng"])
        )
    return sorted(hotspots, key=lambda item: item["distanceKm"])


def choose_hotspot(
    hotspots: List[Dict[str, Any]],
    target_name: str,
) -> Optional[Dict[str, Any]]:
    if not hotspots:
        return None

    normalized_target = normalize_name(target_name)
    exact_matches = [
        hotspot
        for hotspot in hotspots
        if normalize_name(str(hotspot.get("locName", ""))) == normalized_target
    ]
    if exact_matches:
        return exact_matches[0]

    contains_matches = [
        hotspot
        for hotspot in hotspots
        if normalized_target
        and normalized_target in normalize_name(str(hotspot.get("locName", "")))
    ]
    if contains_matches:
        return contains_matches[0]

    return hotspots[0]


def recent_for_location(
    loc_id: str,
    days: int,
    max_results: Optional[int],
    locale: str,
    include_provisional: bool,
    token: str,
) -> List[Dict[str, Any]]:
    return ebird_get(
        f"/data/obs/{urllib.parse.quote(loc_id)}/recent",
        {
            "back": days,
            "maxResults": max_results,
            "locale": locale,
            "fmt": "json",
            "includeProvisional": str(include_provisional).lower(),
        },
        token,
    )


def recent_for_geo(
    lat: float,
    lng: float,
    radius_km: float,
    days: int,
    max_results: Optional[int],
    locale: str,
    include_provisional: bool,
    token: str,
) -> List[Dict[str, Any]]:
    return ebird_get(
        "/data/obs/geo/recent",
        {
            "lat": lat,
            "lng": lng,
            "dist": radius_km,
            "back": days,
            "maxResults": max_results,
            "locale": locale,
            "fmt": "json",
            "includeProvisional": str(include_provisional).lower(),
        },
        token,
    )


def observation_row(obs: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "common_name": obs.get("comName", ""),
        "scientific_name": obs.get("sciName", ""),
        "species_code": obs.get("speciesCode", ""),
        "observed_at": obs.get("obsDt", ""),
        "count": obs.get("howMany", ""),
        "location": obs.get("locName", ""),
        "loc_id": obs.get("locId", ""),
        "lat": obs.get("lat", ""),
        "lng": obs.get("lng", ""),
        "reviewed": obs.get("obsReviewed", ""),
        "valid": obs.get("obsValid", ""),
    }


def write_csv(rows: Iterable[Dict[str, Any]], output_path: str) -> None:
    fieldnames = [
        "common_name",
        "scientific_name",
        "species_code",
        "observed_at",
        "count",
        "location",
        "loc_id",
        "lat",
        "lng",
        "reviewed",
        "valid",
    ]
    with open(output_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def print_table(rows: List[Dict[str, Any]], limit: int) -> None:
    if not rows:
        print("No observations found.")
        return

    shown_rows = rows[:limit] if limit > 0 else rows
    widths = {
        "observed_at": 16,
        "common_name": 28,
        "count": 7,
        "location": 36,
    }
    print(
        f"{'Observed':<{widths['observed_at']}} "
        f"{'Common name':<{widths['common_name']}} "
        f"{'Count':<{widths['count']}} "
        f"Location"
    )
    print("-" * 92)
    for row in shown_rows:
        common_name = str(row["common_name"])[: widths["common_name"]]
        location = str(row["location"])[: widths["location"]]
        print(
            f"{str(row['observed_at']):<{widths['observed_at']}} "
            f"{common_name:<{widths['common_name']}} "
            f"{str(row['count']):<{widths['count']}} "
            f"{location}"
        )
    if limit > 0 and len(rows) > limit:
        print(f"... {len(rows) - limit} more rows not shown")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch recent eBird observations for a US park."
    )
    parser.add_argument("--loc-id", help="eBird hotspot/location ID, e.g. L336470")
    parser.add_argument("--lat", type=float, default=DEFAULT_LAT)
    parser.add_argument("--lng", type=float, default=DEFAULT_LNG)
    parser.add_argument("--hotspot-name", default=DEFAULT_HOTSPOT_NAME)
    parser.add_argument("--radius-km", type=float, default=10.0)
    parser.add_argument("--days", type=int, default=30, help="1-30 days; eBird max is 30")
    parser.add_argument("--max-results", type=int, default=None)
    parser.add_argument("--locale", default="en")
    parser.add_argument("--include-provisional", action="store_true")
    parser.add_argument(
        "--mode",
        choices=["hotspot", "geo"],
        default="hotspot",
        help="hotspot chooses an eBird hotspot; geo searches all recent observations nearby",
    )
    parser.add_argument(
        "--fallback-geo",
        action="store_true",
        help="If hotspot mode returns no observations, retry by coordinate radius.",
    )
    parser.add_argument("--csv", dest="csv_path", help="Write normalized results to CSV")
    parser.add_argument("--json", dest="json_path", help="Write raw API results to JSON")
    parser.add_argument("--show", type=int, default=25, help="Rows to print; 0 means all")
    args = parser.parse_args()

    if not 1 <= args.days <= 30:
        parser.error("--days must be between 1 and 30; eBird recent endpoints do not go farther back")
    if not 0 < args.radius_km <= 50:
        parser.error("--radius-km must be > 0 and <= 50")
    return args


def main() -> int:
    args = parse_args()
    try:
        token = require_token()
        selected_hotspot: Optional[Dict[str, Any]] = None

        if args.mode == "geo" and not args.loc_id:
            raw_observations = recent_for_geo(
                args.lat,
                args.lng,
                args.radius_km,
                args.days,
                args.max_results,
                args.locale,
                args.include_provisional,
                token,
            )
            source = (
                f"geo radius {args.radius_km:g} km around "
                f"{args.lat:.5f},{args.lng:.5f}"
            )
        else:
            loc_id = args.loc_id
            if not loc_id:
                hotspots = get_hotspots(
                    args.lat, args.lng, args.radius_km, args.days, token
                )
                selected_hotspot = choose_hotspot(hotspots, args.hotspot_name)
                if not selected_hotspot:
                    raise EbirdError(
                        "No eBird hotspot found near the provided coordinates. "
                        "Try --mode geo or increase --radius-km."
                    )
                loc_id = str(selected_hotspot["locId"])
            raw_observations = recent_for_location(
                loc_id,
                args.days,
                args.max_results,
                args.locale,
                args.include_provisional,
                token,
            )
            source = loc_id

            if not raw_observations and args.fallback_geo:
                raw_observations = recent_for_geo(
                    args.lat,
                    args.lng,
                    args.radius_km,
                    args.days,
                    args.max_results,
                    args.locale,
                    args.include_provisional,
                    token,
                )
                source = (
                    f"fallback geo radius {args.radius_km:g} km around "
                    f"{args.lat:.5f},{args.lng:.5f}"
                )

        rows = [observation_row(obs) for obs in raw_observations]
        rows.sort(key=lambda row: str(row["observed_at"]), reverse=True)

        if selected_hotspot:
            print(
                "Selected hotspot: "
                f"{selected_hotspot.get('locName')} ({selected_hotspot.get('locId')}), "
                f"{selected_hotspot.get('distanceKm'):.2f} km from coordinates, "
                f"latestObsDt={selected_hotspot.get('latestObsDt', '')}"
            )
        print(f"Source: {source}")
        print(f"Found {len(rows)} species/rows in the last {args.days} day(s).")
        print_table(rows, args.show)

        if args.csv_path:
            write_csv(rows, args.csv_path)
            print(f"Wrote CSV: {args.csv_path}")
        if args.json_path:
            with open(args.json_path, "w", encoding="utf-8") as handle:
                json.dump(raw_observations, handle, ensure_ascii=False, indent=2)
            print(f"Wrote JSON: {args.json_path}")
        return 0
    except EbirdError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
