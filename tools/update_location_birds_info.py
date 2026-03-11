#!/usr/bin/env python3
"""
补齐 location_birds 目录下所有 JSON 文件的 bird_info 字段
从 all_birds.csv 读取英文名、学名，补充缺失的 english_name 和 scientific_name
"""

import json
import csv
from pathlib import Path

# 项目根目录（脚本在 tools/ 下，上一级是根目录）
PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOCATION_BIRDS_DIR = PROJECT_ROOT / 'feather-flash-quiz' / 'location_birds'
CSV_FILE = PROJECT_ROOT / 'all_birds.csv'


def load_bird_info_from_csv():
    """从 all_birds.csv 加载所有鸟类信息"""
    bird_info_map = {}
    if not CSV_FILE.exists():
        print(f"⚠️  {CSV_FILE} 不存在，跳过从CSV读取")
        return bird_info_map

    try:
        with open(CSV_FILE, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            data_lines = [line for line in lines if line.strip() and not line.strip().startswith('#')]

            if data_lines:
                header_line = None
                for i, line in enumerate(lines):
                    if line.strip().startswith('#'):
                        header_line = i
                        break

                has_chinese = False
                if header_line is not None:
                    header = lines[header_line].strip()
                    has_chinese = 'chinese_name' in header.lower()

                fieldnames = ['slug', 'chinese_name', 'english_name', 'scientific_name', 'wikipedia_page'] if has_chinese else ['slug', 'english_name', 'scientific_name', 'wikipedia_page']
                reader = csv.DictReader(data_lines, fieldnames=fieldnames)

                for row in reader:
                    slug = row.get('slug', '').strip()
                    if slug and slug != 'slug':
                        bird_info_map[slug] = {
                            'chinese_name': row.get('chinese_name', '').strip('"') if has_chinese else '',
                            'english_name': row.get('english_name', '').strip('"'),
                            'scientific_name': row.get('scientific_name', '').strip('"')
                        }
    except Exception as e:
        print(f"❌ 读取 all_birds.csv 失败: {e}")
        import traceback
        traceback.print_exc()

    return bird_info_map


def update_json_file(json_file: Path, bird_info_map: dict) -> bool:
    """更新单个 JSON 文件的 bird_info 字段，只补充缺失的，保留原有值"""
    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        slug = json_file.stem.replace('_cloudinary_urls', '')

        if 'bird_info' not in data:
            data['bird_info'] = {}

        existing_info = data['bird_info']
        updated = False

        if slug in bird_info_map:
            csv_info = bird_info_map[slug]

            if not existing_info.get('chinese_name') and csv_info.get('chinese_name'):
                existing_info['chinese_name'] = csv_info['chinese_name']
                updated = True

            if not existing_info.get('english_name') and csv_info.get('english_name'):
                existing_info['english_name'] = csv_info['english_name']
                updated = True

            if not existing_info.get('scientific_name') and csv_info.get('scientific_name'):
                existing_info['scientific_name'] = csv_info['scientific_name']
                updated = True

        if 'slug' not in existing_info:
            existing_info['slug'] = slug
            updated = True

        if updated:
            with open(json_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            return True

        return False

    except Exception as e:
        print(f"❌ 处理 {json_file} 失败: {e}")
        return False


def main():
    print("🔧 开始补齐 location_birds 中缺失的 bird_info 字段...\n")

    bird_info_map = load_bird_info_from_csv()
    print(f"📋 从 all_birds.csv 加载了 {len(bird_info_map)} 条鸟类信息\n")

    if not LOCATION_BIRDS_DIR.exists():
        print(f"❌ 目录不存在: {LOCATION_BIRDS_DIR}")
        return

    json_files = list(LOCATION_BIRDS_DIR.rglob('*_cloudinary_urls.json'))
    print(f"📁 找到 {len(json_files)} 个 location_birds JSON 文件\n")

    updated_count = 0
    no_csv_count = 0
    skipped_count = 0

    for json_file in sorted(json_files):
        slug = json_file.stem.replace('_cloudinary_urls', '')

        if update_json_file(json_file, bird_info_map):
            rel_path = json_file.relative_to(LOCATION_BIRDS_DIR)
            print(f"✅ {slug} ({rel_path})")
            updated_count += 1
        else:
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                info = data.get('bird_info', {})
                if not info.get('english_name') or not info.get('scientific_name'):
                    if slug not in bird_info_map:
                        no_csv_count += 1
                        if no_csv_count <= 5:  # 只显示前几个
                            print(f"⚠️  {slug} - CSV 中无此记录")
                    else:
                        skipped_count += 1
                else:
                    skipped_count += 1
            except Exception:
                skipped_count += 1

    if no_csv_count > 5:
        print(f"⚠️  ... 共 {no_csv_count} 个物种在 CSV 中无记录")

    print(f"\n{'='*60}")
    print(f"✅ 已补齐: {updated_count} 个文件")
    print(f"ℹ️  跳过（已完整或无需更新）: {skipped_count} 个文件")
    if no_csv_count:
        print(f"⚠️  CSV 无记录: {no_csv_count} 个物种")
    print(f"{'='*60}\n")


if __name__ == '__main__':
    main()
