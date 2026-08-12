#!/usr/bin/env python3
"""
批量刷新所有地点的鸟单并更新图片/JSON/展示数据 (V2)

V2 改进:
- 三阶段流程: 先检查所有地点缺失 → 统一下载/上传 → 按地点收尾
- 抓取失败时重试 2 次（共 3 次尝试）
- 同一鸟类在多个地点缺失时只下载一次
"""

import argparse
import csv
import json
import os
import re
import shutil
import subprocess
import sys
import time
import unicodedata
from collections import OrderedDict
from datetime import datetime, date, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
CONFIG_PATH = PROJECT_ROOT / "config" / "birdreport_locations.json"
LOCATION_BIRDS_DIR = PROJECT_ROOT / "feather-flash-quiz" / "location_birds"
TMP_BASE = PROJECT_ROOT / "tmp" / "weekly_refresh"
MIN_SPECIES_DEFAULT = 10
MAX_RETRIES = 2
MAX_FETCH_RETRIES = 2  # 抓取失败最多重试 2 次，共 3 次尝试

sys.path.insert(0, str(PROJECT_ROOT / "tools"))
from location_utils import get_location_birds_path
from process_new_birds import (  # type: ignore
    load_all_birds_csv,
    merge_with_all_birds_csv,
    check_missing_birds,
    download_birds,
    check_missing_cloudinary,
    upload_to_cloudinary,
    update_bird_info,
    update_all_birds_csv,
    generate_html,
    reorder_new_birds,
)
from bird_image_policy import (  # type: ignore
    bird_dir_has_acceptable_local_images,
    count_acceptable_images_in_bird_dir,
)
from fetch_from_birdreport import fetch_birds_for_payload  # type: ignore
from auto_sounds_refresh import (  # type: ignore
    download_and_upload_sounds,
    print_sounds_summary,
)
from html_browser_open import try_open_local_html  # type: ignore
BIRD_INFO_CACHE = load_all_birds_csv()


def parse_args():
    parser = argparse.ArgumentParser(
        description="按地点批量刷新鸟类图片并复制 Cloudinary JSON (V2 三阶段流程)"
    )
    parser.add_argument(
        "--locations",
        nargs="+",
        help="仅处理指定地点（可用 id 或 name）",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="默认拉取的天数（未指定 --start/--end 时生效，默认 7）",
    )
    parser.add_argument(
        "--start",
        help="覆盖所有地点的开始日期 YYYY-MM-DD",
    )
    parser.add_argument(
        "--end",
        help="覆盖所有地点的结束日期 YYYY-MM-DD",
    )
    parser.add_argument(
        "--min-species",
        type=int,
        default=MIN_SPECIES_DEFAULT,
        help="若去重鸟种少于该值则跳过更新（默认 10）",
    )
    return parser.parse_args()


def load_locations():
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"未找到配置文件: {CONFIG_PATH}")
    data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    locations = data.get("locations", data)
    if not isinstance(locations, list):
        raise ValueError("配置格式错误，需要列表或包含 locations 字段的对象")
    return locations


def maybe_filter_locations(locations, targets):
    if not targets:
        return locations
    normalized = {t.lower() for t in targets}
    filtered = []
    for entry in locations:
        if (
            entry.get("id", "").lower() in normalized
            or entry.get("name", "").lower() in normalized
        ):
            filtered.append(entry)
    if not filtered:
        raise ValueError("没有匹配的地点。请检查 --locations 参数。")
    return filtered


def parse_date_value(value, fallback=None):
    if not value:
        return fallback
    return datetime.strptime(value, "%Y-%m-%d").date()


def resolve_date_range(entry, args):
    end_date = parse_date_value(args.end, date.today())
    start_date = parse_date_value(args.start, None)
    days = args.days if args.days is not None else entry.get("default_days", 7)
    if start_date is None:
        start_date = end_date - timedelta(days=max(1, days) - 1)
    if start_date > end_date:
        raise ValueError(f"开始日期 {start_date} 晚于结束日期 {end_date}")
    return start_date, end_date


def build_payload(entry, start, end, alias, query_level="point", district_override=None):
    payload = {
        "taxonid": entry.get("taxonid", ""),
        "startTime": start.strftime("%Y-%m-%d"),
        "endTime": end.strftime("%Y-%m-%d"),
        "province": entry.get("province", ""),
        "city": entry.get("city", ""),
        "district": district_override if district_override is not None else entry.get("district", ""),
        "pointname": alias if alias else "",
        "username": entry.get("username", ""),
        "serial_id": entry.get("serial_id", ""),
        "ctime": entry.get("ctime", ""),
        "version": entry.get("version", "CH4"),
        "state": entry.get("state", ""),
        "mode": entry.get("mode", "0"),
        "taxon_month": entry.get("taxon_month", ""),
        "outside_type": entry.get("outside_type", "0"),
        "limit": entry.get("limit", "1500"),
        "page": entry.get("page", "1"),
    }
    if query_level == "province":
        payload["city"] = ""
        payload["district"] = ""
        payload["pointname"] = ""
    elif query_level == "city":
        payload["district"] = ""
        payload["pointname"] = ""
    elif query_level == "district":
        payload["pointname"] = ""
    return payload


def fetch_species_for_location(entry, start, end, output_file):
    query_level = entry.get("query_level", "point")
    location_name = entry.get("name", "未知地点")
    combined = OrderedDict()

    if query_level == "district":
        districts = entry.get("districts", [])
        if districts:
            print(f"🔐 {location_name} - 多区县查询: {len(districts)} 个区县")
            for district in districts:
                if not district:
                    continue
                print(f"  🔍 {district}: 调用 API ...")
                payload = build_payload(entry, start, end, None, query_level="district", district_override=district)
                try:
                    records = fetch_birds_for_payload(payload)
                    print(f"  ✅ {district}: 返回 {len(records)} 条记录")
                    for record in records:
                        key = (record.chinese, record.scientific)
                        if key not in combined:
                            combined[key] = record
                except Exception as exc:
                    print(f"  ⚠️  {district} 查询失败: {exc}")
                    continue
            if not combined:
                raise RuntimeError("所有区县查询都未返回结果")
        else:
            print(f"🔐 {location_name} - 区县级别查询: 调用 API ...")
            payload = build_payload(entry, start, end, None, query_level="district")
            try:
                records = fetch_birds_for_payload(payload)
                print(f"✅ 区县级别: 返回 {len(records)} 条记录")
                for record in records:
                    key = (record.chinese, record.scientific)
                    if key not in combined:
                        combined[key] = record
            except Exception as exc:
                print(f"⚠️  区县级别查询失败: {exc}")
                raise RuntimeError(f"区县级别查询失败: {exc}")
    elif query_level in ["province", "city"]:
        level_names = {"province": "省级别", "city": "城市级别"}
        level_name = level_names.get(query_level, query_level)
        print(f"🔐 {location_name} - {level_name}查询: 调用 API ...")
        payload = build_payload(entry, start, end, None, query_level=query_level)
        records = fetch_birds_for_payload(payload)
        print(f"✅ {level_name}: 返回 {len(records)} 条记录")
        for record in records:
            key = (record.chinese, record.scientific)
            if key not in combined:
                combined[key] = record
    else:
        aliases = entry.get("point_aliases") or [entry.get("pointname") or entry.get("name")]
        for alias in aliases:
            if not alias:
                continue
            print(f"🔐 {location_name} - {alias}: 调用 API ...")
            payload = build_payload(entry, start, end, alias, query_level="point")
            try:
                records = fetch_birds_for_payload(payload)
            except Exception as exc:
                print(f"⚠️  {alias} 抓取失败: {exc}")
                continue
            print(f"✅ {alias}: 返回 {len(records)} 条记录")
            for record in records:
                key = (record.chinese, record.scientific)
                if key not in combined:
                    combined[key] = record

    if not combined:
        raise RuntimeError("所有搜索词都未返回结果")

    with open(output_file, "w", encoding="utf-8") as f:
        for record in combined.values():
            line = f"{record.chinese} {record.english or ''} {record.scientific or ''}".strip()
            f.write(f"{line}\n")
    return list(combined.values())


def remove_accents(text):
    return "".join(
        char
        for char in unicodedata.normalize("NFD", text)
        if unicodedata.category(char) != "Mn"
    )


def generate_slug(name):
    if not name:
        return ""
    name = remove_accents(name)
    name = name.lower()
    name = re.sub(r"[^\w\s-]", "", name)
    name = re.sub(r"[-\s]+", "_", name)
    return name.strip("_")


def write_csv_from_records(records, csv_file):
    lines = ['# slug,chinese_name,english_name,scientific_name,wikipedia_page']
    slug_map = {}
    for record in records:
        base_name = record.english or record.scientific or record.chinese
        slug = generate_slug(base_name)
        chinese = (record.chinese or "").replace('"', '""')
        english = (record.english or "").replace('"', '""')
        scientific = (record.scientific or "").replace('"', '""')
        wiki = ""
        if english:
            wiki = english.replace(" ", "_")
        lines.append(f'{slug},"{chinese}","{english}","{scientific}",{wiki}')
        slug_map[slug] = {
            "chinese_name": record.chinese or "",
            "english_name": record.english or "",
            "scientific_name": record.scientific or "",
        }
    csv_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return slug_map


def format_slug(slug, local_info):
    info = (local_info or {}).get(slug) or BIRD_INFO_CACHE.get(slug)
    if not info:
        return slug
    chinese = info.get("chinese_name") or info.get("chinese")
    english = info.get("english_name") or info.get("english")
    label = english or slug
    if chinese:
        return f"{label}（{chinese}）"
    return label


def format_slug_list(slugs, local_info):
    if not slugs:
        return []
    return [format_slug(slug, local_info) for slug in slugs]


def read_slugs_from_csv(csv_file):
    slugs = []
    with open(csv_file, encoding="utf-8") as f:
        filtered = [
            line for line in f.readlines() if line.strip() and not line.startswith("#")
        ]
        reader = csv.reader(filtered)
        for row in reader:
            if not row:
                continue
            slug = row[0].strip().strip('"')
            if slug and slug.lower() != "slug":
                slugs.append(slug)
    return slugs


def copy_json_to_location(slugs, location_name, report_code):
    dest_dir = get_location_birds_path(location_name, report_code)
    dest_dir.mkdir(parents=True, exist_ok=True)
    copied = 0
    missing = []
    for slug in slugs:
        src = PROJECT_ROOT / "cloudinary_uploads" / f"{slug}_cloudinary_urls.json"
        if src.exists():
            shutil.copy2(src, dest_dir / src.name)
            copied += 1
        else:
            missing.append(slug)
    location_dir = dest_dir.parent
    for old_folder in location_dir.iterdir():
        if old_folder.is_dir() and old_folder.name != report_code and old_folder.name != "000000":
            shutil.rmtree(old_folder)
    return dest_dir, copied, missing


def ensure_tmp_dir():
    TMP_BASE.mkdir(parents=True, exist_ok=True)
    batch_dir = TMP_BASE / datetime.now().strftime("%Y%m%d_%H%M%S")
    batch_dir.mkdir(parents=True, exist_ok=True)
    return batch_dir


def main():
    args = parse_args()
    locations = maybe_filter_locations(load_locations(), args.locations)
    run_dir = ensure_tmp_dir()
    summary = []
    combined_slugs = []
    combined_seen = set()

    # ========== 阶段1: 检查所有地点，收集缺失鸟类 ==========
    print("\n" + "=" * 80)
    print("📋 阶段1: 检查所有地点的缺失鸟类...")
    print("=" * 80)

    all_missing_local = set()
    all_missing_cloud = set()
    all_missing_info = {}   # slug -> {chinese_name, english_name, scientific_name, wikipedia_page}
    location_data_list = []  # 成功抓取的地点数据
    extended_range_locs = []  # 使用30天扩展范围才成功抓取的地点

    for entry in locations:
        loc_id = entry.get("id") or entry.get("name")
        loc_name = entry.get("name", loc_id)
        print("\n" + "-" * 60)
        print(f"🌍 地点: {loc_name} ({loc_id})")

        try:
            start_date, end_date = resolve_date_range(entry, args)
        except ValueError as exc:
            print(f"❌ 日期错误: {exc}")
            summary.append({"location": loc_name, "status": "日期错误", "details": str(exc)})
            continue

        location_dir = run_dir / loc_id
        location_dir.mkdir(parents=True, exist_ok=True)
        text_file = location_dir / "birds.txt"
        csv_file = location_dir / "birds.csv"

        # 抓取（带重试，失败后自动扩展到30天再试）
        records = None
        last_exc = None
        for attempt in range(1, MAX_FETCH_RETRIES + 2):
            try:
                records = fetch_species_for_location(entry, start_date, end_date, text_file)
                break
            except Exception as exc:
                last_exc = exc
                if attempt < 3:
                    print(f"🔁 抓取失败，第 {attempt}/3 次尝试，将重试: {exc}")
                    time.sleep(4)
                else:
                    print(f"⚠️  常规时间范围（{start_date} ~ {end_date}）3次均失败，尝试扩展至30天...")

        if records is None:
            # 用30天范围重试
            ext_end = date.today()
            ext_start = ext_end - timedelta(days=29)
            for attempt in range(1, MAX_FETCH_RETRIES + 2):
                try:
                    records = fetch_species_for_location(entry, ext_start, ext_end, text_file)
                    print(f"✅ 30天扩展范围（{ext_start} ~ {ext_end}）抓取成功: {len(records)} 种")
                    start_date = ext_start
                    end_date = ext_end
                    extended_range_locs.append(loc_name)
                    break
                except Exception as exc:
                    last_exc = exc
                    if attempt < 3:
                        print(f"🔁 30天范围失败，第 {attempt}/3 次尝试，将重试: {exc}")
                        time.sleep(4)
                    else:
                        print(f"❌ 30天范围也失败（已重试 2 次）: {exc}")
                        summary.append({"location": loc_name, "status": "抓取失败", "details": str(last_exc)})

        if records is None:
            continue

        species_count = len(records)
        print(f"📊 {loc_name} 去重鸟种: {species_count}")

        if species_count < max(1, args.min_species):
            print(f"⚠️  警告：少于 {args.min_species} 种（当前 {species_count} 种），但仍会继续处理")

        slug_info = write_csv_from_records(records, csv_file)
        merge_with_all_birds_csv(csv_file)
        missing_local = check_missing_birds(csv_file)
        missing_cloud = check_missing_cloudinary(csv_file)

        all_missing_local.update(missing_local)
        all_missing_cloud.update(missing_cloud)

        # 收集缺失鸟类的名字信息（优先用 BIRD_INFO_CACHE，其次用本地点的 slug_info）
        for slug in (set(missing_local) | set(missing_cloud)):
            if slug not in all_missing_info:
                info = BIRD_INFO_CACHE.get(slug) or slug_info.get(slug) or {}
                all_missing_info[slug] = info

        report_code = end_date.strftime("%y%m%d")
        slugs = read_slugs_from_csv(csv_file)
        for slug in slugs:
            if slug not in combined_seen:
                combined_slugs.append(slug)
                combined_seen.add(slug)

        location_data_list.append({
            "entry": entry,
            "loc_id": loc_id,
            "loc_name": loc_name,
            "start_date": start_date,
            "end_date": end_date,
            "location_dir": location_dir,
            "csv_file": csv_file,
            "slug_info": slug_info,
            "species_count": species_count,
            "missing_local": list(missing_local),
            "missing_cloud": list(missing_cloud),
            "downloads_for_log": sorted(set(missing_local)),
            "report_code": report_code,
        })

    # ========== 阶段2: 统一下载和上传 ==========
    print("\n" + "=" * 80)
    print("📥 阶段2: 统一下载和上传缺失鸟类...")
    print("=" * 80)

    all_birds_map = load_all_birds_csv()
    all_to_process = all_missing_local | all_missing_cloud

    if all_to_process:
        temp_combined_csv = run_dir / "combined_missing_birds.csv"
        with open(temp_combined_csv, 'w', encoding='utf-8') as f:
            f.write('# slug,chinese_name,english_name,scientific_name,wikipedia_page\n')
            for slug in sorted(all_to_process):
                # 优先用 Phase 1 收集的信息（包含新鸟的 API 数据），再 fallback 到 all_birds_map
                bird_info = all_missing_info.get(slug) or all_birds_map.get(slug) or {}
                chinese = bird_info.get('chinese_name', '')
                english = bird_info.get('english_name', '')
                scientific = bird_info.get('scientific_name', '')
                wiki = bird_info.get('wikipedia_page', '')
                if not wiki and english:
                    wiki = english.replace(' ', '_')
                f.write(f'{slug},"{chinese}","{english}","{scientific}",{wiki}\n')

        # 统一下载
        remaining_local = list(all_missing_local)
        for attempt in range(1, MAX_RETRIES + 1):
            if not remaining_local:
                break
            print(f"\n🔁 下载缺失鸟类，第 {attempt}/{MAX_RETRIES} 次尝试（{len(remaining_local)} 种）")
            ok = download_birds(temp_combined_csv, remaining_local)
            if not ok:
                print("⚠️  下载命令失败，停止重试")
                break
            new_missing = []
            for slug in remaining_local:
                bird_path = PROJECT_ROOT / "images" / slug
                if not bird_dir_has_acceptable_local_images(bird_path):
                    new_missing.append(slug)
            remaining_local = new_missing

        if remaining_local:
            print(f"⚠️  仍有 {len(remaining_local)} 种鸟类没有成功下载本地图片：{', '.join(remaining_local)}")

        # 统一上传
        remaining_cloud = list(all_missing_cloud)
        for attempt in range(1, MAX_RETRIES + 1):
            if not remaining_cloud:
                break
            print(f"\n🔁 上传缺失鸟类到 Cloudinary，第 {attempt}/{MAX_RETRIES} 次尝试（{len(remaining_cloud)} 种）")
            ok = upload_to_cloudinary(remaining_cloud, temp_combined_csv)
            if not ok:
                print("⚠️  上传命令失败，停止重试")
                break
            new_missing_cloud = []
            for slug in remaining_cloud:
                json_file = PROJECT_ROOT / "cloudinary_uploads" / f"{slug}_cloudinary_urls.json"
                has_data = False
                if json_file.exists():
                    try:
                        with open(json_file, 'r', encoding='utf-8') as fp:
                            data = json.load(fp)
                            pc = sum(len(data.get(s, [])) for s in ['macaulay', 'inaturalist', 'wikimedia', 'avibase'] if isinstance(data.get(s), list))
                            has_data = pc > 0
                    except Exception:
                        pass
                if not has_data:
                    new_missing_cloud.append(slug)
            remaining_cloud = new_missing_cloud

        if remaining_cloud:
            print(f"⚠️  仍有 {len(remaining_cloud)} 种鸟类未上传至 Cloudinary：{', '.join(remaining_cloud)}")

    # ========== 阶段3: 按地点收尾 ==========
    print("\n" + "=" * 80)
    print("📋 阶段3: 按地点收尾（update、叫声、复制 JSON）...")
    print("=" * 80)

    for loc_data in location_data_list:
        loc_name = loc_data["loc_name"]
        csv_file = loc_data["csv_file"]
        location_dir = loc_data["location_dir"]
        slug_info = loc_data["slug_info"]
        species_count = loc_data["species_count"]
        downloads_for_log = loc_data["downloads_for_log"]
        report_code = loc_data["report_code"]
        missing_local = set(loc_data["missing_local"])

        print(f"\n🌍 {loc_name}")

        update_bird_info(csv_file)
        slugs = read_slugs_from_csv(csv_file)
        success_sounds, failed_sounds = download_and_upload_sounds(slugs, location_dir)
        dest_dir, copied, missing_copy = copy_json_to_location(slugs, loc_name, report_code)

        # 计算 final_missing_local
        final_missing_local = []
        for slug in missing_local:
            bird_path = PROJECT_ROOT / "images" / slug
            if not bird_dir_has_acceptable_local_images(bird_path):
                final_missing_local.append(slug)

        status = "已更新"
        if species_count < max(1, args.min_species):
            status = f"已更新（{species_count}种，少于{args.min_species}种阈值）"

        summary.append({
            "location": loc_name,
            "status": status,
            "details": f"{species_count} 种",
            "downloads": format_slug_list(downloads_for_log, slug_info),
            "downloads_raw": downloads_for_log,
            "missing_local": format_slug_list(final_missing_local, slug_info),
            "missing_json": format_slug_list(missing_copy, slug_info),
            "sounds_success": len(success_sounds),
            "sounds_failed": len(failed_sounds),
            "sounds_failed_details": failed_sounds,
        })

    successful = [item for item in summary if item["status"].startswith("已更新")]

    if successful:
        print("\n🔁 全局更新 all_birds.csv / HTML ...")
        update_all_birds_csv()
        highlight_slugs = []
        for item in summary:
            highlight_slugs.extend(item.get("downloads_raw") or [])
        highlight_slugs = list(set(highlight_slugs))
        import io as _io, contextlib as _cl
        with _cl.redirect_stdout(_io.StringIO()):
            generate_html(highlight_slugs, priority_slugs=highlight_slugs)
        print("✅ HTML 页面已更新")
        if combined_slugs:
            combined_csv = run_dir / "combined_reorder.csv"
            with open(combined_csv, "w", encoding="utf-8", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["slug", "english_name", "scientific_name", "wikipedia_page"])
                for slug in combined_slugs:
                    writer.writerow([slug, "", "", ""])
            with _cl.redirect_stdout(_io.StringIO()):
                reorder_new_birds(combined_csv)
            print(f"✅ {len(combined_slugs)} 种新鸟类已移至列表顶部")

    # 检查 all_birds.csv 中所有缺少 cloudinary JSON 的鸟类（与原逻辑相同）
    print("\n" + "=" * 80)
    print("🔍 检查 all_birds.csv 中所有缺少 cloudinary JSON 的鸟类...")
    all_birds_map = load_all_birds_csv()
    print(f"📋 从 all_birds.csv 加载了 {len(all_birds_map)} 个鸟类")

    all_missing_birds = []
    birds_with_json_and_photos = []
    birds_with_json_but_no_photos = []
    birds_without_json = []
    remaining_all_missing = []  # 用于最后 generate_html

    for slug, bird_info in all_birds_map.items():
        json_file = PROJECT_ROOT / "cloudinary_uploads" / f"{slug}_cloudinary_urls.json"
        has_cloudinary_data = False
        photo_count = 0
        json_exists = json_file.exists()

        if json_exists:
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for source in ['macaulay', 'inaturalist', 'wikimedia', 'avibase']:
                        if source in data and isinstance(data[source], list):
                            photo_count += len(data[source])
                    has_cloudinary_data = photo_count > 0
            except Exception as e:
                has_cloudinary_data = False
                print(f"  ⚠️  {slug}: JSON 文件读取失败 - {e}")

        if has_cloudinary_data:
            birds_with_json_and_photos.append(slug)
        elif json_exists:
            birds_with_json_but_no_photos.append(slug)
            all_missing_birds.append(slug)
        else:
            birds_without_json.append(slug)
            all_missing_birds.append(slug)

    print(f"\n📊 检查结果统计:")
    print(f"  ✅ 有 JSON 且有照片: {len(birds_with_json_and_photos)} 个")
    print(f"  ⚠️  有 JSON 但无照片: {len(birds_with_json_but_no_photos)} 个")
    print(f"  ❌ 没有 JSON 文件: {len(birds_without_json)} 个")
    print(f"  📋 总计需要处理: {len(all_missing_birds)} 个")

    if all_missing_birds:
        print(f"\n📋 发现 {len(all_missing_birds)} 个鸟类缺少 cloudinary JSON，尝试下载...")
        temp_all_missing_csv = run_dir / "all_missing_birds.csv"
        with open(temp_all_missing_csv, 'w', encoding='utf-8') as f:
            f.write('# slug,chinese_name,english_name,scientific_name,wikipedia_page\n')
            for slug in all_missing_birds:
                bird_info = all_birds_map[slug]
                chinese = bird_info.get('chinese_name', '')
                english = bird_info.get('english_name', '')
                scientific = bird_info.get('scientific_name', '')
                wiki = bird_info.get('wikipedia_page', '')
                if not wiki and english:
                    wiki = english.replace(' ', '_')
                f.write(f'{slug},"{chinese}","{english}","{scientific}",{wiki}\n')

        remaining_all_missing = list(all_missing_birds)
        for attempt in range(1, MAX_RETRIES + 1):
            if not remaining_all_missing:
                break
            print(f"\n🔁 下载 all_birds.csv 中缺失的鸟类，第 {attempt}/{MAX_RETRIES} 次尝试（{len(remaining_all_missing)} 种）")
            ok = download_birds(temp_all_missing_csv, remaining_all_missing)
            if not ok:
                print("⚠️  下载命令失败，停止重试")
                break
            new_all_missing = []
            for slug in remaining_all_missing:
                json_file = PROJECT_ROOT / "cloudinary_uploads" / f"{slug}_cloudinary_urls.json"
                has_data = False
                if json_file.exists():
                    try:
                        with open(json_file, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                            photo_count = 0
                            for source in ['macaulay', 'inaturalist', 'wikimedia', 'avibase']:
                                if source in data and isinstance(data[source], list):
                                    photo_count += len(data[source])
                            has_data = photo_count > 0
                    except Exception:
                        pass
                if not has_data:
                    new_all_missing.append(slug)
            remaining_all_missing = new_all_missing

        print(f"\n📁 检查本地图片文件...")
        birds_with_images = []
        birds_without_images = []
        for slug in all_missing_birds:
            bird_path = PROJECT_ROOT / "images" / slug
            if bird_path.exists():
                total_images = count_acceptable_images_in_bird_dir(bird_path)
                has_images = total_images > 0
                if has_images:
                    birds_with_images.append(slug)
                    bird_info = all_birds_map.get(slug, {})
                    name = bird_info.get('chinese_name', '') or bird_info.get('english_name', slug)
                    print(f"  ✅ {slug} ({name}): 有 {total_images} 张本地图片")
                else:
                    birds_without_images.append(slug)
            else:
                birds_without_images.append(slug)

        print(f"\n📊 本地图片检查结果:")
        print(f"  ✅ 有本地图片: {len(birds_with_images)} 个")
        print(f"  ❌ 无本地图片: {len(birds_without_images)} 个")

        if remaining_all_missing:
            print(f"\n⚠️  仍有 {len(remaining_all_missing)} 种鸟类未成功下载（JSON 文件不存在或无照片）")
        else:
            print(f"\n✅ 所有缺失的鸟类已成功下载")

        print(f"\n☁️  检查需要上传到 Cloudinary 的鸟类...")
        all_missing_cloud = []
        for slug in birds_with_images:
            json_file = PROJECT_ROOT / "cloudinary_uploads" / f"{slug}_cloudinary_urls.json"
            has_cloudinary_data = False
            if json_file.exists():
                try:
                    with open(json_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        photo_count = sum(len(data.get(s, [])) for s in ['macaulay', 'inaturalist', 'wikimedia', 'avibase'] if isinstance(data.get(s), list))
                        has_cloudinary_data = photo_count > 0
                except Exception:
                    pass
            if not has_cloudinary_data:
                all_missing_cloud.append(slug)

        if all_missing_cloud:
            print(f"\n🔁 上传 {len(all_missing_cloud)} 个有本地图片但缺少 cloudinary JSON 的鸟类到 Cloudinary...")
            upload_to_cloudinary(all_missing_cloud, temp_all_missing_csv)
    else:
        print("\n✅ all_birds.csv 中所有鸟类都有 cloudinary JSON")

    # 任务摘要
    print("\n" + "=" * 80)
    print("📋 任务摘要")
    all_downloads = set()
    all_missing_local_set = set()
    all_missing_json_set = set()
    for item in summary:
        _status = item['status']
        if _status.startswith("已更新"):
            print(f"- {item['location']}: {_status} ({item.get('details','')})")
        else:
            print(f"- {item['location']}: {_status} — {item.get('details','')}")
        all_downloads.update(item.get("downloads") or [])
        all_missing_local_set.update(item.get("missing_local") or [])
        all_missing_json_set.update(item.get("missing_json") or [])

    if all_downloads or all_missing_local_set or all_missing_json_set:
        downloaded_count = len(all_downloads) - len(all_missing_local_set)
        uploaded_count = len(all_downloads) - len(all_missing_json_set)
        print(f"\n📊 汇总统计:")
        print(f"  · 缺失的新鸟类: {len(all_downloads)} 种")
        print(f"  · 已成功下载的鸟类: {downloaded_count} 种")
        print(f"  · 已成功上传的鸟类: {uploaded_count} 种")
        print(f"  · 仍缺本地图片的鸟类: {len(all_missing_local_set)} 种")
        print(f"  · 缺少 cloudinary JSON 的鸟类: {len(all_missing_json_set)} 种")
        total_sounds_success = sum(item.get("sounds_success", 0) for item in successful)
        total_sounds_failed = sum(item.get("sounds_failed", 0) for item in successful)
        if total_sounds_success > 0 or total_sounds_failed > 0:
            print(f"  · 鸟叫声下载成功: {total_sounds_success} 种")
            if total_sounds_failed > 0:
                print(f"  · 鸟叫声下载失败: {total_sounds_failed} 种")

    if extended_range_locs:
        print(f"\n⚠️  以下 {len(extended_range_locs)} 个地点使用30天扩展范围才抓取到数据（可能近期观测较少）：")
        for _loc in extended_range_locs:
            print(f"  - {_loc}")

    print("\n🧾 手动步骤提醒：")
    print("1. 检查 images/<slug>/ 中新下载的照片，将不合适的图片 public_id 写入 config/需要删除图片名单，")
    print("   然后运行: bash tools/delete_images_from_config.sh -y")
    print("2. 检查 Cloudinary 中新上传的鸟叫声，确认音频质量（如需删除，同上）。")

    all_priority_slugs = set()
    for item in summary:
        all_priority_slugs.update(item.get("downloads_raw") or [])
    if remaining_all_missing:
        all_priority_slugs.update(remaining_all_missing)
    if all_priority_slugs:
        with _cl.redirect_stdout(_io.StringIO()):
            generate_html(highlight_slugs=list(all_priority_slugs), priority_slugs=list(all_priority_slugs))
        print(f"✅ HTML 已更新（{len(all_priority_slugs)} 种待检查鸟类排在最前）")

    if successful and all_downloads:
        html_file = PROJECT_ROOT / "examples" / "gallery_all_cloudinary.html"
        try_open_local_html(html_file)

    return 0 if successful else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n用户取消。")
        sys.exit(1)
