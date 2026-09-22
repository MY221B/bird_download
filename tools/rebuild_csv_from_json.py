#!/usr/bin/env python3
"""
从 cloudinary_uploads/*_cloudinary_urls.json 合并补全 all_birds.csv。

不会用「仅 JSON 中 bird_info 完整的子集」覆盖整表——旧行为会静默丢掉
CSV 里仍存在、但 JSON 缺英文/学名的条目。
"""

import csv
import json
from pathlib import Path


def extract_all_bird_info():
    """从所有JSON文件中提取完整的鸟类信息"""
    upload_dir = Path('cloudinary_uploads')
    if not upload_dir.exists():
        print("❌ cloudinary_uploads 目录不存在")
        return []

    bird_info_list = []
    json_files = list(upload_dir.glob('*_cloudinary_urls.json'))

    for json_file in sorted(json_files):
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            bird_info = data.get('bird_info', {})
            if bird_info:
                slug = bird_info.get('slug', '')
                chinese_name = bird_info.get('chinese_name', '')
                english_name = bird_info.get('english_name', '')
                scientific_name = bird_info.get('scientific_name', '')

                # 只添加有英文名和学名的记录
                if slug and english_name and scientific_name:
                    wikipedia_page = english_name.replace(' ', '_')

                    bird_info_list.append({
                        'slug': slug,
                        'chinese_name': chinese_name,
                        'english_name': english_name,
                        'scientific_name': scientific_name,
                        'wikipedia_page': wikipedia_page
                    })
        except Exception as e:
            print(f"⚠️  读取 {json_file} 失败: {e}")

    return bird_info_list


def load_existing_csv_rows(csv_file: Path):
    """保留现有 CSV 行，避免重建时丢条目。"""
    existing = {}
    if not csv_file.exists():
        return existing
    with open(csv_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    data_lines = [line for line in lines if line.strip() and not line.strip().startswith('#')]
    if not data_lines:
        return existing
    has_chinese = any('chinese_name' in line.lower() for line in lines if line.strip().startswith('#'))
    fieldnames = (
        ['slug', 'chinese_name', 'english_name', 'scientific_name', 'wikipedia_page']
        if has_chinese
        else ['slug', 'english_name', 'scientific_name', 'wikipedia_page']
    )
    for row in csv.DictReader(data_lines, fieldnames=fieldnames):
        slug = (row.get('slug') or '').strip().strip('"')
        if not slug or slug == 'slug':
            continue
        existing[slug] = {
            'slug': slug,
            'chinese_name': (row.get('chinese_name', '') if has_chinese else '').strip().strip('"'),
            'english_name': (row.get('english_name', '') or '').strip().strip('"'),
            'scientific_name': (row.get('scientific_name', '') or '').strip().strip('"'),
            'wikipedia_page': (row.get('wikipedia_page', '') or '').strip(),
        }
    return existing


def rebuild_csv():
    """合并 JSON bird_info 到 all_birds.csv，保留既有 CSV 行。"""
    bird_info_list = extract_all_bird_info()
    csv_file = Path('all_birds.csv')
    existing = load_existing_csv_rows(csv_file)

    if not bird_info_list and not existing:
        print("❌ 没有找到任何鸟类信息")
        return

    by_slug = dict(existing)
    updated = 0
    added = 0
    for bird in bird_info_list:
        slug = bird['slug']
        if slug in by_slug:
            prev = by_slug[slug]
            merged = dict(prev)
            for key in ('chinese_name', 'english_name', 'scientific_name', 'wikipedia_page'):
                if bird.get(key):
                    merged[key] = bird[key]
            if merged != prev:
                updated += 1
            by_slug[slug] = merged
        else:
            by_slug[slug] = bird
            added += 1

    rows = sorted(by_slug.values(), key=lambda x: x['slug'])

    with open(csv_file, 'w', encoding='utf-8') as f:
        f.write('# slug,chinese_name,english_name,scientific_name,wikipedia_page\n')
        for bird in rows:
            chinese = bird.get('chinese_name', '')
            english = bird.get('english_name', '')
            scientific = bird.get('scientific_name', '')
            wiki = bird.get('wikipedia_page', '') or (english.replace(' ', '_') if english else '')
            f.write(f'{bird["slug"]},"{chinese}","{english}","{scientific}",{wiki}\n')

    print(f"✅ 已更新 {csv_file}")
    print(f"📊 共 {len(rows)} 条记录（新增 {added}，补全/更新 {updated}，保留原有 {len(existing)}）")


if __name__ == '__main__':
    print("🔧 开始从JSON文件合并更新 all_birds.csv...\n")
    rebuild_csv()
    print("\n✅ 完成！")

