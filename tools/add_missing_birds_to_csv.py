#!/usr/bin/env python3
"""
从 cloudinary_uploads/*_cloudinary_urls.json 文件中提取鸟类信息
并添加到 all_birds.csv（如果CSV中不存在）
"""

import json
import csv
import sys
from pathlib import Path

def load_existing_csv():
    """加载现有的CSV文件，返回已有记录的集合"""
    # 确保使用绝对路径，避免工作目录问题
    csv_file = Path('all_birds.csv').resolve()
    existing_slugs = set()
    
    if csv_file.exists():
        try:
            with open(csv_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                # 找到表头行（可能在注释行中）
                header_line = None
                for i, line in enumerate(lines):
                    if line.strip() and 'slug' in line.lower():
                        header_line = i
                        break
                
                if header_line is not None:
                    # 检查字段名
                    header = lines[header_line].strip().lstrip('#').strip()
                    if 'chinese_name' in header.lower():
                        fieldnames = ['slug', 'chinese_name', 'english_name', 'scientific_name', 'wikipedia_page']
                    else:
                        fieldnames = ['slug', 'english_name', 'scientific_name', 'wikipedia_page']
                    
                    # 读取数据行（跳过表头行）
                    data_lines = [line for line in lines[header_line+1:] if line.strip() and not line.strip().startswith('#')]
                    if data_lines:
                        reader = csv.DictReader(data_lines, fieldnames=fieldnames)
                        for row in reader:
                            slug = row.get('slug', '').strip().strip('"')
                            if slug and slug != 'slug':  # 跳过表头
                                existing_slugs.add(slug)
        except Exception as e:
            print(f"⚠️  读取现有CSV失败: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc()
    else:
        print(f"⚠️  CSV文件不存在: {csv_file}", file=sys.stderr)
    
    return existing_slugs

def extract_bird_info_from_json():
    """从所有JSON文件中提取鸟类信息"""
    # 确保使用绝对路径，避免工作目录问题
    upload_dir = Path('cloudinary_uploads').resolve()
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
                    # 生成wikipedia_page名称（英文名替换空格为下划线）
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

def add_to_csv(new_birds):
    """将新鸟类添加到CSV文件"""
    if not new_birds:
        print("ℹ️  没有需要添加的新鸟类")
        return 0
    
    # 确保使用绝对路径，避免工作目录问题
    csv_file = Path('all_birds.csv').resolve()
    
    # 读取现有内容
    existing_lines = []
    if csv_file.exists():
        with open(csv_file, 'r', encoding='utf-8') as f:
            existing_lines = f.readlines()
    
    # 添加新记录
    added_count = 0
    for bird in new_birds:
        # 检查是否已存在
        slug = bird['slug']
        exists = False
        for line in existing_lines:
            if line.strip() and not line.strip().startswith('#') and line.strip().startswith(slug + ','):
                exists = True
                break
        
        if not exists:
            # 格式：slug,"chinese_name","english_name","scientific_name",wikipedia_page
            chinese = bird.get('chinese_name', '')
            english = bird.get('english_name', '')
            name_display = f"{english}（{chinese}）" if chinese else english
            new_line = f'{bird["slug"]},"{chinese}","{bird["english_name"]}","{bird["scientific_name"]}",{bird["wikipedia_page"]}\n'
            existing_lines.append(new_line)
            added_count += 1
            print(f"✅ 添加: {bird['slug']} - {name_display}")
    
    # 写回文件
    if added_count > 0:
        with open(csv_file, 'w', encoding='utf-8') as f:
            # 保留注释行（如果有）
            header_written = False
            for line in existing_lines:
                if line.strip().startswith('#') and not header_written:
                    f.write(line)
                    header_written = True
                elif not line.strip().startswith('#'):
                    f.write(line)
            
            # 如果没有注释行，添加一个
            if not header_written:
                f.write('# slug,chinese_name,english_name,scientific_name,wikipedia_page\n')
                for line in existing_lines:
                    if not line.strip().startswith('#'):
                        f.write(line)
        
        print(f"\n📝 已更新 {csv_file}")
    
    return added_count

def main():
    """主函数"""
    print("🔧 开始从JSON文件提取鸟类信息并添加到 all_birds.csv...\n")
    
    # 加载现有CSV记录
    existing_slugs = load_existing_csv()
    print(f"📋 现有CSV中有 {len(existing_slugs)} 条记录\n")
    
    # 从JSON文件提取信息
    all_bird_info = extract_bird_info_from_json()
    print(f"📁 从JSON文件中提取了 {len(all_bird_info)} 条完整的鸟类信息\n")
    
    # 过滤出CSV中不存在的记录
    new_birds = [bird for bird in all_bird_info if bird['slug'] not in existing_slugs]
    
    if not new_birds:
        print(f"✅ 所有鸟类信息已存在于CSV中（JSON文件中共有 {len(all_bird_info)} 个鸟类，CSV中已有 {len(existing_slugs)} 个）")
        return
    
    print(f"📝 需要添加的新鸟类: {len(new_birds)} 个")
    print(f"   - JSON文件中共有: {len(all_bird_info)} 个鸟类")
    print(f"   - CSV中已有: {len(existing_slugs)} 个鸟类")
    print(f"   - 需要新增: {len(new_birds)} 个鸟类\n")
    for bird in new_birds:
        chinese = bird.get('chinese_name', '')
        english = bird.get('english_name', '')
        name_display = f"{english}（{chinese}）" if chinese else english
        print(f"  - {bird['slug']}: {name_display} ({bird['scientific_name']})")
    
    print()
    
    # 添加到CSV
    added_count = add_to_csv(new_birds)
    
    print(f"\n{'='*60}")
    print(f"✅ 完成: 添加了 {added_count} 条新记录到 all_birds.csv")
    print(f"{'='*60}\n")

if __name__ == '__main__':
    main()

