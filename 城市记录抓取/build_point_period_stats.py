#!/usr/bin/env python3
"""
Build point-level period statistics from reports_index.csv.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
from collections import defaultdict
from pathlib import Path
from typing import Dict, Optional, Set, Tuple


TIME_PERIOD_ALL = "所有时段"
SEASON_ORDER = ["春季", "夏季", "秋季", "冬季"]
SEASON_BY_MONTH = {
    3: "春季",
    4: "春季",
    5: "春季",
    6: "夏季",
    7: "夏季",
    8: "夏季",
    9: "秋季",
    10: "秋季",
    11: "秋季",
    12: "冬季",
    1: "冬季",
    2: "冬季",
}

PERIOD_PRIORITY: Dict[str, int] = {TIME_PERIOD_ALL: 0}
for i, season in enumerate(SEASON_ORDER, start=1):
    PERIOD_PRIORITY[season] = i
for m in range(1, 13):
    PERIOD_PRIORITY[f"{m}月"] = 10 + m

OUTPUT_HEADERS = [
    "地点名称",
    "时间段",
    "观鸟点名称",
    "访问人数",
    "访问次数",
    "大概鸟种数",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Aggregate visits/users/max_taxoncount by place + period + point.",
    )
    parser.add_argument(
        "--input-csv",
        default="data/reports_index.csv",
        help="Input CSV path exported by fetch_city_reports.py",
    )
    parser.add_argument(
        "--output-csv",
        default="data/分时段鸟点排名.csv",
        help="Output summary CSV path",
    )
    parser.add_argument(
        "--place-name",
        default="",
        help="Override place name in output. If empty, infer from query_province/province_name.",
    )
    return parser.parse_args()


def normalize_place_name(raw: str) -> str:
    value = (raw or "").strip()
    if not value:
        return value
    for suffix in ("特别行政区", "自治区", "自治州", "地区", "盟", "省", "市"):
        if value.endswith(suffix):
            return value[: -len(suffix)] or value
    return value


def parse_datetime(value: str) -> Optional[dt.datetime]:
    text = (value or "").strip()
    if not text:
        return None
    text = text.replace("T", " ").replace("Z", "")

    candidates = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
        "%Y/%m/%d %H:%M:%S",
        "%Y/%m/%d %H:%M",
        "%Y/%m/%d",
    ]
    for fmt in candidates:
        try:
            return dt.datetime.strptime(text, fmt)
        except ValueError:
            continue
    try:
        return dt.datetime.fromisoformat(text)
    except ValueError:
        return None


def to_int(value: str) -> int:
    text = (value or "").strip()
    if not text:
        return 0
    try:
        return int(text)
    except ValueError:
        try:
            return int(float(text))
        except ValueError:
            return 0


def infer_place_name(input_csv: Path) -> str:
    with input_csv.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            for key in ("query_province", "province_name", "query_city", "city_name"):
                value = (row.get(key) or "").strip()
                if value:
                    return normalize_place_name(value)
    return ""


def main() -> int:
    args = parse_args()
    input_csv = Path(args.input_csv).resolve()
    output_csv = Path(args.output_csv).resolve()
    output_csv.parent.mkdir(parents=True, exist_ok=True)

    if not input_csv.exists():
        raise SystemExit(f"input csv not found: {input_csv}")

    place_name = normalize_place_name(args.place_name) if args.place_name else infer_place_name(input_csv)
    if not place_name:
        place_name = "未知地点"

    # key: (period, point) -> users / visits / max_taxoncount
    stats: Dict[Tuple[str, str], Dict[str, object]] = defaultdict(
        lambda: {"users": set(), "visits": 0, "max_taxon": 0}
    )

    with input_csv.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            point_name = (row.get("point_name") or "").strip() or "未填写观鸟点"
            user_id = (row.get("userid") or "").strip()
            user_name = (row.get("username") or "").strip()
            if user_id:
                user_key = f"id:{user_id}"
            elif user_name:
                user_key = f"name:{user_name}"
            else:
                user_key = "__UNKNOWN_USER__"

            taxon_count = to_int(row.get("taxoncount") or "")
            start_dt = parse_datetime((row.get("start_time") or "").strip())
            end_dt = parse_datetime((row.get("end_time") or "").strip())
            record_dt = start_dt or end_dt

            periods = [TIME_PERIOD_ALL]
            if record_dt is not None:
                month = record_dt.month
                periods.append(SEASON_BY_MONTH[month])
                periods.append(f"{month}月")

            for period in periods:
                bucket = stats[(period, point_name)]
                users = bucket["users"]
                if isinstance(users, set):
                    users.add(user_key)
                bucket["visits"] = int(bucket["visits"]) + 1
                bucket["max_taxon"] = max(int(bucket["max_taxon"]), taxon_count)

    rows = []
    for (period, point_name), bucket in stats.items():
        users = bucket["users"]
        user_count = len(users) if isinstance(users, set) else 0
        visit_count = int(bucket["visits"])
        max_taxon = int(bucket["max_taxon"])

        rows.append(
            {
                "地点名称": place_name,
                "时间段": period,
                "观鸟点名称": point_name,
                "访问人数": user_count,
                "访问次数": visit_count,
                "大概鸟种数": max_taxon,
                "_period_priority": PERIOD_PRIORITY.get(period, 999),
            }
        )

    rows.sort(
        key=lambda x: (
            x["地点名称"],
            x["_period_priority"],
            -x["访问人数"],
            -x["访问次数"],
            x["观鸟点名称"],
        )
    )

    with output_csv.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_HEADERS)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row[k] for k in OUTPUT_HEADERS})

    print(f"Input: {input_csv}")
    print(f"Output: {output_csv}")
    print(f"Place: {place_name}")
    print(f"Rows: {len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
