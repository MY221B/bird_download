#!/usr/bin/env python3
"""
批量刷新所有地点的鸟单并更新图片/JSON/展示数据
"""

import argparse
import csv
import json
import os
import re
import shutil
import subprocess
import sys
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
BIRD_INFO_CACHE = load_all_birds_csv()


def parse_args():
    parser = argparse.ArgumentParser(
        description="按地点批量刷新鸟类图片并复制 Cloudinary JSON"
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
    """
    构建 API 查询的 payload
    
    query_level 可选值:
    - "point" (默认): 地点级别查询，使用 pointname
    - "district": 区县级别查询，清空 pointname
    - "city": 城市级别查询，清空 district 和 pointname
    - "province": 省级别查询，清空 city、district 和 pointname
    
    district_override: 覆盖 entry 中的 district 字段（用于多区县查询）
    """
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
    
    # 根据查询级别清空相应字段
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
    """
    根据地点配置获取鸟种数据
    
    支持不同的查询级别:
    - point: 地点级别，使用 point_aliases 列表查询
    - district: 区县级别，查询整个区县（支持 districts 数组查询多个区县）
    - city: 城市级别，查询整个城市
    - province: 省级别，查询整个省份
    """
    query_level = entry.get("query_level", "point")
    location_name = entry.get("name", "未知地点")
    combined = OrderedDict()
    
    # 根据查询级别决定查询方式
    if query_level == "district":
        # 区县级别查询：支持单个或多个区县
        districts = entry.get("districts", [])
        
        if districts:
            # 多区县查询：遍历每个区县
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
            # 单区县查询：使用配置中的 district 字段
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
        # 省级或城市级别查询
        level_names = {
            "province": "省级别",
            "city": "城市级别"
        }
        level_name = level_names.get(query_level, query_level)
        print(f"🔐 {location_name} - {level_name}查询: 调用 API ...")
        
        payload = build_payload(entry, start, end, None, query_level=query_level)
        try:
            records = fetch_birds_for_payload(payload)
            print(f"✅ {level_name}: 返回 {len(records)} 条记录")
            for record in records:
                key = (record.chinese, record.scientific)
                if key not in combined:
                    combined[key] = record
        except Exception as exc:
            print(f"⚠️  {level_name}查询失败: {exc}")
            raise RuntimeError(f"{level_name}查询失败: {exc}")
    
    else:
        # 地点级别查询（默认）：使用 point_aliases
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
    # 使用新的文件夹结构：城市/地点/日期
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

    # 清理旧日期文件夹，只保留当前 report_code（永不删除 000000 静态数据集）
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

    for entry in locations:
        loc_id = entry.get("id") or entry.get("name")
        loc_name = entry.get("name", loc_id)
        print("\n" + "=" * 80)
        print(f"🌍 处理地点: {loc_name} ({loc_id})")

        try:
            start_date, end_date = resolve_date_range(entry, args)
        except ValueError as exc:
            print(f"❌ 日期错误: {exc}")
            summary.append(
                {"location": loc_name, "status": "日期错误", "details": str(exc)}
            )
            continue

        location_dir = run_dir / loc_id
        location_dir.mkdir(parents=True, exist_ok=True)
        text_file = location_dir / "birds.txt"
        csv_file = location_dir / "birds.csv"

        try:
            records = fetch_species_for_location(entry, start_date, end_date, text_file)
        except Exception as exc:
            print(f"❌ 抓取失败: {exc}")
            summary.append(
                {"location": loc_name, "status": "抓取失败", "details": str(exc)}
            )
            continue

        species_count = len(records)
        print(f"📊 {loc_name} 去重鸟种: {species_count}")

        if species_count < max(1, args.min_species):
            print(
                f"⚠️  少于 {args.min_species} 种（当前 {species_count} 种），跳过该地点以保留上次报告"
            )
            summary.append(
                {
                    "location": loc_name,
                    "status": "已跳过",
                    "details": f"{species_count} 种，少于 {args.min_species} 种阈值",
                }
            )
            continue

        slug_info = write_csv_from_records(records, csv_file)

        merge_with_all_birds_csv(csv_file)
        missing_local = check_missing_birds(csv_file)
        downloads_for_log = sorted(set(missing_local))
        remaining_local = list(missing_local)
        for attempt in range(1, MAX_RETRIES + 1):
            if not remaining_local:
                break
            print(f"🔁 下载缺失鸟类，第 {attempt}/{MAX_RETRIES} 次尝试（{len(remaining_local)} 种）")
            ok = download_birds(csv_file, remaining_local)
            if not ok:
                print("⚠️  下载命令失败，停止重试")
                break
            # 重新检查：检查本地图片文件
            # 如果本地有图片，说明下载成功；后续会上传，所以这里只检查本地图片
            new_missing = []
            for slug in remaining_local:
                bird_path = PROJECT_ROOT / "images" / slug
                if not bird_dir_has_acceptable_local_images(bird_path):
                    new_missing.append(slug)
            remaining_local = new_missing
        if remaining_local:
            print(f"⚠️  仍有 {len(remaining_local)} 种鸟类没有成功下载本地图片：{', '.join(remaining_local)}")

        missing_cloud = check_missing_cloudinary(csv_file)
        remaining_cloud = list(missing_cloud)
        for attempt in range(1, MAX_RETRIES + 1):
            if not remaining_cloud:
                break
            print(f"🔁 上传缺失鸟类到 Cloudinary，第 {attempt}/{MAX_RETRIES} 次尝试（{len(remaining_cloud)} 种）")
            ok = upload_to_cloudinary(remaining_cloud, csv_file)
            if not ok:
                print("⚠️  上传命令失败，停止重试")
                break
            new_missing_cloud = check_missing_cloudinary(csv_file)
            remaining_cloud = [slug for slug in new_missing_cloud if slug in remaining_cloud]
        if remaining_cloud:
            print(f"⚠️  仍有 {len(remaining_cloud)} 种鸟类未上传至 Cloudinary：{', '.join(remaining_cloud)}")

        update_bird_info(csv_file)

        slugs = read_slugs_from_csv(csv_file)
        report_code = end_date.strftime("%y%m%d")
        
        # 下载和上传鸟叫声
        success_sounds, failed_sounds = download_and_upload_sounds(slugs, location_dir)
        
        # 复制 JSON 到 location_birds（包含新下载的 sounds）
        dest_dir, copied, missing_copy = copy_json_to_location(
            slugs, loc_name, report_code
        )

        for slug in slugs:
            if slug not in combined_seen:
                combined_slugs.append(slug)
                combined_seen.add(slug)

        # 在上传完成后，重新检查本地图片和 Cloudinary JSON 状态
        # 逻辑：
        # 1. 如果 Cloudinary JSON 存在且有照片 → 上传成功，本地图片肯定存在 → 不应该显示在"仍缺本地图片"中
        # 2. 如果 Cloudinary JSON 不存在，但本地有图片 → 下载成功但上传失败 → 不应该显示在"仍缺本地图片"中（因为本地有图片）
        # 3. 如果 Cloudinary JSON 不存在，且本地也没有图片 → 下载失败 → 应该显示在"仍缺本地图片"中
        final_missing_local = []
        for slug in remaining_local:
            # 检查本地图片（仅计 ≥10KB 的合格图）
            bird_path = PROJECT_ROOT / "images" / slug
            has_images = bird_dir_has_acceptable_local_images(bird_path)

            # 只有真正没有本地图片的才显示在"仍缺本地图片"中
            # 如果本地有图片但 Cloudinary JSON 不存在，说明上传失败，会显示在"缺少 cloudinary JSON"中
            if not has_images:
                final_missing_local.append(slug)
        
        summary.append(
            {
                "location": loc_name,
                "status": "已更新",
                "details": f"{species_count} 种 -> 复制 {copied} JSON 至 {dest_dir}",
                "downloads": format_slug_list(downloads_for_log, slug_info),
                "downloads_raw": downloads_for_log,  # 保存原始 slug 列表
                "missing_local": format_slug_list(final_missing_local, slug_info),
                "missing_json": format_slug_list(missing_copy, slug_info),
                "sounds_success": len(success_sounds),
                "sounds_failed": len(failed_sounds),
                "sounds_failed_details": failed_sounds,
            }
        )

    # 收集所有成功处理的地点（包括数量较少但仍处理的地点）
    successful = [item for item in summary if item["status"].startswith("已更新")]

    if successful:
        print("\n🔁 全局更新 all_birds.csv / HTML ...")
        update_all_birds_csv()
        
        # 收集所有需要高亮的鸟类（即所有下载的鸟类）
        highlight_slugs = []
        for item in summary:
            downloads_raw = item.get("downloads_raw") or []
            highlight_slugs.extend(downloads_raw)
        
        # 去重
        highlight_slugs = list(set(highlight_slugs))
        
        # 暂时生成HTML（此时还没有收集到所有需要下载/检查的鸟类）
        generate_html(highlight_slugs, priority_slugs=highlight_slugs)

        if combined_slugs:
            combined_csv = run_dir / "combined_reorder.csv"
            with open(combined_csv, "w", encoding="utf-8", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["slug", "english_name", "scientific_name", "wikipedia_page"])
                for slug in combined_slugs:
                    writer.writerow([slug, "", "", ""])
            reorder_new_birds(combined_csv)

    # 检查 all_birds.csv 中所有缺少 cloudinary JSON 的鸟类
    # 注意：在 update_all_birds_csv() 之后执行，确保使用最新的 all_birds.csv
    print("\n" + "=" * 80)
    print("🔍 检查 all_birds.csv 中所有缺少 cloudinary JSON 的鸟类...")
    all_birds_map = load_all_birds_csv()
    print(f"📋 从 all_birds.csv 加载了 {len(all_birds_map)} 个鸟类")
    
    all_missing_birds = []
    birds_with_json_and_photos = []
    birds_with_json_but_no_photos = []
    birds_without_json = []
    remaining_all_missing = []  # 在更外层定义，以便最后生成HTML时使用
    
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
    
    # 详细日志输出
    print(f"\n📊 检查结果统计:")
    print(f"  ✅ 有 JSON 且有照片: {len(birds_with_json_and_photos)} 个")
    print(f"  ⚠️  有 JSON 但无照片: {len(birds_with_json_but_no_photos)} 个")
    print(f"  ❌ 没有 JSON 文件: {len(birds_without_json)} 个")
    print(f"  📋 总计需要处理: {len(all_missing_birds)} 个")
    
    if birds_with_json_but_no_photos:
        print(f"\n⚠️  有 JSON 但无照片的鸟类（前10个）:")
        for slug in birds_with_json_but_no_photos[:10]:
            bird_info = all_birds_map.get(slug, {})
            name = bird_info.get('chinese_name', '') or bird_info.get('english_name', slug)
            print(f"    - {slug} ({name})")
        if len(birds_with_json_but_no_photos) > 10:
            print(f"    ... 还有 {len(birds_with_json_but_no_photos) - 10} 个")
    
    if birds_without_json:
        print(f"\n❌ 没有 JSON 文件的鸟类（前10个）:")
        for slug in birds_without_json[:10]:
            bird_info = all_birds_map.get(slug, {})
            name = bird_info.get('chinese_name', '') or bird_info.get('english_name', slug)
            print(f"    - {slug} ({name})")
        if len(birds_without_json) > 10:
            print(f"    ... 还有 {len(birds_without_json) - 10} 个")
    
    if all_missing_birds:
        print(f"\n📋 发现 {len(all_missing_birds)} 个鸟类缺少 cloudinary JSON，尝试下载...")
        # 创建一个临时 CSV 文件包含所有缺失的鸟类
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
        
        # 尝试下载这些缺失的鸟类
        remaining_all_missing = list(all_missing_birds)  # 更新外层变量
        for attempt in range(1, MAX_RETRIES + 1):
            if not remaining_all_missing:
                break
            print(f"\n🔁 下载 all_birds.csv 中缺失的鸟类，第 {attempt}/{MAX_RETRIES} 次尝试（{len(remaining_all_missing)} 种）")
            ok = download_birds(temp_all_missing_csv, remaining_all_missing)
            if not ok:
                print("⚠️  下载命令失败，停止重试")
                break
            # 重新检查缺失的鸟类
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
        
        # 检查哪些鸟类成功下载了图片（本地有图片）
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
            if len(remaining_all_missing) <= 20:
                for slug in remaining_all_missing:
                    bird_info = all_birds_map.get(slug, {})
                    name = bird_info.get('chinese_name', '') or bird_info.get('english_name', slug)
                    print(f"    - {slug} ({name})")
            else:
                for slug in remaining_all_missing[:10]:
                    bird_info = all_birds_map.get(slug, {})
                    name = bird_info.get('chinese_name', '') or bird_info.get('english_name', slug)
                    print(f"    - {slug} ({name})")
                print(f"    ... 还有 {len(remaining_all_missing) - 10} 个")
        else:
            print(f"\n✅ 所有缺失的鸟类已成功下载")
        
        # 只上传有本地图片的鸟类到 Cloudinary
        # 检查哪些鸟类需要上传（JSON文件不存在或没有有效照片数据）
        print(f"\n☁️  检查需要上传到 Cloudinary 的鸟类...")
        all_missing_cloud = []
        birds_already_uploaded = []
        for slug in birds_with_images:
            json_file = PROJECT_ROOT / "cloudinary_uploads" / f"{slug}_cloudinary_urls.json"
            has_cloudinary_data = False
            photo_count = 0
            if json_file.exists():
                try:
                    with open(json_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        for source in ['macaulay', 'inaturalist', 'wikimedia', 'avibase']:
                            if source in data and isinstance(data[source], list):
                                photo_count += len(data[source])
                        has_cloudinary_data = photo_count > 0
                except Exception:
                    pass
            
            if has_cloudinary_data:
                birds_already_uploaded.append(slug)
                bird_info = all_birds_map.get(slug, {})
                name = bird_info.get('chinese_name', '') or bird_info.get('english_name', slug)
                print(f"  ✅ {slug} ({name}): 已上传（{photo_count} 张照片）")
            else:
                all_missing_cloud.append(slug)
                bird_info = all_birds_map.get(slug, {})
                name = bird_info.get('chinese_name', '') or bird_info.get('english_name', slug)
                print(f"  ❌ {slug} ({name}): 需要上传（JSON文件{'存在但无照片' if json_file.exists() else '不存在'}）")
        
        print(f"\n📊 上传检查结果:")
        print(f"  ✅ 已上传: {len(birds_already_uploaded)} 个")
        print(f"  ❌ 需要上传: {len(all_missing_cloud)} 个")
        
        if all_missing_cloud:
            print(f"\n🔁 上传 {len(all_missing_cloud)} 个有本地图片但缺少 cloudinary JSON 的鸟类到 Cloudinary...")
            upload_to_cloudinary(all_missing_cloud, temp_all_missing_csv)
        else:
            if birds_with_images:
                print(f"\n✅ 所有有本地图片的鸟类都已上传到 Cloudinary")
            else:
                print(f"\n⚠️  没有鸟类成功下载图片，跳过上传步骤")
    else:
        print("\n✅ all_birds.csv 中所有鸟类都有 cloudinary JSON")

    print("\n" + "=" * 80)
    print("📋 任务摘要")
    
    # 汇总所有需要下载和缺本地图片的鸟类
    all_downloads = set()
    all_missing_local = set()
    all_missing_json = set()
    
    for item in summary:
        print(f"- {item['location']}: {item['status']} ({item.get('details','')})")
        downloads = item.get("downloads") or []
        missing_local = item.get("missing_local") or []
        missing_json = item.get("missing_json") or []
        
        all_downloads.update(downloads)
        all_missing_local.update(missing_local)
        all_missing_json.update(missing_json)
    
    # 汇总输出
    if all_downloads or all_missing_local or all_missing_json:
        downloaded_count = len(all_downloads) - len(all_missing_local)
        uploaded_count = len(all_downloads) - len(all_missing_json)
        
        print(f"\n📊 汇总统计:")
        print(f"  · 缺失的新鸟类: {len(all_downloads)} 种")
        print(f"  · 已成功下载的鸟类: {downloaded_count} 种")
        print(f"  · 已成功上传的鸟类: {uploaded_count} 种（需检查图片）")
        print(f"  · 仍缺本地图片的鸟类: {len(all_missing_local)} 种")
        print(f"  · 缺少 cloudinary JSON 的鸟类: {len(all_missing_json)} 种")
        
        # 统计声音下载情况
        total_sounds_success = sum(item.get("sounds_success", 0) for item in successful)
        total_sounds_failed = sum(item.get("sounds_failed", 0) for item in successful)
        if total_sounds_success > 0 or total_sounds_failed > 0:
            print(f"  · 鸟叫声下载成功: {total_sounds_success} 种")
            if total_sounds_failed > 0:
                print(f"  · 鸟叫声下载失败: {total_sounds_failed} 种")
        
        if all_downloads:
            print(f"\n📥 需要下载/检查的鸟类（{len(all_downloads)} 种）:")
            for bird in sorted(all_downloads):
                print(f"    - {bird}")
        
        if all_missing_local:
            print(f"\n❌ 仍缺本地图片的鸟类（{len(all_missing_local)} 种）:")
            for bird in sorted(all_missing_local):
                print(f"    - {bird}")
        
        if all_missing_json:
            print(f"\n☁️  缺少 cloudinary JSON 的鸟类（{len(all_missing_json)} 种）:")
            for bird in sorted(all_missing_json):
                print(f"    - {bird}")
        
        # 显示声音下载失败的详细信息
        all_sounds_failed = []
        for item in successful:
            failed_details = item.get("sounds_failed_details", [])
            all_sounds_failed.extend(failed_details)
        
        if all_sounds_failed:
            print(f"\n🔊 鸟叫声下载失败的鸟类（{len(all_sounds_failed)} 种）:")
            for bird in all_sounds_failed[:20]:  # 最多显示20个
                name = bird.get('chinese_name') or bird['slug']
                reason = bird.get('reason', '未知原因')
                print(f"    - {name} ({bird['slug']}): {reason}")
            if len(all_sounds_failed) > 20:
                print(f"    ... 还有 {len(all_sounds_failed) - 20} 个")

    print("\nℹ️ 说明：列表中的'缺少 cloudinary JSON'代表对应鸟类的图片尚未成功下载或上传。可重跑 `run_weekly_refresh.py --locations <地点>`，或手动使用 `tools/batch_fetch.sh` 与 `tools/upload_to_cloudinary.py` 来补齐。")

    print("\n🧾 手动步骤提醒：")
    print("1. 打开 images/ 或 Cloudinary 后台检查本次新下载的鸟类，删除不合适的照片。")
    print("2. 检查 Cloudinary 中新上传的鸟叫声，确认音频质量。")
    print("3. 将不合适的图片 public_id 写入 config/需要删除图片名单，运行 `bash tools/delete_images_from_config.sh -y`（如需要）。")
    print("4. 登录 Lovable，触发站点重新部署/推送更新。")
    print("5. 通过 `feather-flash-quiz/location_birds/<地点>/<日期>` 查看复制结果。")
    print("\n💡 鸟叫声下载失败的原因通常是：")
    print("   · eBird数据库中无此物种记录")
    print("   · Macaulay Library中找不到该物种的音频")
    print("   · 网络问题导致下载失败")
    print("   可以手动使用 `python3 tools/batch_download_sounds.py` 重试")

    # 收集所有需要下载/检查的鸟类（slug格式）
    all_priority_slugs = set()
    all_highlight_slugs = set()
    
    # 从 summary 中收集 downloads_raw
    for item in summary:
        downloads_raw = item.get("downloads_raw") or []
        all_priority_slugs.update(downloads_raw)
        all_highlight_slugs.update(downloads_raw)
    
    # 收集 remaining_all_missing（如果存在）
    if remaining_all_missing:
        all_priority_slugs.update(remaining_all_missing)
        all_highlight_slugs.update(remaining_all_missing)
    
    # 如果有需要下载/检查的鸟类，重新生成HTML，让它们排在最前面并标红
    if all_priority_slugs:
        print(f"\n🔄 重新生成HTML，将 {len(all_priority_slugs)} 个需要下载/检查的鸟类排在最前面并标红...")
        generate_html(highlight_slugs=list(all_highlight_slugs), priority_slugs=list(all_priority_slugs))
    
    # 自动打开 HTML 页面
    if successful and all_downloads:
        html_file = PROJECT_ROOT / "examples" / "gallery_all_cloudinary.html"
        if html_file.exists():
            print(f"\n🌐 正在打开 HTML 页面: {html_file}")
            try:
                subprocess.run(["open", str(html_file)], check=False)
            except Exception as e:
                print(f"⚠️  自动打开失败: {e}，请手动打开 {html_file}")

    return 0 if successful else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n用户取消。")
        sys.exit(1)
