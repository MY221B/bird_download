#!/usr/bin/env python3
"""
从新增鸟单.txt（简单列表格式）解析鸟类信息，并复制对应的JSON文件到location_birds目录

使用方法:
    python3 tools/copy_birds_from_list.py 新增鸟单.txt 奥森北园 251114
"""

import sys
import csv
import shutil
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent

# 导入工具函数
import sys
sys.path.insert(0, str(PROJECT_ROOT / "tools"))
from location_utils import get_location_birds_path

def load_all_birds_csv():
    """从 all_birds.csv 加载所有鸟类信息，返回中文名到slug的映射"""
    csv_file = PROJECT_ROOT / 'all_birds.csv'
    slug_by_chinese = {}
    
    if not csv_file.exists():
        return slug_by_chinese
    
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
                        chinese = row.get('chinese_name', '').strip('"') if has_chinese else ''
                        if chinese:
                            slug_by_chinese[chinese] = slug
    except Exception as e:
        print(f"⚠️  读取 all_birds.csv 失败: {e}")
    
    return slug_by_chinese


def parse_bird_list(input_file):
    """解析简单的鸟类列表文件（每行一个中文名）"""
    birds = []
    with open(input_file, 'r', encoding='utf-8') as f:
        for line in f:
            chinese = line.strip()
            if chinese:  # 跳过空行
                birds.append(chinese)
    return birds


def main():
    if len(sys.argv) < 4:
        print("用法:")
        print("  python3 tools/copy_birds_from_list.py <新增鸟单.txt> <地点> <日期>")
        print("例如:")
        print("  python3 tools/copy_birds_from_list.py 新增鸟单.txt 奥森北园 251114")
        sys.exit(1)
    
    input_file = Path(sys.argv[1])
    location = sys.argv[2]
    date = sys.argv[3]
    
    if not input_file.exists():
        print(f"❌ 错误: 找不到文件 {input_file}")
        sys.exit(1)
    
    print(f"📋 解析新增鸟单: {input_file}")
    
    # 解析鸟类列表
    bird_names = parse_bird_list(input_file)
    print(f"✅ 找到 {len(bird_names)} 种鸟类\n")
    
    if not bird_names:
        print("❌ 未找到任何鸟类信息")
        sys.exit(1)
    
    # 加载slug映射
    print("📖 加载鸟类slug映射...")
    slug_by_chinese = load_all_birds_csv()
    print(f"✅ 加载了 {len(slug_by_chinese)} 个中文名映射\n")
    
    # 目标目录（使用新的文件夹结构：城市/地点/日期）
    target_dir = get_location_birds_path(location, date)
    target_dir.mkdir(parents=True, exist_ok=True)
    
    # 源目录
    source_dir = PROJECT_ROOT / "cloudinary_uploads"
    
    # 复制JSON文件
    copied_count = 0
    not_found_count = 0
    missing_json_count = 0
    
    print(f"📁 目标目录: {target_dir}\n")
    
    for chinese_name in bird_names:
        # 查找slug
        slug = slug_by_chinese.get(chinese_name)
        
        if not slug:
            print(f"⚠️  {chinese_name} - 未找到对应的slug")
            not_found_count += 1
            continue
        
        # 查找JSON文件
        json_file = source_dir / f"{slug}_cloudinary_urls.json"
        
        if not json_file.exists():
            print(f"⚠️  {chinese_name} ({slug}) - JSON文件不存在")
            missing_json_count += 1
            continue
        
        # 复制文件
        target_file = target_dir / f"{slug}_cloudinary_urls.json"
        shutil.copy2(json_file, target_file)
        print(f"✅ {chinese_name} ({slug})")
        copied_count += 1
    
    print(f"\n{'='*60}")
    print(f"✅ 成功复制: {copied_count} 个文件")
    if not_found_count > 0:
        print(f"⚠️  未找到slug: {not_found_count} 种鸟类")
    if missing_json_count > 0:
        print(f"⚠️  JSON文件缺失: {missing_json_count} 种鸟类")
    print(f"{'='*60}\n")
    
    if copied_count == 0:
        print("❌ 没有成功复制任何文件")
        sys.exit(1)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n已取消")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

