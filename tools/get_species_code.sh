#!/bin/bash

# 获取鸟类的eBird Species Code和学名
# 用法: ./get_species_code.sh "Bird Name"

BIRD_NAME="$1"

if [ -z "$BIRD_NAME" ]; then
    echo "用法: $0 \"Bird Name\""
    echo "示例: $0 \"Marsh Tit\""
    echo "      $0 \"Great Tit\""
    echo "      $0 \"Blue Jay\""
    exit 1
fi

echo "=========================================="
echo "搜索鸟类: $BIRD_NAME"
echo "=========================================="
echo ""

# 预处理：如果传入的是 eBird 物种链接，直接提取 species code
if echo "$BIRD_NAME" | grep -qE 'https?://[^ ]*ebird\.org/species/[^ ]+'; then
    DIRECT_CODE=$(echo "$BIRD_NAME" | sed -n 's#.*ebird\.org/species/\([^/?#]*\).*#\1#p')
    if [ -n "$DIRECT_CODE" ]; then
        echo "检测到 eBird 物种链接，直接提取 code: $DIRECT_CODE"
        SPECIES_CODE="$DIRECT_CODE"
    fi
fi

# URL编码
ENCODED_NAME=$(python3 -c "import urllib.parse; print(urllib.parse.quote('$BIRD_NAME'))" 2>/dev/null)
if [ -z "$ENCODED_NAME" ]; then
    ENCODED_NAME=$(echo "$BIRD_NAME" | sed 's/ /+/g')
fi

###############################################
# 方法1: 优先使用 eBird 官方 taxonomy API（需 EBIRD_TOKEN）
###############################################
if [ -z "$SPECIES_CODE" ] && [ -n "$EBIRD_TOKEN" ]; then
    echo "方法1: 使用 eBird taxonomy API 获取 Species Code..."
    echo "--------------------------------------"
    # 先尽量从 iNaturalist 已解析的学名中取；若没有则用输入名
    MATCH_NAME="$SCIENTIFIC_NAME"
    if [ -z "$MATCH_NAME" ] || [ "$MATCH_NAME" = "未找到" ]; then
        MATCH_NAME="$BIRD_NAME"
    fi
    NAME_LOWER=$(echo "$MATCH_NAME" | tr 'A-Z' 'a-z')
    SCI_ENC=$(python3 -c "import urllib.parse,sys;print(urllib.parse.quote(sys.argv[1]))" "$MATCH_NAME" 2>/dev/null || echo "$MATCH_NAME")
    TAXO_URL_SPECIFIC="https://api.ebird.org/v2/ref/taxonomy/ebird?fmt=json&species=$SCI_ENC&locale=en"
    SPECIES_CODE_API=$(curl -s -H "X-eBirdApiToken: $EBIRD_TOKEN" "$TAXO_URL_SPECIFIC" | python3 - <<'PY'
import sys, json
try:
    d = json.load(sys.stdin)
    if isinstance(d, list) and d:
        print(d[0].get('speciesCode',''))
    else:
        print('')
except Exception:
    print('')
PY
    )
    if [ -z "$SPECIES_CODE_API" ]; then
        TAXO_URL="https://api.ebird.org/v2/ref/taxonomy/ebird?fmt=json&locale=en"
        SPECIES_CODE_API=$( NAME_LOWER="$NAME_LOWER" curl -s -H "X-eBirdApiToken: $EBIRD_TOKEN" "$TAXO_URL" | NAME_LOWER="$NAME_LOWER" python3 - <<'PY'
import sys, json, os
name = os.environ.get('NAME_LOWER','').strip().lower()
code = ''
try:
    data = json.load(sys.stdin)
    for r in data:
        sci = r.get('sciName','').strip().lower()
        com = r.get('comName','').strip().lower()
        if name and (name == sci or name == com):
            code = r.get('speciesCode','')
            if code:
                break
    if not code and name:
        for r in data:
            sci = r.get('sciName','').strip().lower()
            if name in sci:
                code = r.get('speciesCode','')
                if code:
                    break
    if not code and name:
        for r in data:
            com = r.get('comName','').strip().lower()
            if name in com:
                code = r.get('speciesCode','')
                if code:
                    break
    print(code)
except Exception:
    print('')
PY
        )
    fi
    # 若仍未命中，快速用 iNaturalist 拿学名再请求一次 taxonomy API
    if [ -z "$SPECIES_CODE_API" ]; then
        INAT_SCI=$(curl -s "https://api.inaturalist.org/v1/taxa?q=$ENCODED_NAME&is_active=true" | python3 - <<'PY'
import sys, json
try:
    d = json.load(sys.stdin)
    r = d.get('results', [])
    if r:
        # 取第一个的学名字段 name
        print(r[0].get('name',''))
    else:
        print('')
except Exception:
    print('')
PY
        )
        if [ -n "$INAT_SCI" ]; then
            SCI_ENC2=$(python3 -c "import urllib.parse,sys;print(urllib.parse.quote(sys.argv[1]))" "$INAT_SCI" 2>/dev/null || echo "$INAT_SCI")
            SPECIES_CODE_API=$(curl -s -H "X-eBirdApiToken: $EBIRD_TOKEN" "https://api.ebird.org/v2/ref/taxonomy/ebird?fmt=json&species=$SCI_ENC2&locale=en" | python3 - <<'PY'
import sys, json
try:
    d = json.load(sys.stdin)
    if isinstance(d, list) and d:
        print(d[0].get('speciesCode',''))
    else:
        print('')
except Exception:
    print('')
PY
            )
            # 同步填写 SCIENTIFIC_NAME，便于后续总结与展示
            if [ -n "$SPECIES_CODE_API" ] && { [ -z "$SCIENTIFIC_NAME" ] || [ "$SCIENTIFIC_NAME" = "未找到" ]; }; then
                SCIENTIFIC_NAME="$INAT_SCI"
            fi
        fi
    fi
    if [ -n "$SPECIES_CODE_API" ]; then
        SPECIES_CODE="$SPECIES_CODE_API"
        echo "  ✅ 找到 Species Code(API): $SPECIES_CODE"
        echo "  验证URL: https://ebird.org/species/$SPECIES_CODE"
        echo "  Macaulay Library搜索: https://search.macaulaylibrary.org/catalog?taxonCode=$SPECIES_CODE"
    else
        echo "  ❌ taxonomy API 未匹配到物种（稍后使用其他兜底）"
    fi
    echo ""
fi

###############################################
# 方法1.5: eBird 网页重定向兜底（无需 token）
###############################################
if [ -z "$SPECIES_CODE" ]; then
    echo "方法1.5: eBird 网页重定向兜底..."
    echo "--------------------------------------"
    EBIRD_URL="https://ebird.org/species/$ENCODED_NAME"
    FINAL_URL=$(curl -s -L -H "User-Agent: Mozilla/5.0" -o /dev/null -w "%{url_effective}" "$EBIRD_URL" 2>/dev/null)
    SPECIES_CODE_REDIRECT=$(echo "$FINAL_URL" | grep -o 'species/[^/]*$' | sed 's/species\///')
    if [ -n "$SPECIES_CODE_REDIRECT" ] && [ "$SPECIES_CODE_REDIRECT" != "$ENCODED_NAME" ]; then
        SPECIES_CODE="$SPECIES_CODE_REDIRECT"
        echo "  ✅ 找到 Species Code: $SPECIES_CODE"
        echo "  验证URL: https://ebird.org/species/$SPECIES_CODE"
        echo "  Macaulay Library搜索: https://search.macaulaylibrary.org/catalog?taxonCode=$SPECIES_CODE"
    else
        echo "  ⚠️  未从eBird找到精确匹配（可能被登录页拦截）"
        SPECIES_CODE="未找到"
    fi
    echo ""
fi

echo ""

# 方法2: 从iNaturalist获取学名
echo "方法2: 从iNaturalist获取学名..."
echo "--------------------------------------"

INATURALIST_API="https://api.inaturalist.org/v1/taxa?q=$ENCODED_NAME&is_active=true"

SCIENTIFIC_NAME=$(curl -s "$INATURALIST_API" | \
    python3 -c "
import json, sys
try:
    data = json.load(sys.stdin)
    results = data.get('results', [])
    if results:
        # 找第一个鸟类结果
        for r in results:
            # 检查是否是鸟类 (Class: Aves)
            if any('Aves' in str(a) for a in r.get('ancestor_ids', [])) or 'Aves' in str(r.get('iconic_taxon_name', '')):
                print(r.get('name', 'N/A'))
                break
        else:
            # 如果没找到鸟类，返回第一个结果
            print(results[0].get('name', 'N/A'))
    else:
        print('N/A')
except:
    print('N/A')
" 2>/dev/null)

TAXON_ID=$(curl -s "$INATURALIST_API" | \
    python3 -c "
import json, sys
try:
    data = json.load(sys.stdin)
    results = data.get('results', [])
    if results:
        print(results[0].get('id', 'N/A'))
    else:
        print('N/A')
except:
    print('N/A')
" 2>/dev/null)

COMMON_NAME_CN=$(curl -s "$INATURALIST_API" | \
    python3 -c "
import json, sys
try:
    data = json.load(sys.stdin)
    results = data.get('results', [])
    if results:
        # 尝试获取中文名
        preferred_names = results[0].get('preferred_common_name', '')
        print(preferred_names if preferred_names else 'N/A')
    else:
        print('N/A')
except:
    print('N/A')
" 2>/dev/null)

if [ "$SCIENTIFIC_NAME" != "N/A" ]; then
    echo "  ✅ 学名: $SCIENTIFIC_NAME"
    echo "  Taxon ID: $TAXON_ID"
    if [ "$COMMON_NAME_CN" != "N/A" ]; then
        echo "  俗名: $COMMON_NAME_CN"
    fi
    echo "  iNaturalist观察: https://www.inaturalist.org/taxa/$TAXON_ID"
else
    echo "  ❌ 未找到"
    SCIENTIFIC_NAME="未找到"
fi

echo ""

# 方法2.5: 兜底获取 eBird Species Code（Macaulay suggest）
if [ -z "$SPECIES_CODE" ] || [ "$SPECIES_CODE" = "未找到" ]; then
    echo "方法2.5: 使用Macaulay suggest兜底获取 eBird Species Code..."
    echo "--------------------------------------"

    # 先用输入名称尝试
    SUGGEST_URL_NAME="https://search.macaulaylibrary.org/suggest?locale=en&entityType=taxa&limit=10&term=$ENCODED_NAME"
    export SCIENTIFIC_NAME  # 传给下方python用于精确匹配学名
    SPECIES_CODE_SUGG=$(curl -s -H "Accept: application/json" -H "User-Agent: Mozilla/5.0" -H "Referer: https://search.macaulaylibrary.org/catalog" "$SUGGEST_URL_NAME" | python3 - <<'PY'
import sys, json, os
try:
    data = json.load(sys.stdin)
    results = data.get('results', [])
    sci = os.environ.get('SCIENTIFIC_NAME', '').strip().lower()
    com = os.environ.get('BIRD_COMMON', '').strip().lower()
    code = ''
    # 1) 优先按学名精确匹配
    if sci:
        for r in results:
            if r.get('taxonCode') and r.get('sciName', '').strip().lower() == sci:
                code = r['taxonCode']
                break
    # 2) 其次按英文俗名精确匹配
    if not code and com:
        for r in results:
            if r.get('taxonCode') and r.get('comName', '').strip().lower() == com:
                code = r['taxonCode']
                break
    # 3) 否则选择第一个包含taxonCode的结果
    if not code:
        for r in results:
            if r.get('taxonCode'):
                code = r['taxonCode']
                break
    print(code)
except Exception:
    print('')
PY
)

    if [ -n "$SPECIES_CODE_SUGG" ]; then
        SPECIES_CODE="$SPECIES_CODE_SUGG"
        echo "  ✅ 找到 Species Code(名称匹配): $SPECIES_CODE"
        echo "  验证URL: https://ebird.org/species/$SPECIES_CODE"
        echo "  Macaulay Library搜索: https://search.macaulaylibrary.org/catalog?taxonCode=$SPECIES_CODE"
    else
        # 若按名称未命中，且已获得学名，则再用学名尝试一次
        if [ "$SCIENTIFIC_NAME" != "未找到" ] && [ -n "$SCIENTIFIC_NAME" ]; then
            SCI_NAME_ENC=$(python3 -c "import urllib.parse,os;print(urllib.parse.quote(os.environ.get('SCI','')))" SCI="$SCIENTIFIC_NAME" 2>/dev/null)
            SUGGEST_URL_SCI="https://search.macaulaylibrary.org/suggest?locale=en&entityType=taxa&limit=10&term=$SCI_NAME_ENC"
            SPECIES_CODE_SUGG=$(curl -s -H "Accept: application/json" -H "User-Agent: Mozilla/5.0" -H "Referer: https://search.macaulaylibrary.org/catalog" "$SUGGEST_URL_SCI" | python3 - <<'PY'
import sys, json, os
try:
    data = json.load(sys.stdin)
    results = data.get('results', [])
    sci = os.environ.get('SCIENTIFIC_NAME', '').strip().lower()
    com = os.environ.get('BIRD_COMMON', '').strip().lower()
    code = ''
    # 1) 优先按学名精确匹配
    if sci:
        for r in results:
            if r.get('taxonCode') and r.get('sciName', '').strip().lower() == sci:
                code = r['taxonCode']
                break
    # 2) 其次按英文俗名精确匹配
    if not code and com:
        for r in results:
            if r.get('taxonCode') and r.get('comName', '').strip().lower() == com:
                code = r['taxonCode']
                break
    # 3) 否则选择第一个包含taxonCode的结果
    if not code:
        for r in results:
            if r.get('taxonCode'):
                code = r['taxonCode']
                break
    print(code)
except Exception:
    print('')
PY
)
            if [ -n "$SPECIES_CODE_SUGG" ]; then
                SPECIES_CODE="$SPECIES_CODE_SUGG"
                echo "  ✅ 找到 Species Code(学名匹配): $SPECIES_CODE"
                echo "  验证URL: https://ebird.org/species/$SPECIES_CODE"
                echo "  Macaulay Library搜索: https://search.macaulaylibrary.org/catalog?taxonCode=$SPECIES_CODE"
            else
                echo "  ❌ 兜底未找到Species Code"
            fi
        else
            echo "  ❌ 兜底未找到Species Code"
        fi
    fi
    echo ""
fi

# 方法2.7: 通过 Macaulay search(q=学名) 获取 Asset 并从 Asset 页面提取 species code
if [ -z "$SPECIES_CODE" ] || [ "$SPECIES_CODE" = "未找到" ]; then
    if [ "$SCIENTIFIC_NAME" != "未找到" ] && [ -n "$SCIENTIFIC_NAME" ]; then
        echo "方法2.7: 通过 Macaulay search(q=学名) -> Asset 页面提取 species code..."
        echo "--------------------------------------"
        Q_ENC=$(python3 -c "import urllib.parse,sys;print(urllib.parse.quote(sys.argv[1]))" "$SCIENTIFIC_NAME" 2>/dev/null || echo "$SCIENTIFIC_NAME")
        SEARCH_URL="https://search.macaulaylibrary.org/api/v1/search?q=$Q_ENC&mediaType=p&sort=rating_rank_desc&count=5"
        ASSET_ID=$(curl -s -H "Accept: application/json" -H "User-Agent: Mozilla/5.0" "$SEARCH_URL" | \
          python3 - <<'PY'
import sys, json
try:
    d = json.load(sys.stdin)
    c = d.get('results', {}).get('content', [])
    print(c[0].get('assetId') if c else '')
except Exception:
    print('')
PY
        )
        if [ -n "$ASSET_ID" ]; then
            HTML=$(curl -s -H "User-Agent: Mozilla/5.0" "https://macaulaylibrary.org/asset/$ASSET_ID")
            CODE_FROM_ASSET=$(echo "$HTML" | grep -o 'ebird.org/species/[^"\'']*' | sed 's#.*/species/##' | head -1)
            if [ -n "$CODE_FROM_ASSET" ]; then
                SPECIES_CODE="$CODE_FROM_ASSET"
                echo "  ✅ 从 Asset 提取到 Species Code: $SPECIES_CODE"
                echo "  验证URL: https://ebird.org/species/$SPECIES_CODE"
            else
                echo "  ❌ 未在 Asset 页面发现 eBird 物种链接"
            fi
        else
            echo "  ❌ search(q=学名) 未返回 Asset"
        fi
        echo ""
    fi
fi
# 方法2.6: 使用 eBird 官方 taxonomy API（需 EBIRD_TOKEN）
if [ -z "$SPECIES_CODE" ] || [ "$SPECIES_CODE" = "未找到" ]; then
    if [ -n "$EBIRD_TOKEN" ]; then
        echo "方法2.6: 使用 eBird taxonomy API 获取 Species Code..."
        echo "--------------------------------------"
        # 优先使用学名匹配，其次英文俗名
        MATCH_NAME="$SCIENTIFIC_NAME"
        if [ -z "$MATCH_NAME" ] || [ "$MATCH_NAME" = "未找到" ]; then
            MATCH_NAME="$BIRD_NAME"
        fi
        NAME_LOWER=$(echo "$MATCH_NAME" | tr 'A-Z' 'a-z')
        # 优先精确查询（带 species 参数，返回极小结果集）
        SCI_ENC=$(python3 -c "import urllib.parse,sys;print(urllib.parse.quote(sys.argv[1]))" "$MATCH_NAME" 2>/dev/null || echo "$MATCH_NAME")
        TAXO_URL_SPECIFIC="https://api.ebird.org/v2/ref/taxonomy/ebird?fmt=json&species=$SCI_ENC&locale=en"
        SPECIES_CODE_API=$(curl -s -H "X-eBirdApiToken: $EBIRD_TOKEN" "$TAXO_URL_SPECIFIC" | python3 - <<'PY'
import sys, json
try:
    d = json.load(sys.stdin)
    if isinstance(d, list) and d:
        print(d[0].get('speciesCode',''))
    else:
        print('')
except Exception:
    print('')
PY
        )
        # 若精确查询失败，再回退全量匹配
        if [ -z "$SPECIES_CODE_API" ]; then
            TAXO_URL="https://api.ebird.org/v2/ref/taxonomy/ebird?fmt=json&locale=en"
            SPECIES_CODE_API=$( NAME_LOWER="$NAME_LOWER" curl -s -H "X-eBirdApiToken: $EBIRD_TOKEN" "$TAXO_URL" | NAME_LOWER="$NAME_LOWER" python3 - <<'PY'
import sys, json, os
name = os.environ.get('NAME_LOWER','').strip().lower()
code = ''
try:
    data = json.load(sys.stdin)
    # 先完全匹配学名或英文名
    for r in data:
        sci = r.get('sciName','').strip().lower()
        com = r.get('comName','').strip().lower()
        if name and (name == sci or name == com):
            code = r.get('speciesCode','')
            if code:
                break
    # 再尝试前缀/包含匹配（容错部分变体），优先 sciName
    if not code and name:
        for r in data:
            sci = r.get('sciName','').strip().lower()
            if name in sci:
                code = r.get('speciesCode','')
                if code:
                    break
    if not code and name:
        for r in data:
            com = r.get('comName','').strip().lower()
            if name in com:
                code = r.get('speciesCode','')
                if code:
                    break
    print(code)
except Exception:
    print('')
PY
            )
        fi
        if [ -n "$SPECIES_CODE_API" ]; then
            SPECIES_CODE="$SPECIES_CODE_API"
            echo "  ✅ 找到 Species Code(API): $SPECIES_CODE"
            echo "  验证URL: https://ebird.org/species/$SPECIES_CODE"
            echo "  Macaulay Library搜索: https://search.macaulaylibrary.org/catalog?taxonCode=$SPECIES_CODE"
        else
            echo "  ❌ taxonomy API 未匹配到物种"
        fi
        echo ""
    fi
fi

# 方法3: 尝试从Wikipedia获取
echo "方法3: 从Wikipedia获取信息..."
echo "--------------------------------------"

WIKI_URL="https://en.wikipedia.org/w/api.php?action=query&format=json&titles=${ENCODED_NAME}&prop=extracts&exintro=true&explaintext=true"

WIKI_EXTRACT=$(curl -s "$WIKI_URL" | \
    python3 -c "
import json, sys
try:
    data = json.load(sys.stdin)
    pages = data.get('query', {}).get('pages', {})
    for page_id in pages:
        if page_id != '-1':
            extract = pages[page_id].get('extract', '')[:200]
            # 尝试提取学名（通常在括号中）
            import re
            match = re.search(r'\(([A-Z][a-z]+ [a-z]+)\)', extract)
            if match:
                print(match.group(1))
            else:
                print('Found but no scientific name')
            break
    else:
        print('N/A')
except:
    print('N/A')
" 2>/dev/null)

if [ "$WIKI_EXTRACT" != "N/A" ] && [ "$WIKI_EXTRACT" != "Found but no scientific name" ]; then
    echo "  ✅ Wikipedia学名: $WIKI_EXTRACT"
    echo "  Wikipedia页面: https://en.wikipedia.org/wiki/${ENCODED_NAME}"
elif [ "$WIKI_EXTRACT" = "Found but no scientific name" ]; then
    echo "  ⚠️  找到Wikipedia页面但未提取到学名"
    echo "  Wikipedia页面: https://en.wikipedia.org/wiki/${ENCODED_NAME}"
else
    echo "  ❌ 未找到Wikipedia页面"
fi

echo ""
echo "=========================================="
echo "=== 总结 ==="
echo "=========================================="
echo ""
echo "🐦 英文名: $BIRD_NAME"
echo "🔬 学名: $SCIENTIFIC_NAME"
echo "🏷️  eBird Species Code: $SPECIES_CODE"
if [ "$TAXON_ID" != "N/A" ]; then
    echo "🆔 iNaturalist Taxon ID: $TAXON_ID"
fi
echo ""
echo "=========================================="
echo "=== 使用方式 ==="
echo "=========================================="
echo ""

if [ "$SPECIES_CODE" != "未找到" ]; then
    echo "Macaulay Library API:"
    echo "  curl \"https://search.macaulaylibrary.org/api/v1/search?taxonCode=$SPECIES_CODE&mediaType=p&sort=rating_rank_desc&count=10\""
    echo ""
fi

if [ "$SCIENTIFIC_NAME" != "未找到" ]; then
    echo "iNaturalist API:"
    echo "  curl \"https://api.inaturalist.org/v1/observations?taxon_name=$(echo $SCIENTIFIC_NAME | sed 's/ /%20/g')&quality_grade=research&photos=true&per_page=10\""
    echo ""
fi

if [ "$SPECIES_CODE" != "未找到" ] || [ "$SCIENTIFIC_NAME" != "未找到" ]; then
    echo "Wikipedia:"
    echo "  https://en.wikipedia.org/wiki/${ENCODED_NAME}"
    echo ""
fi

echo "=========================================="
echo "✅ 完成！"
echo "=========================================="

