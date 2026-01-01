#!/usr/bin/env python3
"""
从 cloudinary_uploads/*_cloudinary_urls.json 文件重建 all_birds.csv
包含所有字段：slug, chinese_name, english_name, scientific_name, wikipedia_page
"""

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

def rebuild_csv():
    """重建CSV文件"""
    bird_info_list = extract_all_bird_info()
    
    if not bird_info_list:
        print("❌ 没有找到任何鸟类信息")
        return
    
    csv_file = Path('all_birds.csv')
    
    # 按slug排序
    bird_info_list.sort(key=lambda x: x['slug'])
    
    # 写入CSV
    with open(csv_file, 'w', encoding='utf-8') as f:
        # 写入表头
        f.write('# slug,chinese_name,english_name,scientific_name,wikipedia_page\n')
        
        # 写入数据
        for bird in bird_info_list:
            chinese = bird.get('chinese_name', '')
            f.write(f'{bird["slug"]},"{chinese}","{bird["english_name"]}","{bird["scientific_name"]}",{bird["wikipedia_page"]}\n')
    
    print(f"✅ 已重建 {csv_file}")
    print(f"📊 共 {len(bird_info_list)} 条记录")

if __name__ == '__main__':
    print("🔧 开始从JSON文件重建 all_birds.csv...\n")
    rebuild_csv()
    print("\n✅ 完成！")

