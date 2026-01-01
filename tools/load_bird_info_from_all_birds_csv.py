#!/usr/bin/env python3
"""
从 all_birds.csv 加载鸟类信息的工具函数
"""

import csv
from pathlib import Path

def load_all_birds_csv():
    """从 all_birds.csv 加载所有鸟类信息"""
    csv_file = Path('all_birds.csv')
    bird_info_map = {}
    
    if not csv_file.exists():
        return bird_info_map
    
    try:
        with open(csv_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            data_lines = [line for line in lines if line.strip() and not line.strip().startswith('#')]
            
            # 检查是否有chinese_name字段
            header_line = None
            for i, line in enumerate(lines):
                if line.strip().startswith('#'):
                    header_line = i
                    break
            
            has_chinese = False
            if header_line is not None:
                header = lines[header_line].strip()
                has_chinese = 'chinese_name' in header.lower()
            
            if data_lines:
                if has_chinese:
                    reader = csv.DictReader(data_lines, fieldnames=['slug', 'chinese_name', 'english_name', 'scientific_name', 'wikipedia_page'])
                else:
                    reader = csv.DictReader(data_lines, fieldnames=['slug', 'english_name', 'scientific_name', 'wikipedia_page'])
                
                for row in reader:
                    slug = row.get('slug', '').strip()
                    if slug and slug != 'slug':  # 跳过可能的表头
                        bird_info_map[slug] = {
                            'chinese_name': row.get('chinese_name', '').strip('"') if has_chinese else '',
                            'english_name': row.get('english_name', '').strip('"'),
                            'scientific_name': row.get('scientific_name', '').strip('"'),
                            'wikipedia_page': row.get('wikipedia_page', '').strip()
                        }
    except Exception as e:
        print(f"⚠️  读取 all_birds.csv 失败: {e}")
    
    return bird_info_map

def get_bird_info_from_all_birds_csv(slug):
    """从 all_birds.csv 获取单个鸟类的信息"""
    bird_info_map = load_all_birds_csv()
    return bird_info_map.get(slug)

