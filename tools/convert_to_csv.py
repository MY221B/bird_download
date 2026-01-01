#!/usr/bin/env python3
"""
将用户提供的鸟类列表快速转换成 CSV 格式

支持的输入格式：
1. 带编号格式：39 4770 - 大山雀 Parus minor × 6
2. 简单中文名：大山雀
3. 带学名格式：大山雀 Parus minor
4. 带英文名：大山雀 Great Tit Parus minor

输出：标准 CSV 格式（slug,english_name,scientific_name,wikipedia_page）
"""

import re
import sys
import unicodedata
import os
import json
import urllib.request
import urllib.parse

def remove_accents(text):
    """移除重音符号，用于生成 slug"""
    nfd = unicodedata.normalize('NFD', text)
    return ''.join(char for char in nfd if unicodedata.category(char) != 'Mn')

def generate_slug(name):
    """
    从英文名或学名生成 slug
    例如：Red-flanked Bluetail → red_flanked_bluetail
    """
    name = remove_accents(name)
    name = name.lower()
    name = re.sub(r'[^\w\s-]', '', name)  # 移除特殊字符
    name = re.sub(r'[-\s]+', '_', name)   # 空格和连字符转为下划线
    return name

def generate_wikipedia_page(english_name):
    """
    从英文名生成 Wikipedia 页面名
    例如：Red-flanked Bluetail → Red-flanked_Bluetail
    """
    return english_name.replace(' ', '_')

def query_ebird_for_english_name(scientific_name, use_cache=True):
    """
    通过学名查询 eBird API 获取英文名
    
    返回: (english_name, ebird_scientific_name) 或 (None, None)
    """
    ebird_token = os.environ.get('EBIRD_TOKEN', '')
    if not ebird_token:
        print("  ⚠️  未设置 EBIRD_TOKEN 环境变量，无法自动查询英文名", file=sys.stderr)
        return None, None
    
    # 使用缓存
    cache_dir = os.path.expanduser('~/.cache/bird_memory_cards')
    os.makedirs(cache_dir, exist_ok=True)
    
    from datetime import datetime
    cache_file = os.path.join(cache_dir, f'ebird_taxonomy_{datetime.now().strftime("%Y%m")}.json')
    
    taxonomy = None
    if use_cache and os.path.exists(cache_file):
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                taxonomy = json.load(f)
                print(f"  📖 使用缓存的 eBird taxonomy", file=sys.stderr)
        except:
            pass
    
    if not taxonomy:
        print(f"  📡 下载 eBird taxonomy（首次或月度更新）...", file=sys.stderr)
        try:
            url = 'https://api.ebird.org/v2/ref/taxonomy/ebird?fmt=json'
            req = urllib.request.Request(url, headers={'X-eBirdApiToken': ebird_token})
            with urllib.request.urlopen(req, timeout=30) as response:
                taxonomy = json.loads(response.read().decode('utf-8'))
            
            # 保存到缓存
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(taxonomy, f, ensure_ascii=False, indent=2)
                print(f"  ✅ 已缓存到: {cache_file}", file=sys.stderr)
        except Exception as e:
            print(f"  ❌ 下载 eBird taxonomy 失败: {e}", file=sys.stderr)
            return None, None
    
    # 先尝试完全匹配学名
    sci_lower = scientific_name.strip().lower()
    for item in taxonomy:
        if item.get('sciName', '').strip().lower() == sci_lower:
            return item.get('comName'), item.get('sciName')
    
    print(f"  ⚠️  在 eBird 中未找到学名: {scientific_name}", file=sys.stderr)
    return None, None

def parse_bird_line(line):
    """
    解析一行鸟类信息
    
    支持格式：
    - "39 4770 - 大山雀 Parus minor × 6"
    - "大山雀 Great Tit Parus minor"
    - "大山雀 Parus minor"
    - "大山雀"
    
    返回：(chinese_name, english_name, scientific_name)
    """
    line = line.strip()
    if not line or line.startswith('#'):
        return None
    
    # 移除可能的编号前缀（如 "39 4770 -"）
    line = re.sub(r'^\d+\s+\d+\s*-\s*', '', line)
    
    # 移除可能的数量后缀（如 "× 6"）
    line = re.sub(r'\s*[×xX]\s*\d+\s*$', '', line)
    
    line = line.strip()
    
    # 尝试匹配不同格式
    # 格式1：大山雀 Great Tit Parus minor（中文名 + 英文名 + 学名）
    # 注意：英文名可能包含撇号（如 Pallas's）和连字符
    # 中文名支持扩展Unicode范围，包括䴙䴘䴓等特殊字符
    match = re.match(r'^([\u4e00-\u9fff\u4d00-\u4dff]+)\s+([A-Z][a-zA-Z\s\'\-]+?)\s+([A-Z][a-z]+\s+[a-z]+(?:\s+[a-z]+)*)$', line)
    if match:
        chinese, english, scientific = match.groups()
        return (chinese.strip(), english.strip(), scientific.strip())
    
    # 格式2：大山雀 Parus minor（中文名 + 学名）
    # 学名通常是两个单词，首字母大写
    # 中文名支持扩展Unicode范围，包括䴙䴘䴓等特殊字符
    match = re.match(r'^([\u4e00-\u9fff\u4d00-\u4dff]+)\s+([A-Z][a-z]+\s+[a-z]+(?:\s+[a-z]+)*)$', line)
    if match:
        chinese, scientific = match.groups()
        return (chinese.strip(), None, scientific.strip())
    
    # 格式3：只有中文名
    # 中文名支持扩展Unicode范围，包括䴙䴘䴓等特殊字符
    match = re.match(r'^([\u4e00-\u9fff\u4d00-\u4dff]+)$', line)
    if match:
        chinese = match.group(1)
        return (chinese.strip(), None, None)
    
    # 无法解析
    print(f"  ⚠️  无法解析: {line}", file=sys.stderr)
    return None

def prompt_missing_info(chinese_name, english_name, scientific_name):
    """交互式提示用户输入缺失的信息"""
    print(f"\n处理: {chinese_name}")
    
    if not english_name:
        english_name = input(f"  请输入英文名（如 Great Tit）: ").strip()
    
    if not scientific_name:
        scientific_name = input(f"  请输入学名（如 Parus minor）: ").strip()
    
    return english_name, scientific_name

def main():
    if len(sys.argv) < 2:
        print("用法 1（交互模式）：")
        print("  python3 tools/convert_to_csv.py")
        print("  然后粘贴鸟类列表，按 Ctrl+D（Mac/Linux）或 Ctrl+Z（Windows）结束输入")
        print()
        print("用法 2（文件模式）：")
        print("  python3 tools/convert_to_csv.py input.txt > output.csv")
        print()
        print("用法 3（自动模式，跳过缺失字段）：")
        print("  python3 tools/convert_to_csv.py --auto input.txt > output.csv")
        print()
        print("支持的输入格式：")
        print("  - 39 4770 - 大山雀 Parus minor × 6")
        print("  - 大山雀 Great Tit Parus minor")
        print("  - 大山雀 Parus minor")
        print("  - 大山雀")
        print()
        sys.exit(1)
    
    # 检查是否为自动模式
    auto_mode = False
    input_source = sys.stdin
    
    if sys.argv[1] == '--auto':
        auto_mode = True
        if len(sys.argv) > 2 and sys.argv[2] != '-':
            input_source = open(sys.argv[2], 'r', encoding='utf-8')
    elif sys.argv[1] != '-':
        input_source = open(sys.argv[1], 'r', encoding='utf-8')
    
    # 输出 CSV 头部
    print("# slug,english_name,scientific_name,wikipedia_page")
    
    birds = []
    lines = input_source.readlines()
    
    for line in lines:
        result = parse_bird_line(line)
        if not result:
            continue
        
        chinese_name, english_name, scientific_name = result
        
        # 尝试通过 eBird API 补全缺失信息
        if auto_mode:
            # 如果有学名但没有英文名，尝试查询
            if scientific_name and not english_name:
                print(f"  🔍 查询: {chinese_name} ({scientific_name})", file=sys.stderr)
                queried_english, queried_sci = query_ebird_for_english_name(scientific_name)
                if queried_english:
                    english_name = queried_english
                    # 如果 eBird 的学名不同，使用 eBird 的学名
                    if queried_sci and queried_sci != scientific_name:
                        print(f"  📝 学名更新: {scientific_name} → {queried_sci}", file=sys.stderr)
                        scientific_name = queried_sci
                    print(f"  ✅ 找到英文名: {english_name}", file=sys.stderr)
            
            # 如果仍然信息不完整，跳过
            if not english_name or not scientific_name:
                print(f"⚠️  跳过 '{chinese_name}'（信息不完整）", file=sys.stderr)
                continue
        else:
            # 交互模式：提示用户输入缺失信息
            if not english_name or not scientific_name:
                english_name, scientific_name = prompt_missing_info(
                    chinese_name, english_name, scientific_name
                )
        
        if not english_name or not scientific_name:
            continue
        
        # 生成 slug 和 Wikipedia 页面名
        slug = generate_slug(english_name)
        wikipedia_page = generate_wikipedia_page(english_name)
        
        birds.append((slug, english_name, scientific_name, wikipedia_page))
    
    # 输出所有鸟类
    for slug, english_name, scientific_name, wikipedia_page in birds:
        print(f'{slug},"{english_name}","{scientific_name}",{wikipedia_page}')
    
    if input_source != sys.stdin:
        input_source.close()
    
    # 输出统计信息到 stderr
    print(f"\n✅ 成功转换 {len(birds)} 种鸟类", file=sys.stderr)

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n已取消", file=sys.stderr)
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ 错误: {e}", file=sys.stderr)
        sys.exit(1)

