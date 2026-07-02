#!/usr/bin/env python3
"""
智能 eBird 物种查找工具

核心思路：
1. 从 slug 提取关键词进行模糊搜索
2. 缓存完整的 eBird taxonomy 到本地
3. 使用多种匹配策略：精确 -> 包含 -> 模糊
"""

import json
import os
import re
import sys
import subprocess
import urllib.parse
from pathlib import Path
from typing import Optional, List, Dict, Tuple
from datetime import datetime, timedelta

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
CACHE_FILE = PROJECT_ROOT / "config" / "ebird_taxonomy_cache.json"
CACHE_EXPIRY_DAYS = 7  # 缓存7天


def load_or_fetch_taxonomy() -> List[Dict]:
    """
    加载或获取 eBird taxonomy
    使用本地缓存减少 API 调用

    过期后优先尝试在线刷新；若无 EBIRD_TOKEN 或网络失败，仍返回过期缓存（stale-while-revalidate），
    避免 7 天一过智能匹配全部失效。
    """
    stale_data: List[Dict] = []
    if CACHE_FILE.exists():
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                cache = json.load(f)
            stale_data = cache.get('data') or []
            cached_time = datetime.fromisoformat(cache.get('timestamp', '2000-01-01'))
            if stale_data and datetime.now() - cached_time < timedelta(days=CACHE_EXPIRY_DAYS):
                return stale_data
        except Exception:
            stale_data = []

    # 获取新数据
    print("📥 正在获取 eBird taxonomy 数据...", file=sys.stderr)
    ebird_token = os.environ.get('EBIRD_TOKEN')

    if not ebird_token:
        print("❌ 未设置 EBIRD_TOKEN", file=sys.stderr)
        if stale_data:
            print(f"⚠️ 使用过期本地 taxonomy（{len(stale_data)} 条），智能匹配仍可用", file=sys.stderr)
            return stale_data
        return []

    try:
        url = "https://api.ebird.org/v2/ref/taxonomy/ebird?fmt=json&locale=en"
        result = subprocess.run(
            ['curl', '-s', '-H', f'X-eBirdApiToken: {ebird_token}', url],
            capture_output=True,
            text=True,
            timeout=60
        )

        if result.returncode == 0 and result.stdout:
            data = json.loads(result.stdout)

            # 保存缓存
            cache = {
                'timestamp': datetime.now().isoformat(),
                'data': data
            }
            CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(CACHE_FILE, 'w', encoding='utf-8') as f:
                json.dump(cache, f, ensure_ascii=False)

            print(f"✅ 已缓存 {len(data)} 个物种到 {CACHE_FILE}", file=sys.stderr)
            return data
    except Exception as e:
        print(f"❌ 获取 taxonomy 失败: {e}", file=sys.stderr)

    if stale_data:
        print(f"⚠️ 刷新失败，继续使用过期本地 taxonomy（{len(stale_data)} 条）", file=sys.stderr)
        return stale_data
    return []


def load_manual_mapping() -> Dict[str, str]:
    """加载手动映射配置"""
    mapping_file = PROJECT_ROOT / "config" / "ebird_manual_mapping.json"
    
    if mapping_file.exists():
        try:
            with open(mapping_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get('mappings', {})
        except:
            pass
    
    return {}


# 已知的 slug 到 eBird code 的直接映射
# 用于处理名称差异较大的物种
SLUG_TO_CODE_MAPPING = {
    # 名称差异较大的物种
    'japanese_tit': 'gretit1',  # Japanese Tit -> Great Tit (eBird 将其归入大山雀)
    'grey_capped_woodpecker': 'gycwoo1',  # -> Gray-capped Pygmy Woodpecker
    'vinous_throated_parrotbill': 'vitpar1',  # 棕头鸦雀
    'eurasian_hoopoe': 'hoopoe',  # 戴胜 -> Common Hoopoe
    'yellow_bellied_tit': 'yebtit4',  # 黄腹山雀 -> Yellow-bellied Tit
    'chinese_thrush': 'chithr2',  # 斑鸫
    'japanese_spotted_woodpecker': 'pygwoo1',  # 小星头啄木鸟 -> Japanese Pygmy Woodpecker
    'great_tit': 'gretit1',  # 大山雀
    'bluetail': 'refblu1',  # 红胁蓝尾鸲 -> Red-flanked Bluetail
    'eastern_buzzard': 'combuz6',  # 普通鵟 -> Eastern Buzzard
    
    # 常见水鸟
    'smew': 'smew',  # 斑头秋沙鸭
    'gadwall': 'gadwal',  # 赤膀鸭
    'northern_shoveler': 'norsho',  # 琵嘴鸭
    'eurasian_wigeon': 'eurwig',  # 赤颈鸭
    'eurasian_coot': 'eurcoo',  # 白骨顶
    
    # 涉禽和猛禽
    'gray_heron': 'graher1',  # 苍鹭
    'grey_heron': 'graher1',  # 苍鹭（grey 拼写）
    'little_egret': 'litegr',  # 小白鹭
    'black_kite': 'blakit1',  # 黑鸢
    'upland_buzzard': 'uplbuz1',  # 大鵟
    
    # 雀形目
    'dusky_warbler': 'duswar',  # 褐柳莺（注意：不是 duswar1）

    # 多种 Grasshopper Warbler 词重叠很高，必须固定到对应 eBird code，避免模糊匹配串种
    'middendorffs_grasshopper_warbler': 'migwar',
    'pallass_grasshopper_warbler': 'pagwar1',

    # eBird 仍作 Godlewski's Bunting；IOC「西南灰眉岩鹀」学名 Emberiza yunnanensis 无独立种
    'southern_rock_bunting': 'godbun1',
    # 学名已从 Charadrius 移至 Anarhynchus；英文名匹配即可，此处兜底
    'white_faced_plover': 'whfplo2',
}


def slug_to_keywords(slug: str) -> List[str]:
    """
    从 slug 提取搜索关键词
    例如: eurasian_hoopoe -> ['hoopoe', 'eurasian hoopoe']
    """
    # 转换为空格分隔的词
    words = slug.replace('_', ' ').split()
    
    keywords = []
    
    # 完整名称
    full_name = ' '.join(words)
    keywords.append(full_name)
    
    # 最后一个词（通常是物种名）
    if words:
        keywords.append(words[-1])
    
    # 去掉常见前缀后的名称
    prefixes_to_remove = ['eurasian', 'asian', 'common', 'chinese', 'japanese', 'oriental', 'northern', 'southern', 'eastern', 'western', 'greater', 'lesser']
    filtered_words = [w for w in words if w.lower() not in prefixes_to_remove]
    if filtered_words and filtered_words != words:
        keywords.append(' '.join(filtered_words))
    
    # 添加变体拼写 (grey/gray)
    for kw in keywords.copy():
        if 'grey' in kw.lower():
            keywords.append(kw.lower().replace('grey', 'gray'))
        if 'gray' in kw.lower():
            keywords.append(kw.lower().replace('gray', 'grey'))
    
    return keywords


def search_taxonomy(
    taxonomy: List[Dict],
    slug: str,
    chinese_name: str = "",
    english_name: str = "",
    scientific_name: str = ""
) -> Optional[Dict]:
    """
    在 taxonomy 中智能搜索物种
    
    返回最匹配的物种信息: {'code': ..., 'comName': ..., 'sciName': ...}
    """
    # 1. 首先检查直接映射（优先级最高）
    if slug in SLUG_TO_CODE_MAPPING:
        code = SLUG_TO_CODE_MAPPING[slug]
        # 从 taxonomy 中找到对应的完整信息
        for item in taxonomy:
            if item.get('speciesCode') == code:
                return {
                    'code': code,
                    'comName': item.get('comName', ''),
                    'sciName': item.get('sciName', ''),
                    'score': 1000  # 最高优先级
                }
    
    # 2. 检查手动映射文件
    manual_mapping = load_manual_mapping()
    if english_name and english_name in manual_mapping:
        code = manual_mapping[english_name]
        for item in taxonomy:
            if item.get('speciesCode') == code:
                return {
                    'code': code,
                    'comName': item.get('comName', ''),
                    'sciName': item.get('sciName', ''),
                    'score': 900
                }
    
    # 3. 生成搜索关键词
    search_terms = []
    
    # 从已知信息生成搜索词
    if english_name:
        search_terms.append(english_name.lower())
    
    if scientific_name:
        search_terms.append(scientific_name.lower())
    
    # 从 slug 生成关键词
    slug_keywords = slug_to_keywords(slug)
    search_terms.extend([k.lower() for k in slug_keywords])
    
    # 去重
    search_terms = list(dict.fromkeys(search_terms))
    
    matches = []
    
    for item in taxonomy:
        com_name = item.get('comName', '').lower()
        sci_name = item.get('sciName', '').lower()
        code = item.get('speciesCode', '')
        
        # 跳过非物种级别的条目（杂交种、未确定等）
        if code.startswith('y0') or 'hybrid' in com_name or ' sp.' in com_name:
            continue
        
        score = 0
        
        for term in search_terms:
            # 精确匹配 - 高分
            if term == com_name or term == sci_name:
                score += 100
            # 包含匹配 - 中分
            elif term in com_name or term in sci_name:
                score += 50
            # 部分词匹配 - 低分
            else:
                term_words = set(term.split())
                name_words = set(com_name.split())
                common_words = term_words & name_words
                if common_words:
                    score += len(common_words) * 20
        
        if score > 0:
            matches.append({
                'code': code,
                'comName': item.get('comName', ''),
                'sciName': item.get('sciName', ''),
                'score': score
            })
    
    if not matches:
        return None
    
    # 按分数排序，取最高分
    matches.sort(key=lambda x: -x['score'])
    
    # 如果有多个匹配，优先选择不带括号的（主物种而非亚种）
    top_matches = [m for m in matches if m['score'] == matches[0]['score']]
    for m in top_matches:
        if '(' not in m['comName']:
            return m
    
    return matches[0]


def smart_get_ebird_code(
    slug: str,
    chinese_name: str = "",
    english_name: str = "",
    scientific_name: str = ""
) -> Optional[str]:
    """
    智能获取 eBird species code
    即使数据不完整也能工作
    """
    taxonomy = load_or_fetch_taxonomy()
    
    if not taxonomy:
        return None
    
    result = search_taxonomy(
        taxonomy,
        slug,
        chinese_name=chinese_name,
        english_name=english_name,
        scientific_name=scientific_name
    )
    
    if result:
        return result['code']
    
    return None


def batch_lookup(birds: List[Dict]) -> Dict[str, Dict]:
    """
    批量查找鸟类的 eBird 信息
    
    Args:
        birds: [{'slug': ..., 'chinese_name': ..., 'english_name': ..., 'scientific_name': ...}, ...]
    
    Returns:
        {slug: {'code': ..., 'comName': ..., 'sciName': ...}, ...}
    """
    taxonomy = load_or_fetch_taxonomy()
    
    if not taxonomy:
        return {}
    
    results = {}
    
    for bird in birds:
        slug = bird.get('slug', '')
        result = search_taxonomy(
            taxonomy,
            slug,
            chinese_name=bird.get('chinese_name', ''),
            english_name=bird.get('english_name', ''),
            scientific_name=bird.get('scientific_name', '')
        )
        
        if result:
            results[slug] = result
    
    return results


def main():
    """测试和演示"""
    import sys
    
    if len(sys.argv) < 2:
        print("用法: python3 smart_ebird_lookup.py <slug> [chinese_name]")
        print("示例: python3 smart_ebird_lookup.py eurasian_hoopoe 戴胜")
        return
    
    slug = sys.argv[1]
    chinese_name = sys.argv[2] if len(sys.argv) > 2 else ""
    
    print(f"\n🔍 搜索: {slug}")
    if chinese_name:
        print(f"   中文名: {chinese_name}")
    
    taxonomy = load_or_fetch_taxonomy()
    
    if not taxonomy:
        print("❌ 无法获取 taxonomy 数据")
        return
    
    result = search_taxonomy(taxonomy, slug, chinese_name=chinese_name)
    
    if result:
        print(f"\n✅ 找到匹配:")
        print(f"   eBird Code: {result['code']}")
        print(f"   英文名: {result['comName']}")
        print(f"   学名: {result['sciName']}")
        print(f"   匹配分数: {result['score']}")
        print(f"\n   🔗 Macaulay Library: https://search.macaulaylibrary.org/catalog?taxonCode={result['code']}&mediaType=a")
    else:
        print("\n❌ 未找到匹配")
        
        # 显示搜索关键词
        keywords = slug_to_keywords(slug)
        print(f"\n   尝试的关键词: {keywords}")


if __name__ == '__main__':
    main()
