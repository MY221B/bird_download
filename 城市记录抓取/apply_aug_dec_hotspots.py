#!/usr/bin/env python3
"""Add Aug–Dec hotspot suggestions into config/birdreport_locations.json until each city reaches target."""

from __future__ import annotations

import argparse
import csv
import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Sequence, Set, Tuple


AUG_DEC = {f"{m}月" for m in range(8, 13)}
REPO = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--locations-json", default=str(REPO / "config" / "birdreport_locations.json"))
    p.add_argument("--target-count", type=int, default=15)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--apply", action="store_true")
    return p.parse_args()


def normalize_name(name: str) -> str:
    text = unicodedata.normalize("NFKC", (name or "").strip())
    text = text.replace("（", "(").replace("）", ")")
    text = re.sub(r"\s+", "", text)
    for token in (
        "北京市",
        "上海市",
        "广州市",
        "深圳市",
        "西安市",
        "长沙市",
        "兰州市",
        "桂林市",
        "芜湖市",
        "云南省",
    ):
        if text.startswith(token):
            text = text[len(token) :]
    return text


def score_aug_dec(ranking_csv: Path) -> List[Tuple[str, int, int]]:
    by_point: Dict[str, Dict[str, int]] = defaultdict(dict)
    with ranking_csv.open(encoding="utf-8") as fp:
        for row in csv.DictReader(fp):
            period = (row.get("时间段") or "").strip()
            if period not in AUG_DEC:
                continue
            point = (row.get("观鸟点名称") or "").strip()
            if not point:
                continue
            visitors = int(row.get("访问人数") or 0)
            by_point[point][period] = max(by_point[point].get(period, 0), visitors)
    ranked = [(p, max(m.values()), len(m)) for p, m in by_point.items()]
    ranked.sort(key=lambda x: (-x[1], -x[2], x[0]))
    return ranked


def is_covered(point: str, existing: Set[str]) -> bool:
    norm = normalize_name(point)
    if not norm:
        return True
    if norm in existing:
        return True
    for known in existing:
        if known and (known in norm or norm in known):
            return True
    return False


def slugify_ascii(name: str, prefix: str) -> str:
    from pypinyin import lazy_pinyin

    compact = normalize_name(name)
    parts = lazy_pinyin(compact)
    body = "_".join(p.lower() for p in parts if p)
    body = re.sub(r"[^a-z0-9_]+", "_", body)
    body = re.sub(r"_+", "_", body).strip("_")
    if not body:
        body = "point"
    return f"{prefix}_{body}"[:80]


def is_low_quality_point(name: str) -> bool:
    text = name or ""
    bad_patterns = [
        r"弄\d",
        r"路\d+号",
        r"街道.+寺$",
        r"假日风景",
        r"颐景",
        r"汽渡$",
        r"种质资源库",
    ]
    return any(re.search(pat, text) for pat in bad_patterns)


CITY_JOBS = [
    {
        "match": "上海市",
        "ranking": "城市记录抓取/data/上海市_20250801-20251231_分时段鸟点排名.csv",
        "province": "上海市",
        "city": "",
        "id_prefix": "shanghai",
        "note_prefix": "shanghai_augdec_rank_",
    },
    {
        "match": "深圳市",
        "ranking": "城市记录抓取/data/深圳市_20250801-20251231_分时段鸟点排名.csv",
        "province": "广东省",
        "city": "深圳市",
        "id_prefix": "shenzhen",
        "note_prefix": "shenzhen_augdec_rank_",
    },
    {
        "match": "广州市",
        "ranking": "城市记录抓取/data/广州市_20250801-20251231_分时段鸟点排名.csv",
        "province": "广东省",
        "city": "广州市",
        "id_prefix": "guangzhou",
        "note_prefix": "guangzhou_augdec_rank_",
    },
    {
        "match": "长沙市",
        "ranking": "城市记录抓取/data/长沙市_20250801-20251231_分时段鸟点排名.csv",
        "province": "湖南省",
        "city": "长沙市",
        "id_prefix": "changsha",
        "note_prefix": "changsha_augdec_rank_",
    },
    {
        "match": "桂林市",
        "ranking": "城市记录抓取/data/桂林市_20250801-20251231_分时段鸟点排名.csv",
        "province": "广西壮族自治区",
        "city": "桂林市",
        "id_prefix": "guilin",
        "note_prefix": "guilin_augdec_rank_",
    },
    {
        "match": "兰州市",
        "ranking": "城市记录抓取/data/兰州市_20250801-20251231_分时段鸟点排名.csv",
        "province": "甘肃省",
        "city": "兰州市",
        "id_prefix": "lanzhou",
        "note_prefix": "lanzhou_augdec_rank_",
    },
    {
        "match": "芜湖市",
        "ranking": "城市记录抓取/data/芜湖市_20250801-20251231_分时段鸟点排名.csv",
        "province": "安徽省",
        "city": "芜湖市",
        "id_prefix": "wuhu",
        "note_prefix": "wuhu_augdec_rank_",
    },
    {
        "match": "云南省",
        "ranking": "城市记录抓取/data/云南省_20250801-20251231_分时段鸟点排名.csv",
        "province": "云南省",
        "city": "",
        "id_prefix": "yunnan",
        "note_prefix": "yunnan_augdec_rank_",
    },
]


def city_locations(locations: Sequence[dict], match: str) -> List[dict]:
    out = []
    for loc in locations:
        province = loc.get("province") or ""
        city = loc.get("city") or ""
        if match in (province, city) or match in province or match in city:
            out.append(loc)
    return out


def existing_names(locs: Sequence[dict]) -> Set[str]:
    names: Set[str] = set()
    for loc in locs:
        names.add(normalize_name(loc.get("name") or ""))
        for alias in loc.get("point_aliases") or []:
            names.add(normalize_name(alias))
    return {n for n in names if n}


def choose_display_name(raw: str) -> str:
    name = (raw or "").strip()
    for token in (
        "上海市",
        "深圳市",
        "广州市",
        "长沙市",
        "桂林市",
        "兰州市",
        "芜湖市",
        "云南省",
        "北京",
    ):
        if name.startswith(token):
            name = name[len(token) :]
    name = name.strip(" -/|")
    if len(name) > 24 and "(" in name:
        name = name.split("(", 1)[0].strip()
    name = name.replace("国家级自然保护区", "自然保护区")
    name = name.replace("国家湿地公园", "湿地公园")
    name = name.replace("国家森林公园", "森林公园")
    return name or raw.strip()


def main() -> int:
    args = parse_args()
    if not args.apply and not args.dry_run:
        args.dry_run = True

    path = Path(args.locations_json)
    data = json.loads(path.read_text(encoding="utf-8"))
    locations: List[dict] = data["locations"]
    existing_ids = {loc.get("id") for loc in locations}
    added_total = 0

    for job in CITY_JOBS:
        ranking = REPO / job["ranking"]
        current = city_locations(locations, job["match"])
        need = max(0, args.target_count - len(current))
        print(f"\n=== {job['match']}: have={len(current)} need={need} ===")
        if need == 0:
            print("skip (>= target)")
            continue
        if not ranking.exists():
            print(f"missing ranking: {ranking}")
            continue
        ranked = score_aug_dec(ranking)
        names = existing_names(current)
        picks: List[Tuple[str, int, int]] = []
        for point, score, months in ranked:
            if is_low_quality_point(point):
                continue
            if is_covered(point, names):
                continue
            display = choose_display_name(point)
            if is_covered(display, names):
                continue
            picks.append((point, score, months))
            names.add(normalize_name(point))
            names.add(normalize_name(display))
            if len(picks) >= need:
                break
        if not picks:
            print("no new candidates")
            continue
        for i, (point, score, months) in enumerate(picks, 1):
            display = choose_display_name(point)
            loc_id = slugify_ascii(display, job["id_prefix"])
            base_id = loc_id
            n = 2
            while loc_id in existing_ids:
                loc_id = f"{base_id}_{n}"
                n += 1
            existing_ids.add(loc_id)
            entry = {
                "id": loc_id,
                "name": display,
                "province": job["province"],
                "city": job["city"],
                "district": "",
                "mode": 0,
                "outside_type": 0,
                "default_days": 7,
                "query_level": "point",
                "point_aliases": list(
                    dict.fromkeys(
                        [display, point]
                        + ([normalize_name(point)] if normalize_name(point) not in {display, point} else [])
                    )
                ),
                "note": f"{job['note_prefix']}{i}",
            }
            print(
                f"+ {entry['id']} | {entry['name']} | aliases={entry['point_aliases']} "
                f"| score={score} months={months}"
            )
            if args.apply:
                locations.append(entry)
                added_total += 1

    if args.apply and added_total:
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"\nWrote {added_total} locations -> {path}")
    else:
        print(f"\ndry-run complete; would add {added_total if args.apply else 'shown'} entries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
