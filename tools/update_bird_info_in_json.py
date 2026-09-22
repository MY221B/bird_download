#!/usr/bin/env python3
"""
更新所有 cloudinary_uploads/*_cloudinary_urls.json 文件的 bird_info 字段
从 all_birds.csv 读取完整的鸟类信息
"""

import json
import csv
from pathlib import Path

def load_bird_info_from_csv():
    """从 all_birds.csv 加载所有鸟类信息"""
    bird_info_map = {}
    csv_file = Path('all_birds.csv')
    
    if not csv_file.exists():
        print(f"⚠️  all_birds.csv 不存在，跳过从CSV读取")
        return bird_info_map
    
    try:
        with open(csv_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            # 跳过注释行，找到实际数据行
            data_lines = [line for line in lines if line.strip() and not line.strip().startswith('#')]
            
            if data_lines:
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
                
                # 根据字段选择不同的fieldnames
                if has_chinese:
                    reader = csv.DictReader(data_lines, fieldnames=['slug', 'chinese_name', 'english_name', 'scientific_name', 'wikipedia_page'])
                else:
                    reader = csv.DictReader(data_lines, fieldnames=['slug', 'english_name', 'scientific_name', 'wikipedia_page'])
                
                for row in reader:
                    slug = row.get('slug', '').strip()
                    if slug:
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

def update_json_file(json_file, bird_info_map):
    """更新单个JSON文件的bird_info字段"""
    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # 获取slug（从文件名提取）
        slug = json_file.stem.replace('_cloudinary_urls', '')
        
        # 获取现有bird_info或创建新的
        if 'bird_info' not in data:
            data['bird_info'] = {}
        
        existing_info = data['bird_info']
        updated = False
        
        # 从CSV获取信息
        if slug in bird_info_map:
            csv_info = bird_info_map[slug]
            
            # 更新缺失的字段（保留现有值，只补充缺失的）
            if not existing_info.get('chinese_name') and csv_info.get('chinese_name'):
                existing_info['chinese_name'] = csv_info['chinese_name']
                updated = True
            
            if not existing_info.get('english_name') and csv_info.get('english_name'):
                existing_info['english_name'] = csv_info['english_name']
                updated = True
            
            if not existing_info.get('scientific_name') and csv_info.get('scientific_name'):
                existing_info['scientific_name'] = csv_info['scientific_name']
                updated = True
        
        # 确保slug字段存在
        if 'slug' not in existing_info:
            existing_info['slug'] = slug
            updated = True
        
        # 如果有更新，保存文件（必须保留 sounds 等非图片字段，禁止重建白名单丢数据）
        if updated:
            ordered_data = {}
            if 'bird_info' in data:
                ordered_data['bird_info'] = data['bird_info']

            for key in ['macaulay', 'inaturalist', 'birdphotos', 'wikimedia', 'avibase']:
                if key in data:
                    ordered_data[key] = data[key]

            for key, value in data.items():
                if key not in ordered_data:
                    ordered_data[key] = value

            with open(json_file, 'w', encoding='utf-8') as f:
                json.dump(ordered_data, f, indent=2, ensure_ascii=False)

            return True

        return False
        
    except Exception as e:
        print(f"❌ 处理 {json_file} 失败: {e}")
        return False

def main():
    """主函数"""
    print("🔧 开始更新所有JSON文件的bird_info字段...\n")
    
    # 加载CSV信息
    bird_info_map = load_bird_info_from_csv()
    print(f"📋 从 all_birds.csv 加载了 {len(bird_info_map)} 条鸟类信息\n")
    
    # 查找所有JSON文件
    upload_dir = Path('cloudinary_uploads')
    if not upload_dir.exists():
        print(f"❌ 目录不存在: {upload_dir}")
        return
    
    json_files = list(upload_dir.glob('*_cloudinary_urls.json'))
    print(f"📁 找到 {len(json_files)} 个JSON文件\n")
    
    updated_count = 0
    skipped_count = 0
    
    for json_file in sorted(json_files):
        slug = json_file.stem.replace('_cloudinary_urls', '')
        
        if update_json_file(json_file, bird_info_map):
            print(f"✅ {slug}")
            updated_count += 1
        else:
            # 检查是否缺少信息
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    info = data.get('bird_info', {})
                    if not info.get('english_name') or not info.get('scientific_name'):
                        if slug not in bird_info_map:
                            print(f"⚠️  {slug} - CSV中无此记录")
                        else:
                            print(f"ℹ️  {slug} - 已完整")
                    else:
                        skipped_count += 1
            except:
                skipped_count += 1
    
    print(f"\n{'='*60}")
    print(f"✅ 更新完成: {updated_count} 个文件已更新")
    print(f"ℹ️  跳过: {skipped_count} 个文件（无需更新）")
    print(f"{'='*60}\n")

if __name__ == '__main__':
    main()

