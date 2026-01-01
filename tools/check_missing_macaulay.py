#!/usr/bin/env python3
"""
检查哪些鸟类缺少 Macaulay 照片
"""

import os
import csv
import json
from pathlib import Path

def check_missing_macaulay():
    """检查所有鸟类中哪些缺少 Macaulay 照片"""
    images_dir = Path("images")
    all_birds_file = Path("all_birds.csv")
    
    # 读取所有鸟类列表
    birds = []
    if all_birds_file.exists():
        with open(all_birds_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            # 找到实际的数据行（跳过注释）
            data_lines = [line for line in lines if line.strip() and not line.strip().startswith('#')]
            if data_lines:
                # 第一行应该是标题行
                reader = csv.DictReader(data_lines)
                for row in reader:
                    if 'slug' in row:
                        birds.append({
                            'slug': row['slug'],
                            'english_name': row.get('english_name', ''),
                            'scientific_name': row.get('scientific_name', ''),
                            'wikipedia_page': row.get('wikipedia_page', '')
                        })
    
    # 补充：从images目录读取CSV中可能没有的鸟类
    csv_slugs = {b['slug'] for b in birds}
    for bird_dir in images_dir.iterdir():
        if bird_dir.is_dir() and bird_dir.name not in csv_slugs:
            birds.append({
                'slug': bird_dir.name,
                'english_name': '',
                'scientific_name': '',
                'wikipedia_page': ''
            })
    
    missing_birds = []
    
    print("=" * 60)
    print("检查缺少 Macaulay 照片的鸟类")
    print("=" * 60)
    print()
    
    for bird in birds:
        slug = bird['slug']
        bird_path = images_dir / slug
        macaulay_dir = bird_path / "macaulay"
        
        # 检查 macaulay 目录是否存在且有照片
        has_photos = False
        if macaulay_dir.exists():
            # 检查是否有 .jpg 或 .jpeg 文件
            jpg_files = list(macaulay_dir.glob("*.jpg")) + list(macaulay_dir.glob("*.jpeg"))
            if jpg_files:
                has_photos = True
        
        # 也检查元数据文件
        metadata_file = bird_path / "download_metadata.json"
        has_metadata = False
        if metadata_file.exists():
            try:
                with open(metadata_file, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)
                    if metadata.get('macaulay') and len(metadata.get('macaulay', [])) > 0:
                        has_metadata = True
            except:
                pass
        
        if not has_photos and not has_metadata:
            missing_birds.append(bird)
            print(f"❌ {slug}: 缺少 Macaulay 照片")
        else:
            print(f"✅ {slug}: 已有 Macaulay 照片")
    
    print()
    print("=" * 60)
    print(f"统计: 共 {len(birds)} 个鸟类，{len(missing_birds)} 个缺少 Macaulay 照片")
    print("=" * 60)
    print()
    
    if missing_birds:
        print("缺少 Macaulay 照片的鸟类列表:")
        print("-" * 60)
        for bird in missing_birds:
            print(f"  - {bird['slug']}: {bird['english_name']} ({bird['scientific_name']})")
        print()
        
        # 保存到文件
        output_file = Path("missing_macaulay_birds.txt")
        with open(output_file, 'w', encoding='utf-8') as f:
            for bird in missing_birds:
                f.write(f"{bird['slug']}\t{bird['english_name']}\t{bird['scientific_name']}\t{bird['wikipedia_page']}\n")
        print(f"📄 已保存到: {output_file}")
        print()
        print("可以使用以下命令下载缺失的照片:")
        print("-" * 60)
        for bird in missing_birds:
            wiki_page = bird['wikipedia_page'] or bird['english_name'].replace(' ', '_')
            print(f"./tools/fetch_four_sources.sh {bird['slug']} \"{bird['english_name']}\" \"{bird['scientific_name']}\" {wiki_page}")
    
    return missing_birds

if __name__ == "__main__":
    check_missing_macaulay()

