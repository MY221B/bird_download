#!/usr/bin/env python3
"""Suggest Aug–Dec hotspots from period ranking CSV to top up a city to N locations."""

from __future__ import annotations

import argparse
import csv
import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple


AUG_DEC = {f"{m}月" for m in range(8, 13)}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="From 分时段鸟点排名.csv, pick Aug–Dec hotspots not yet in address library.",
    )
    parser.add_argument("--ranking-csv", required=True)
    parser.add_argument(
        "--locations-json",
        default=str(Path(__file__).resolve().parents[1] / "config" / "birdreport_locations.json"),
    )
    parser.add_argument(
        "--city-match",
        required=True,
        help="Match locations by province or city field substring, e.g. 上海市 / 深圳市",
    )
    parser.add_argument("--target-count", type=int, default=15)
    parser.add_argument("--candidate-pool", type=int, default=40)
    parser.add_argument("--note-prefix", default="")
    return parser.parse_args()


def normalize_name(name: str) -> str:
    text = unicodedata.normalize("NFKC", (name or "").strip())
    text = text.replace("（", "(").replace("）", ")")
    text = re.sub(r"\s+", "", text)
    for token in ("北京市", "上海市", "广州市", "深圳市", "西安市", "长沙市", "兰州市", "桂林市", "芜湖市"):
        if text.startswith(token):
            text = text[len(token) :]
    return text


def score_aug_dec(ranking_csv: Path) -> List[Tuple[str, int, int]]:
    """Return [(point_name, max_monthly_visitors, months_seen), ...] sorted by score desc."""
    by_point: Dict[str, Dict[str, int]] = defaultdict(dict)
    with ranking_csv.open(encoding="utf-8") as fp:
        reader = csv.DictReader(fp)
        for row in reader:
            period = (row.get("时间段") or "").strip()
            if period not in AUG_DEC:
                continue
            point = (row.get("观鸟点名称") or "").strip()
            if not point:
                continue
            visitors = int(row.get("访问人数") or 0)
            by_point[point][period] = max(by_point[point].get(period, 0), visitors)

    ranked: List[Tuple[str, int, int]] = []
    for point, months in by_point.items():
        ranked.append((point, max(months.values()), len(months)))
    ranked.sort(key=lambda item: (-item[1], -item[2], item[0]))
    return ranked


def existing_names(locations: Sequence[dict], city_match: str) -> Set[str]:
    names: Set[str] = set()
    for loc in locations:
        province = loc.get("province") or ""
        city = loc.get("city") or ""
        if city_match not in (province, city) and city_match not in province and city_match not in city:
            continue
        names.add(normalize_name(loc.get("name") or ""))
        for alias in loc.get("point_aliases") or []:
            names.add(normalize_name(alias))
    return {n for n in names if n}


def is_covered(point: str, existing: Set[str]) -> bool:
    norm = normalize_name(point)
    if not norm:
        return True
    if norm in existing:
        return True
    for known in existing:
        if not known:
            continue
        if known in norm or norm in known:
            return True
    return False


def slugify(name: str) -> str:
    mapping = {
        "公园": "gongyuan",
        "湿地": "shidi",
        "水库": "shuiku",
        "东滩": "dongtan",
        "植物园": "zhiwuyuan",
        "森林": "senlin",
        "自然保护区": "baohuqu",
        "风景区": "fengjingqu",
        "大学": "daxue",
    }
    text = normalize_name(name)
    for cn, en in mapping.items():
        text = text.replace(cn, f"_{en}")
    # Keep CJK as pinyin-ish fallback: drop to hex-free ascii-ish underscore slug of remaining.
    ascii_parts = re.findall(r"[A-Za-z0-9]+", text)
    if ascii_parts:
        return "_".join(p.lower() for p in ascii_parts)
    # Fallback: use unicode codepoints lightly
    return "point_" + "_".join(f"{ord(ch):x}" for ch in normalize_name(name)[:8])


def main() -> int:
    args = parse_args()
    ranking_csv = Path(args.ranking_csv)
    locations_path = Path(args.locations_json)
    data = json.loads(locations_path.read_text(encoding="utf-8"))
    locations = data["locations"]
    existing = existing_names(locations, args.city_match)
    current_count = sum(
        1
        for loc in locations
        if args.city_match in (loc.get("province") or "", loc.get("city") or "")
        or args.city_match in (loc.get("province") or "")
        or args.city_match in (loc.get("city") or "")
    )
    need = max(0, args.target_count - current_count)
    ranked = score_aug_dec(ranking_csv)

    print(f"city_match={args.city_match}")
    print(f"existing_locations={current_count}, target={args.target_count}, need={need}")
    print(f"aug_dec_ranked_points={len(ranked)}")
    print("--- already covered (top pool) ---")
    suggestions: List[Tuple[str, int, int]] = []
    shown = 0
    for point, score, months in ranked:
        covered = is_covered(point, existing)
        if shown < args.candidate_pool:
            mark = "KEEP" if covered else "NEW "
            print(f"{mark}  max_visitors={score:4d} months={months}  {point}")
            shown += 1
        if not covered:
            suggestions.append((point, score, months))
        if len(suggestions) >= max(need, 1) and shown >= args.candidate_pool:
            # keep scanning a bit for print, but we already have enough NEW
            pass

    print("--- suggested NEW to add ---")
    picks = suggestions[:need]
    if need == 0:
        print("(already at/above target)")
        return 0
    if not picks:
        print("(no uncovered candidates found in ranking)")
        return 1
    for i, (point, score, months) in enumerate(picks, 1):
        note = f"{args.note_prefix}{i}" if args.note_prefix else ""
        print(f"{i:2d}. {point}  (max_visitors={score}, months={months})  note={note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
