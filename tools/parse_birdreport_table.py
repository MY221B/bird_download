#!/usr/bin/env python3
"""
解析中国观鸟记录中心的表格格式

支持旧版7列表格与当前8列表格（包含记录次数），以及制表符分隔的行。
当前列顺序：序号、鸟种编号、中文名、拉丁学名、英文名称、目、科、记录次数。
旧版示例：
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
    """按表头识别列；无表头时兼容新旧名称顺序，不限制鸟种数量。"""
    header_names = {
        '#': 'sequence', '序号': 'sequence',
        '鸟种编号': 'id', '编号': 'id',
        '中文名': 'chinese',
        '英文名称': 'english', '英文名': 'english',
        '拉丁学名': 'scientific', '学名': 'scientific',
        '目': 'order', '科': 'family', '记录次数': 'count',
    }
    cells = []
    for line in lines:
        text = line.strip('\r\n').lstrip('\ufeff')
        if '\t' in text:
            cells.extend(cell.strip() for cell in text.split('\t'))
        elif text.strip():
            cells.append(text.strip())

    def valid_names(chinese, scientific):
        return (
            re.search(r'[\u3400-\u9fff]', chinese)
            and re.fullmatch(r'[A-Z][a-z]+\s+[a-z]+(?:\s+[a-z]+)*', scientific)
        )

    birds = []
    columns = None
    width = 0
    i = 0
    while i < len(cells):
        if cells[i] in header_names:
            end = i
            headers = {}
            while end < len(cells) and cells[end] in header_names:
                headers[header_names[cells[end]]] = end - i
                end += 1
            if {'chinese', 'english', 'scientific', 'id'} <= headers.keys():
                columns, width = headers, end - i
            i = end
            continue

        if columns and i + width <= len(cells):
            row = cells[i:i + width]
            chinese = row[columns['chinese']]
            scientific = row[columns['scientific']]
            sequence = row[columns.get('sequence', columns['id'])]
            if sequence.isdigit() and row[columns['id']].isdigit() and valid_names(chinese, scientific):
                birds.append({
                    'chinese': chinese,
                    'english': row[columns['english']],
                    'scientific': scientific,
                })
                i += width
                continue

        # Some clipboard selections omit the header: identify a complete row
        # by its sequence, taxon ID and names, allowing either name order.
        if i + 6 < len(cells) and cells[i].isdigit() and cells[i + 1].isdigit():
            chinese = cells[i + 2]
            first, second = cells[i + 3:i + 5]
            for scientific, english in ((second, first), (first, second)):
                if valid_names(chinese, scientific):
                    birds.append({'chinese': chinese, 'english': english, 'scientific': scientific})
                    i += 6
                    break
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

