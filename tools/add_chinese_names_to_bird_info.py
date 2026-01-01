#!/usr/bin/env python3
"""
为所有缺少中文名的鸟类在bird_info中补上中文名
"""

import json
import csv
from pathlib import Path

UPLOAD_DIR = Path('cloudinary_uploads')
LOCATION_BIRDS_DIR = Path('feather-flash-quiz/location_birds')
ALL_BIRDS_CSV = Path('all_birds.csv')

def load_chinese_names_from_location_birds():
    """从location_birds目录的JSON文件中加载中文名"""
    chinese_map = {}
    if not LOCATION_BIRDS_DIR.exists():
        return chinese_map
    
    for json_file in LOCATION_BIRDS_DIR.rglob('*_cloudinary_urls.json'):
        try:
            data = json.loads(json_file.read_text(encoding='utf-8'))
            bird_info = data.get('bird_info') or {}
            slug = bird_info.get('slug')
            chinese_name = bird_info.get('chinese_name')
            if slug and chinese_name:
                chinese_map[slug] = chinese_name
        except Exception:
            continue
    
    return chinese_map

def load_bird_info_from_csv():
    """从all_birds.csv加载鸟类信息"""
    bird_map = {}
    if not ALL_BIRDS_CSV.exists():
        return bird_map
    
    try:
        with open(ALL_BIRDS_CSV, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            data_lines = [line for line in lines if line.strip() and not line.strip().startswith('#')]
            if data_lines:
                reader = csv.DictReader(data_lines)
                for row in reader:
                    slug = row.get('slug')
                    if slug:
                        bird_map[slug] = {
                            'english_name': row.get('english_name', '').strip('"'),
                            'scientific_name': row.get('scientific_name', '').strip('"')
                        }
    except Exception:
        pass
    
    return bird_map

def get_chinese_name_from_known_sources(slug):
    """从已知来源获取中文名（作为最后备选）"""
    # 已知的中文名映射（从文档和新增鸟单.txt中提取）
    known_names = {
        'bluetail': '红胁蓝尾鸲',  # Red-flanked Bluetail
        'chinese_thrush': '斑鸫',  # 从文档中看到
        'common_coot': '白骨顶',  # 和eurasian_coot一样
        'eurasian_wren': '鹪鹩',  # 从新增鸟单.txt
        'grey_heron': '苍鹭',  # 和gray_heron一样
        'japanese_waxwing': '小太平鸟',  # 从新增鸟单.txt
        'little_egret': '小白鹭',  # 从文档中看到
        'silver_throated_bushtit': '银喉长尾山雀',  # 从新增鸟单.txt
        'water_pipit': '水鹨',  # 从新增鸟单.txt
    }
    return known_names.get(slug)

def update_bird_info_with_chinese_names():
    """更新所有缺少中文名的bird_info"""
    print("=" * 60)
    print("为缺少中文名的鸟类补上中文名")
    print("=" * 60)
    print()
    
    # 加载中文名映射
    print("📋 加载中文名数据...")
    chinese_map = load_chinese_names_from_location_birds()
    print(f"   从 location_birds 加载了 {len(chinese_map)} 个中文名")
    
    bird_map = load_bird_info_from_csv()
    print(f"   从 all_birds.csv 加载了 {len(bird_map)} 个鸟类信息")
    print()
    
    # 检查所有JSON文件
    updated_count = 0
    missing_count = 0
    missing_birds = []
    
    print("🔍 检查所有鸟类...")
    print("-" * 60)
    
    for json_file in sorted(UPLOAD_DIR.glob('*_cloudinary_urls.json')):
        slug = json_file.stem.replace('_cloudinary_urls', '')
        
        try:
            data = json.loads(json_file.read_text(encoding='utf-8'))
            
            # 确保bird_info存在
            if 'bird_info' not in data:
                data['bird_info'] = {}
            
            bird_info = data['bird_info']
            bird_info['slug'] = slug
            
            # 检查是否缺少中文名
            chinese_name = bird_info.get('chinese_name', '')
            
            if not chinese_name:
                # 尝试从不同来源获取
                chinese_name = chinese_map.get(slug, '')
                
                # 如果还是没有，尝试从已知来源获取
                if not chinese_name:
                    chinese_name = get_chinese_name_from_known_sources(slug)
                
                if not chinese_name:
                    # 如果还是没有，标记为缺失
                    missing_count += 1
                    missing_birds.append(slug)
                    print(f"  ❌ {slug}: 缺少中文名")
                    continue
                
                # 更新bird_info
                bird_info['chinese_name'] = chinese_name
                
                # 同时确保英文名和学名存在
                if not bird_info.get('english_name') and slug in bird_map:
                    bird_info['english_name'] = bird_map[slug]['english_name']
                if not bird_info.get('scientific_name') and slug in bird_map:
                    bird_info['scientific_name'] = bird_map[slug]['scientific_name']
                
                # 保存更新后的JSON
                json_file.write_text(
                    json.dumps(data, ensure_ascii=False, indent=2),
                    encoding='utf-8'
                )
                
                updated_count += 1
                print(f"  ✅ {slug}: 已添加中文名 '{chinese_name}'")
            else:
                print(f"  ✓  {slug}: 已有中文名 '{chinese_name}'")
        
        except Exception as e:
            print(f"  ⚠️  {slug}: 处理失败 - {e}")
    
    print()
    print("=" * 60)
    print(f"统计:")
    print(f"  ✅ 已更新: {updated_count} 个鸟类")
    print(f"  ❌ 仍缺少: {missing_count} 个鸟类")
    print("=" * 60)
    
    if missing_birds:
        print()
        print("仍缺少中文名的鸟类:")
        print("-" * 60)
        for bird in missing_birds:
            print(f"  - {bird}")
        print()
        print("提示: 这些鸟类需要手动添加中文名，或者从其他来源获取")
    
    return updated_count, missing_count, missing_birds

if __name__ == '__main__':
    update_bird_info_with_chinese_names()

