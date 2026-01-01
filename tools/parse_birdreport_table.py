#!/usr/bin/env python3
"""
解析中国观鸟记录中心的表格格式

特殊格式（每个鸟类占7行）：
1
4148
珠颈斑鸠
Spotted Dove
Spilopelia chinensis
鸽形目
鸠鸽科

输出：中文名 学名
"""

import sys
import re

def parse_birdreport_table(lines):
    """
    解析观鸟记录中心的表格格式
    
    格式说明（每个鸟类占7行）：
    1       - 序号（1-56）
    4148    - 鸟种编号
    珠颈斑鸠 - 中文名
    Spotted Dove - 英文名
    Spilopelia chinensis - 学名
    鸽形目  - 目
    鸠鸽科  - 科
    """
    birds = []
    skip_until_first_bird = True
    i = 0
    
    while i < len(lines):
        line = lines[i].strip()
        
        # 跳过空行
        if not line:
            i += 1
            continue
        
        # 跳过明显的页面元素
        if any(keyword in line for keyword in [
            'logo', '网站', '查询', '鸟种分布', '活动', '专栏', '文件', '图库',
            '用户', '登录', '注册', '帮助', '首页', '所在位置', '鸟种名称',
            '基础统计', '编号', '拼音', 'Copyright', '版权', '地址', 'ICP'
        ]):
            i += 1
            continue
        
        # 跳过表头
        if line in ['#', '中文名', '英文名称', '拉丁学名', '目', '科']:
            skip_until_first_bird = False
            i += 1
            continue
        
        if skip_until_first_bird:
            i += 1
            continue
        
        # 检查是否是序号行（1-56的纯数字）
        if re.match(r'^\d+$', line):
            seq_num = int(line)
            if 1 <= seq_num <= 56 and i + 6 < len(lines):
                # 读取接下来的6行
                bird_id = lines[i + 1].strip() if i + 1 < len(lines) else ''
                chinese = lines[i + 2].strip() if i + 2 < len(lines) else ''
                english = lines[i + 3].strip() if i + 3 < len(lines) else ''
                scientific = lines[i + 4].strip() if i + 4 < len(lines) else ''
                order = lines[i + 5].strip() if i + 5 < len(lines) else ''
                family = lines[i + 6].strip() if i + 6 < len(lines) else ''
                
                # 验证学名格式（支持多词学名）
                if re.match(r'^[A-Z][a-z]+ [a-z]+(?:\s+[a-z]+)*', scientific):
                    # 验证中文名（支持特殊字符如䴙䴘）
                    if re.search(r'[\u4e00-\u9fff䴙䴘]', chinese):
                        birds.append({
                            'chinese': chinese,
                            'english': english,
                            'scientific': scientific
                        })
                        i += 7  # 跳过这7行
                        continue
        
        i += 1
    
    return birds

def main():
    # 确定输入源
    if len(sys.argv) > 1:
        if sys.argv[1] == '-':
            input_source = sys.stdin
            source_name = "标准输入"
        else:
            try:
                input_source = open(sys.argv[1], 'r', encoding='utf-8')
                source_name = sys.argv[1]
            except Exception as e:
                print(f"❌ 无法打开文件: {e}", file=sys.stderr)
                sys.exit(1)
    else:
        print("用法：", file=sys.stderr)
        print("  python3 tools/parse_birdreport_table.py <file>", file=sys.stderr)
        print("  python3 tools/parse_birdreport_table.py 观鸟中心页面复制.txt", file=sys.stderr)
        sys.exit(1)
    
    print(f"📋 从 {source_name} 读取鸟类列表...", file=sys.stderr)
    print("", file=sys.stderr)
    
    lines = input_source.readlines()
    
    if input_source != sys.stdin:
        input_source.close()
    
    birds = parse_birdreport_table(lines)
    
    print(f"✅ 找到 {len(birds)} 种鸟类", file=sys.stderr)
    print("", file=sys.stderr)
    
    if not birds:
        print("❌ 未找到任何鸟类信息", file=sys.stderr)
        sys.exit(1)
    
    # 去重
    unique_birds = []
    seen = set()
    for bird in birds:
        key = (bird['chinese'], bird['scientific'])
        if key not in seen:
            seen.add(key)
            unique_birds.append(bird)
    
    if len(unique_birds) < len(birds):
        print(f"📊 去重后: {len(unique_birds)} 种鸟类", file=sys.stderr)
        print("", file=sys.stderr)
    
    # 输出
    print("# 从中国观鸟记录中心提取的鸟类名单", file=sys.stderr)
    print("# 可直接用 convert_to_csv.py --auto - 转换", file=sys.stderr)
    print("", file=sys.stderr)
    
    for bird in unique_birds:
        # 输出格式：中文名 英文名 学名（完整格式）
        print(f"{bird['chinese']} {bird['english']} {bird['scientific']}")
    
    print("", file=sys.stderr)
    print("✅ 完成！", file=sys.stderr)
    print("", file=sys.stderr)
    print("下一步：", file=sys.stderr)
    print("  python3 tools/convert_to_csv.py --auto - < output.txt > my_birds.csv", file=sys.stderr)

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n已取消", file=sys.stderr)
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ 错误: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)

