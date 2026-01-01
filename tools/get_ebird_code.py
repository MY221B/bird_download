#!/usr/bin/env python3
"""
从 eBird Taxonomy API 获取 species code。
优先使用 species 参数精确查询；失败则全量匹配 sciName/comName。

用法:
  EBIRD_TOKEN=xxxx python3 tools/get_ebird_code.py "Marsh Tit" "Poecile palustris"
输出:
  martit2
"""
import os
import sys
import json
import urllib.parse
import urllib.request

API = "https://api.ebird.org/v2/ref/taxonomy/ebird?fmt=json&locale=en"

def fetch(url: str, token: str):
    req = urllib.request.Request(url, headers={
        'X-eBirdApiToken': token,
        'User-Agent': 'Mozilla/5.0'
    })
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode('utf-8'))

def main():
    token = os.environ.get('EBIRD_TOKEN', '').strip()
    if not token:
        print('', end='')
        return
    com = (sys.argv[1] if len(sys.argv) > 1 else '').strip()
    sci = (sys.argv[2] if len(sys.argv) > 2 else '').strip()

    # 1) 精确 species 查询（优先用学名，否则用英文名）
    q = urllib.parse.quote(sci or com)
    try:
        data = fetch(f"{API}&species={q}", token)
        if isinstance(data, list) and data:
            code = data[0].get('speciesCode')
            if code:
                print(code)
                return
    except Exception:
        pass

    # 2) 全量匹配（精确->包含，先 sciName 再 comName）
    try:
        data = fetch(API, token)
        target = (sci or com).lower()
        # 精确学名/英文名
        for r in data:
            if r.get('sciName','').lower() == target or r.get('comName','').lower() == target:
                if r.get('speciesCode'):
                    print(r['speciesCode'])
                    return
        # 包含匹配（容错变体）
        for r in data:
            if target in r.get('sciName','').lower() or target in r.get('comName','').lower():
                if r.get('speciesCode'):
                    print(r['speciesCode'])
                    return
    except Exception:
        pass

    print('', end='')

if __name__ == '__main__':
    main()


