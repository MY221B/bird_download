#!/usr/bin/env python3
"""
查找鸟类的 eBird species code
用法: python3 tools/find_ebird_code.py "Bird English Name" [scientific_name]
"""

import sys
import os
import json
import subprocess
import urllib.parse

def find_ebird_code(search_term, is_scientific=False):
    """
    查找eBird species code
    
    Args:
        search_term: 搜索词（英文名或学名）
        is_scientific: 是否为学名
    """
    ebird_token = os.environ.get('EBIRD_TOKEN')
    
    if not ebird_token:
        print("❌ 错误: 未设置 EBIRD_TOKEN 环境变量")
        print("请先运行: source config/ebird_token.sh")
        return None
    
    print(f"🔍 搜索: {search_term}")
    print(f"   类型: {'学名' if is_scientific else '英文名'}")
    print()
    
    # 获取完整的taxonomy
    url = "https://api.ebird.org/v2/ref/taxonomy/ebird?fmt=json&locale=en"
    
    try:
        result = subprocess.run(
            ['curl', '-s', '-H', f'X-eBirdApiToken: {ebird_token}', url],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode != 0 or not result.stdout:
            print("❌ API 调用失败")
            return None
        
        data = json.loads(result.stdout)
        matches = []
        
        search_lower = search_term.lower()
        
        for item in data:
            com_name = item.get('comName', '')
            sci_name = item.get('sciName', '')
            code = item.get('speciesCode', '')
            
            if is_scientific:
                # 学名搜索
                if search_lower in sci_name.lower():
                    matches.append({
                        'code': code,
                        'common': com_name,
                        'scientific': sci_name,
                        'exact': sci_name.lower() == search_lower
                    })
            else:
                # 英文名搜索
                if search_lower in com_name.lower():
                    matches.append({
                        'code': code,
                        'common': com_name,
                        'scientific': sci_name,
                        'exact': com_name.lower() == search_lower
                    })
        
        if not matches:
            print("❌ 未找到匹配结果")
            print()
            print("💡 提示:")
            print("  1. 检查拼写是否正确")
            print("  2. 尝试使用学名搜索: python3 tools/find_ebird_code.py \"Scientific Name\" --scientific")
            print("  3. 访问 https://ebird.org 手动搜索")
            return None
        
        # 排序：精确匹配优先
        matches.sort(key=lambda x: (not x['exact'], x['common']))
        
        print(f"✅ 找到 {len(matches)} 个匹配结果:\n")
        
        for i, match in enumerate(matches, 1):
            marker = "🎯" if match['exact'] else "  "
            print(f"{marker} [{i}] {match['common']}")
            print(f"      学名: {match['scientific']}")
            print(f"      Code: {match['code']}")
            print(f"      eBird: https://ebird.org/species/{match['code']}")
            print()
        
        if matches[0]['exact']:
            print(f"💡 推荐使用: {matches[0]['code']}")
            print()
            print("📋 添加到映射文件:")
            print(f'   "{matches[0]["common"]}": "{matches[0]["code"]}"')
        
        return matches[0]['code'] if matches else None
        
    except Exception as e:
        print(f"❌ 错误: {e}")
        return None


def main():
    if len(sys.argv) < 2:
        print("用法:")
        print("  python3 tools/find_ebird_code.py \"Bird English Name\"")
        print("  python3 tools/find_ebird_code.py \"Scientific Name\" --scientific")
        print()
        print("示例:")
        print("  python3 tools/find_ebird_code.py \"Japanese Tit\"")
        print("  python3 tools/find_ebird_code.py \"Parus minor\" --scientific")
        sys.exit(1)
    
    search_term = sys.argv[1]
    is_scientific = '--scientific' in sys.argv or '-s' in sys.argv
    
    find_ebird_code(search_term, is_scientific)


if __name__ == '__main__':
    main()
