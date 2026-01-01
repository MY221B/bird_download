#!/usr/bin/env python3
"""
从新增鸟单.txt解析鸟类信息，并复制对应的JSON文件到location_birds目录

使用方法:
    python3 tools/copy_birds_to_location.py 新增鸟单.txt 奥森南园 251105
"""

import sys
import os
import csv
import shutil
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
os.chdir(PROJECT_ROOT)

# 导入解析函数
sys.path.insert(0, str(PROJECT_ROOT / "tools"))
from parse_birdreport_table import parse_birdreport_table
from location_utils import get_location_birds_path

def parse_birdreport_table_improved(lines):
    """
    改进的解析函数，能够正确解析所有鸟类记录
    """
    birds = []
    i = 0
    skip_until_first_bird = True
    
    # 找到表头
    while i < len(lines):
        line = lines[i].strip()
        if line == '科':
            skip_until_first_bird = False
            i += 1
            break
        i += 1
    
    if skip_until_first_bird:
        return birds
    
    # 解析鸟类记录
    while i < len(lines):
        line = lines[i].strip()
        
        # 跳过空行和明显的页面元素
        if not line or any(keyword in line for keyword in [
            'logo', '网站', '查询', '鸟种分布', '活动', '专栏', '文件', '图库',
            '用户', '登录', '注册', '帮助', '首页', '所在位置', '鸟种名称',
            '基础统计', '编号', '拼音', 'Copyright', '版权', '地址', 'ICP'
        ]):
            i += 1
            continue
        
        # 检查是否是记录开始标记（数字，通常是1、2、3等）
        if line.isdigit():
            # 尝试读取一个完整的记录（7行）
            if i + 6 < len(lines):
                # 格式：数字标记、编号、中文名、英文名、学名、目、科
                num_marker = line
                bird_id = lines[i+1].strip() if i+1 < len(lines) else ''
                chinese = lines[i+2].strip() if i+2 < len(lines) else ''
                english = lines[i+3].strip() if i+3 < len(lines) else ''
                scientific = lines[i+4].strip() if i+4 < len(lines) else ''
                order = lines[i+5].strip() if i+5 < len(lines) else ''
                family = lines[i+6].strip() if i+6 < len(lines) else ''
                
                # 验证记录格式
                if (chinese and re.search(r'[\u4e00-\u9fff䴙䴘]', chinese) and
                    english and re.match(r'^[A-Z]', english) and
                    scientific and re.match(r'^[A-Z][a-z]+ [a-z]+', scientific)):
                    birds.append({
                        'chinese': chinese,
                        'english': english,
                        'scientific': scientific
                    })
                    # 跳过这个记录（7行）
                    i += 7
                    continue
        
        i += 1
    
    return birds


def load_all_birds_csv():
    """从 all_birds.csv 加载所有鸟类信息，返回多个映射"""
    csv_file = PROJECT_ROOT / 'all_birds.csv'
    slug_by_chinese = {}
    slug_by_english = {}
    slug_by_scientific = {}
    
    if not csv_file.exists():
        return slug_by_chinese, slug_by_english, slug_by_scientific
    
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
                        english = row.get('english_name', '').strip('"')
                        scientific = row.get('scientific_name', '').strip('"')
                        
                        if chinese:
                            slug_by_chinese[chinese] = slug
                        if english:
                            slug_by_english[english] = slug
                        if scientific:
                            slug_by_scientific[scientific] = slug
    except Exception as e:
        print(f"⚠️  读取 all_birds.csv 失败: {e}")
    
    return slug_by_chinese, slug_by_english, slug_by_scientific


def find_slug_for_bird(bird, slug_by_chinese, slug_by_english, slug_by_scientific):
    """根据鸟类信息找到对应的slug"""
    chinese = bird.get('chinese', '')
    english = bird.get('english', '')
    scientific = bird.get('scientific', '')
    
    # 优先使用中文名匹配
    if chinese and chinese in slug_by_chinese:
        return slug_by_chinese[chinese]
    
    # 其次使用英文名匹配
    if english and english in slug_by_english:
        return slug_by_english[english]
    
    # 最后使用学名匹配
    if scientific and scientific in slug_by_scientific:
        return slug_by_scientific[scientific]
    
    return None


def main():
    if len(sys.argv) < 4:
        print("用法:")
        print("  python3 tools/copy_birds_to_location.py <新增鸟单.txt> <地点> <日期>")
        print("例如:")
        print("  python3 tools/copy_birds_to_location.py 新增鸟单.txt 奥森南园 251105")
        sys.exit(1)
    
    input_file = Path(sys.argv[1])
    location = sys.argv[2]
    date = sys.argv[3]
    
    if not input_file.exists():
        print(f"❌ 错误: 找不到文件 {input_file}")
        sys.exit(1)
    
    print(f"📋 解析新增鸟单: {input_file}")
    
    # 解析鸟类列表
    with open(input_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    # 使用改进的解析函数
    birds = parse_birdreport_table_improved(lines)
    print(f"✅ 找到 {len(birds)} 种鸟类\n")
    
    if not birds:
        print("❌ 未找到任何鸟类信息")
        sys.exit(1)
    
    # 加载slug映射
    print("📖 加载鸟类slug映射...")
    slug_by_chinese, slug_by_english, slug_by_scientific = load_all_birds_csv()
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
    
    for bird in birds:
        chinese = bird.get('chinese', '')
        english = bird.get('english', '')
        scientific = bird.get('scientific', '')
        
        # 查找slug
        slug = find_slug_for_bird(bird, slug_by_chinese, slug_by_english, slug_by_scientific)
        
        if not slug:
            print(f"⚠️  {chinese} ({english}) - 未找到对应的slug")
            not_found_count += 1
            continue
        
        # 查找JSON文件
        json_file = source_dir / f"{slug}_cloudinary_urls.json"
        
        if not json_file.exists():
            print(f"⚠️  {chinese} ({slug}) - JSON文件不存在")
            missing_json_count += 1
            continue
        
        # 复制文件
        target_file = target_dir / f"{slug}_cloudinary_urls.json"
        shutil.copy2(json_file, target_file)
        print(f"✅ {chinese} ({slug})")
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

