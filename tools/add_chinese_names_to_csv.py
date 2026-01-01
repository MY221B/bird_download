#!/usr/bin/env python3
"""
为 all_birds.csv 添加中文名字段
从 cloudinary_uploads/*_cloudinary_urls.json 文件中提取中文名
"""

import json
import csv
from pathlib import Path

def load_chinese_names_from_json():
    """从所有JSON文件中提取中文名"""
    upload_dir = Path('cloudinary_uploads')
    if not upload_dir.exists():
        return {}
    
    chinese_names = {}
    json_files = list(upload_dir.glob('*_cloudinary_urls.json'))
    
    for json_file in sorted(json_files):
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            bird_info = data.get('bird_info', {})
            if bird_info:
                slug = bird_info.get('slug', '')
                chinese_name = bird_info.get('chinese_name', '')
                if slug and chinese_name:
                    chinese_names[slug] = chinese_name
        except Exception as e:
            print(f"⚠️  读取 {json_file} 失败: {e}")
    
    return chinese_names

def update_csv_with_chinese_names():
    """更新CSV文件，添加中文名字段"""
    csv_file = Path('all_birds.csv')
    
    if not csv_file.exists():
        print("❌ all_birds.csv 不存在")
        return
    
    # 读取现有CSV
    existing_birds = []
    with open(csv_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        
        # 找到注释行（表头）
        header_line = None
        for i, line in enumerate(lines):
            if line.strip().startswith('#'):
                header_line = i
                break
        
        # 检查是否已有chinese_name字段
        has_chinese = False
        if header_line is not None:
            header = lines[header_line].strip()
            has_chinese = 'chinese_name' in header.lower()
        
        # 找到数据开始行（跳过注释行）
        data_lines = [line for line in lines if line.strip() and not line.strip().startswith('#')]
        
        if data_lines:
            # 读取数据（根据是否有chinese_name字段选择不同的fieldnames）
            if has_chinese:
                reader = csv.DictReader(data_lines, fieldnames=['slug', 'chinese_name', 'english_name', 'scientific_name', 'wikipedia_page'])
            else:
                reader = csv.DictReader(data_lines, fieldnames=['slug', 'english_name', 'scientific_name', 'wikipedia_page'])
            
            for row in reader:
                slug = row.get('slug', '').strip()
                if slug and slug != 'slug':  # 跳过可能的表头
                    existing_birds.append({
                        'slug': slug,
                        'english_name': row.get('english_name', '').strip('"'),
                        'scientific_name': row.get('scientific_name', '').strip('"'),
                        'wikipedia_page': row.get('wikipedia_page', '').strip(),
                        'chinese_name': row.get('chinese_name', '').strip('"') if has_chinese else ''
                    })
    
    # 从JSON文件加载中文名
    chinese_names = load_chinese_names_from_json()
    print(f"📁 从JSON文件中提取了 {len(chinese_names)} 个中文名\n")
    
    # 更新记录
    updated_count = 0
    for bird in existing_birds:
        slug = bird['slug']
        if slug in chinese_names and not bird.get('chinese_name'):
            bird['chinese_name'] = chinese_names[slug]
            updated_count += 1
        elif slug in chinese_names:
            # 即使已有，也更新（确保准确性）
            bird['chinese_name'] = chinese_names[slug]
    
    # 写回CSV（新格式：包含chinese_name）
    with open(csv_file, 'w', encoding='utf-8') as f:
        # 写入新的表头
        f.write('# slug,chinese_name,english_name,scientific_name,wikipedia_page\n')
        
        # 写入数据
        for bird in existing_birds:
            chinese = bird.get('chinese_name', '')
            f.write(f'{bird["slug"]},"{chinese}","{bird["english_name"]}","{bird["scientific_name"]}",{bird["wikipedia_page"]}\n')
    
    print(f"✅ 已更新 {csv_file}")
    print(f"📝 更新了 {updated_count} 条记录的中文名")
    print(f"📊 总计 {len(existing_birds)} 条记录")

if __name__ == '__main__':
    print("🔧 开始为 all_birds.csv 添加中文名字段...\n")
    update_csv_with_chinese_names()
    print("\n✅ 完成！")

