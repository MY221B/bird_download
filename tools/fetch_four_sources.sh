#!/bin/bash

# 用法: ./fetch_four_sources.sh <slug> <English Name> <Scientific Name> [Wikipedia_Page_Name] [--sources <source1,source2,...>]
# 
# 优化说明：
# - 容错模式：单个源失败不影响其他源
# - 文件检测：跳过已下载的文件
# - 优化性能：移除重复 API 调用
# - 支持选择下载指定来源：--sources macaulay,inaturalist,wikimedia,avibase
#   默认下载所有4个来源

# 注释掉严格模式，改为容错模式
# set -e
# set -o pipefail

# 解析参数
SLUG=""
EN_NAME=""
SCI_NAME=""
WIKI_PAGE_NAME=""
SOURCES=""  # 要下载的来源，逗号分隔，如 "macaulay,inaturalist"

# 解析参数：先提取 --sources，再处理位置参数
ARGS=()
while [[ $# -gt 0 ]]; do
  case $1 in
    --sources)
      SOURCES="$2"
      shift 2
      ;;
    *)
      ARGS+=("$1")
      shift
      ;;
  esac
done

# 从位置参数中提取
if [ ${#ARGS[@]} -ge 1 ]; then
  SLUG="${ARGS[0]}"
fi
if [ ${#ARGS[@]} -ge 2 ]; then
  EN_NAME="${ARGS[1]}"
fi
if [ ${#ARGS[@]} -ge 3 ]; then
  SCI_NAME="${ARGS[2]}"
fi
if [ ${#ARGS[@]} -ge 4 ]; then
  WIKI_PAGE_NAME="${ARGS[3]}"
fi

if [ -z "$SLUG" ] || [ -z "$EN_NAME" ] || [ -z "$SCI_NAME" ]; then
  echo "用法: $0 <slug> <English Name> <Scientific Name> [Wikipedia_Page_Name] [--sources <source1,source2,...>]"
  echo "示例: $0 bluetail 'Red-flanked Bluetail' 'Tarsiger cyanurus' Red-flanked_Bluetail"
  echo "      $0 bluetail 'Red-flanked Bluetail' 'Tarsiger cyanurus' Red-flanked_Bluetail --sources macaulay"
  echo "      $0 bluetail 'Red-flanked Bluetail' 'Tarsiger cyanurus' --sources macaulay,inaturalist"
  echo ""
  echo "可用来源: macaulay, inaturalist, wikimedia, avibase"
  echo "默认: 下载所有4个来源"
  exit 1
fi

# 如果没有指定来源，默认下载所有
if [ -z "$SOURCES" ]; then
  SOURCES="macaulay,inaturalist,wikimedia,avibase"
fi

# 检查是否应该下载某个来源
should_download() {
  local source="$1"
  echo "$SOURCES" | grep -q "$source"
}

ENC_EN_NAME=$(python3 -c "import urllib.parse,sys;print(urllib.parse.quote(sys.argv[1]))" "$EN_NAME" 2>/dev/null || echo "$EN_NAME")
WIKI_PAGE_NAME=${WIKI_PAGE_NAME:-$(echo "$EN_NAME" | tr ' ' '_' )}

BASE_DIR="images/$SLUG"
mkdir -p "$BASE_DIR/macaulay" "$BASE_DIR/inaturalist" "$BASE_DIR/wikimedia" "$BASE_DIR/avibase"

# 初始化元数据文件
METADATA_FILE="$BASE_DIR/download_metadata.json"
if [ ! -f "$METADATA_FILE" ]; then
  echo '{"macaulay":[],"inaturalist":[],"wikimedia":[],"avibase":[]}' > "$METADATA_FILE"
fi

echo "=========================================="
echo "开始下载: $EN_NAME"
echo "学名: $SCI_NAME"
echo "Slug: $SLUG"
echo "=========================================="
echo ""

# 1) 直接调 eBird taxonomy 获取 Species Code（优化：移除重复调用 + 添加缓存）
EBIRD_CODE=""
if [ -n "$EBIRD_TOKEN" ]; then
  # 使用 curl 而非 Python urllib（避免 SSL 证书问题）
  ENC_SCI_NAME=$(python3 -c "import urllib.parse,sys;print(urllib.parse.quote(sys.argv[1]))" "$SCI_NAME" 2>/dev/null || echo "$SCI_NAME")
  EBIRD_RESP=$(curl -s -H "X-eBirdApiToken: $EBIRD_TOKEN" \
    "https://api.ebird.org/v2/ref/taxonomy/ebird?fmt=json&locale=en&species=$ENC_SCI_NAME")
  
  if [ -n "$EBIRD_RESP" ]; then
    EBIRD_CODE=$(echo "$EBIRD_RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d[0]['speciesCode'] if d else '')" 2>/dev/null || echo "")
  fi
  
  # 1.2) 如果学名未找到，用英文名从完整 taxonomy 中查找（应对学名分类变更）
  if [ -z "$EBIRD_CODE" ]; then
    echo "[日志] 学名未找到，尝试用英文名从 eBird taxonomy 中查找…"
    
    # 优化：使用缓存（月度更新）
    CACHE_DIR="$HOME/.cache/bird_memory_cards"
    mkdir -p "$CACHE_DIR"
    CACHE_FILE="$CACHE_DIR/ebird_taxonomy_$(date +%Y%m).json"

    # 验证缓存文件是否有效（必须是有记录的 JSON 数组）
    _cache_valid=0
    if [ -f "$CACHE_FILE" ]; then
      _record_count=$(python3 -c "import json,sys; d=json.load(open(sys.argv[1])); print(len(d))" "$CACHE_FILE" 2>/dev/null || echo "0")
      if [ "$_record_count" -gt 100 ] 2>/dev/null; then
        _cache_valid=1
      else
        echo "[日志] 缓存文件无效（记录数: ${_record_count}），将重新下载"
        rm -f "$CACHE_FILE"
      fi
    fi

    if [ "$_cache_valid" -eq 1 ]; then
      echo "[日志] 使用缓存的 eBird taxonomy（$(date +%Y-%m)，${_record_count} 条）"
      EBIRD_FULL=$(cat "$CACHE_FILE")
    else
      echo "[日志] 下载完整 eBird taxonomy（首次或月度更新）..."
      EBIRD_FULL=$(curl -s -H "X-eBirdApiToken: $EBIRD_TOKEN" \
        "https://api.ebird.org/v2/ref/taxonomy/ebird?fmt=json&locale=en")
      # 验证下载结果再保存到缓存
      _dl_count=$(echo "$EBIRD_FULL" | python3 -c "import json,sys; d=json.load(sys.stdin); print(len(d))" 2>/dev/null || echo "0")
      if [ "$_dl_count" -gt 100 ] 2>/dev/null; then
        echo "$EBIRD_FULL" > "$CACHE_FILE"
        echo "[日志] 已缓存到: $CACHE_FILE（${_dl_count} 条记录）"
      else
        echo "[日志] ⚠️  下载的 taxonomy 无效（记录数: ${_dl_count}），跳过缓存保存"
        EBIRD_FULL=""
      fi
    fi
    
    if [ -n "$EBIRD_FULL" ]; then
      EBIRD_CODE=$(echo "$EBIRD_FULL" | EN_NAME="$EN_NAME" SCI_NAME="$SCI_NAME" python3 -c 'import sys,json,os
d=json.load(sys.stdin)
en=os.environ.get("EN_NAME","").strip().lower()
sci=os.environ.get("SCI_NAME","").strip().lower()
# 先用学名精确匹配（不受 locale 影响）
code=""
for item in d:
    if item.get("sciName"," ").strip().lower()==sci:
        code=item.get("speciesCode","")
        break
if not code:
    for item in d:
        if item.get("comName"," ").strip().lower()==en:
            code=item.get("speciesCode","")
            break
print(code)
' 2>/dev/null || echo "")
      
      if [ -n "$EBIRD_CODE" ]; then
        echo "[日志] 通过英文名找到 speciesCode: $EBIRD_CODE (eBird学名: $(echo "$EBIRD_FULL" | EBIRD_CODE="$EBIRD_CODE" python3 -c 'import sys,json,os; d=json.load(sys.stdin); code=os.environ.get("EBIRD_CODE",""); print(next((item.get("sciName","") for item in d if item.get("speciesCode","")==code), ""))' 2>/dev/null || echo ""))"
      fi
    fi
  fi
fi

# 1.3) 仍无 code：用 tools/smart_ebird_lookup（仓库 taxonomy 缓存 + 过期仍可用 + slug 硬编码兜底）
if [ -z "$EBIRD_CODE" ]; then
  _REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
  EBIRD_CODE=$(cd "$_REPO_ROOT" && SLUG="$SLUG" EN_NAME="$EN_NAME" SCI_NAME="$SCI_NAME" python3 -c '
import os, sys
sys.path.insert(0, "tools")
from smart_ebird_lookup import smart_get_ebird_code
c = smart_get_ebird_code(
    slug=os.environ.get("SLUG", ""),
    english_name=os.environ.get("EN_NAME", ""),
    scientific_name=os.environ.get("SCI_NAME", ""),
)
print(c or "")
' 2>/dev/null || echo "")
  if [ -n "$EBIRD_CODE" ]; then
    echo "[日志] smart_ebird_lookup（仓库）speciesCode: $EBIRD_CODE"
  fi
fi

if [ -n "$EBIRD_CODE" ]; then
  echo "[日志] eBird taxonomy speciesCode: $EBIRD_CODE" 
  echo "[日志] Macaulay页面(用speciesCode充当taxonCode): https://search.macaulaylibrary.org/catalog?taxonCode=$EBIRD_CODE&sort=rating_rank_desc"
else
  echo "[日志] eBird taxonomy speciesCode: 无" 
fi

# 下载 Macaulay 照片的函数
download_macaulay() {
if should_download "macaulay"; then
echo "📥 [1/4] Macaulay Library"

# 直接使用 eBird code 作为 Macaulay taxonCode（无需 API 搜索学名/英文名）
ML_CODE=""
if [ -n "$EBIRD_CODE" ]; then
  ML_CODE="$EBIRD_CODE"
  echo "  [日志] 使用 eBird speciesCode: $ML_CODE"
fi

if [ -z "$ML_CODE" ]; then
  echo "  ❌ 未通过 eBird taxonomy 获取到 speciesCode（学名：$SCI_NAME，英文名：$EN_NAME）"
  echo "  提示：跳过 Macaulay，不会清空已有数据"
  ASSETS=""
  MACAULAY_SEARCH_OK=0
else
  echo "  [日志] 使用持久浏览器会话查询 taxonCode=$ML_CODE …"
  MACAULAY_BROWSER_HELPER="${MACAULAY_BROWSER_HELPER:-tools/macaulay_browser.py}"
  ASSET_ERR=$(mktemp -t macaulay_browser.XXXXXX)
  ASSETS=$(python3 "$MACAULAY_BROWSER_HELPER" search --taxon-code "$ML_CODE" --count 20 2>"$ASSET_ERR")
  MACAULAY_BROWSER_STATUS=$?
  if [ "$MACAULAY_BROWSER_STATUS" -ne 0 ]; then
    sed 's/^/  /' "$ASSET_ERR" >&2
    echo "  ⚠️  Macaulay 浏览器查询不可用，本轮保留已有图片和元数据"
    echo "  提示：python3 tools/macaulay_browser.py setup"
    ASSETS=""
    MACAULAY_SEARCH_OK=0
  else
    MACAULAY_SEARCH_OK=1
  fi
  rm -f "$ASSET_ERR"
fi
COUNT=0
MACAULAY_META="[]"
for ASSET_ID in $ASSETS; do
  [ $COUNT -ge 3 ] && break
  OUT="$BASE_DIR/macaulay/${SLUG}_$ASSET_ID.jpg"
  
  # 优化：检测文件是否已存在且有效
  if [ -f "$OUT" ] && file "$OUT" 2>/dev/null | grep -q "JPEG\|PNG\|image"; then
    echo "  ⏭️  已存在: $OUT"
    COUNT=$((COUNT+1))
    # 保存元数据
    MACAULAY_META=$(echo "$MACAULAY_META" | python3 -c "import sys,json; d=json.load(sys.stdin); d.append({'filename':'${SLUG}_${ASSET_ID}.jpg','asset_id':'$ASSET_ID','asset_url':'https://macaulaylibrary.org/asset/$ASSET_ID'}); print(json.dumps(d))")
    continue
  fi
  
  # 下载文件（容错：失败不退出）
  curl -s -o "$OUT" "https://cdn.download.ams.birds.cornell.edu/api/v2/asset/${ASSET_ID}/1200" || {
    echo "  ⚠️  下载失败: $ASSET_ID"
    continue
  }
  
  if file "$OUT" 2>/dev/null | grep -q "JPEG\|PNG\|image"; then
    COUNT=$((COUNT+1))
    echo "  ✅ Macaulay: $OUT"
    # 保存元数据
    MACAULAY_META=$(echo "$MACAULAY_META" | python3 -c "import sys,json; d=json.load(sys.stdin); d.append({'filename':'${SLUG}_${ASSET_ID}.jpg','asset_id':'$ASSET_ID','asset_url':'https://macaulaylibrary.org/asset/$ASSET_ID'}); print(json.dumps(d))")
  else
    rm -f "$OUT"
  fi
done

# 只有搜索成功且至少得到一张有效图片时才替换元数据。
# 会话失效、反爬验证或网络故障都不得清空旧数据。
if [ "${MACAULAY_SEARCH_OK:-0}" -eq 1 ] && [ "$COUNT" -gt 0 ]; then
  python3 -c "import sys,json; data=json.load(open('$METADATA_FILE')); data['macaulay']=json.loads('$MACAULAY_META'); json.dump(data, open('$METADATA_FILE','w'), indent=2)"
elif [ "${MACAULAY_SEARCH_OK:-0}" -eq 1 ]; then
  echo "  ⚠️  Macaulay 未下载到有效图片，保留已有元数据"
fi

echo "  [日志] Macaulay 最终下载数量: $COUNT"

# HTML 回退：若 API 未获取到任何 asset，则解析搜索页面 HTML 提取 assetId
: # 按新规则：未获取到 code 时不再使用 HTML 回退，直接结束 Macaulay 流程
else
  echo "⏭️  跳过 Macaulay Library（未在 --sources 中指定）"
fi
}

# 下载 iNaturalist 照片的函数
download_inaturalist() {
if should_download "inaturalist"; then
echo ""
echo "📥 [2/4] iNaturalist"
INAT_URL="https://api.inaturalist.org/v1/observations?taxon_name=$(echo "$SCI_NAME" | sed 's/ /%20/g')&quality_grade=research&photos=true&per_page=10&order_by=votes"
echo "  [日志] iNat API: $INAT_URL"

# 获取完整的观察数据（包含元数据）
INAT_DATA=$(curl -s "$INAT_URL" 2>/dev/null) || {
  echo "  ⚠️  iNaturalist API 调用失败，跳过"
  INAT_DATA=""
}

ICOUNT=0
INAT_META="[]"
if [ -n "$INAT_DATA" ]; then
  # 使用Python处理JSON并下载
  echo "$INAT_DATA" | python3 -c "
import sys, json, subprocess
try:
    data = json.load(sys.stdin)
    results = data.get('results', [])
    count = 0
    metadata = []
    
    for obs in results[:3]:
        photos = obs.get('photos', [])
        if not photos:
            continue
        
        photo = photos[0]
        user = obs.get('user', {})
        obs_id = obs.get('id')
        photo_id = photo.get('id')
        url = photo.get('url', '').replace('square', 'large')
        license_code = photo.get('license_code', '')
        
        filename = '${SLUG}_' + str(count+1) + '.jpg'
        out_path = '$BASE_DIR/inaturalist/' + filename
        
        # 下载图片
        result = subprocess.run(['curl', '-s', '-o', out_path, url], capture_output=True)
        
        if result.returncode == 0:
            # 验证文件
            verify = subprocess.run(['file', out_path], capture_output=True, text=True)
            if 'JPEG' in verify.stdout or 'PNG' in verify.stdout:
                count += 1
                print(f'  ✅ iNat: {filename}')
                
                # 生成引用格式
                if license_code:
                    credit = f'© {user.get(\"login\", \"Unknown\")} (via iNaturalist), some rights reserved ({license_code.upper()})'
                else:
                    credit = f'© {user.get(\"login\", \"Unknown\")} (via iNaturalist), All Rights Reserved'
                
                # 保存元数据
                metadata.append({
                    'filename': filename,
                    'observation_id': obs_id,
                    'photo_id': photo_id,
                    'observation_url': f'https://www.inaturalist.org/observations/{obs_id}',
                    'photographer': user.get('login'),
                    'license': license_code or 'all-rights-reserved',
                    'credit_format': credit
                })
                
                if count >= 3:
                    break
    
    # 输出元数据JSON
    print('__METADATA_START__')
    print(json.dumps(metadata))
    print('__METADATA_END__')
    
except Exception as e:
    print(f'  ⚠️  处理失败: {e}', file=sys.stderr)
" | tee /tmp/inat_output.txt
  
  # 提取元数据
  INAT_META=$(cat /tmp/inat_output.txt | sed -n '/__METADATA_START__/,/__METADATA_END__/p' | grep -v '__METADATA_' || echo "[]")
  ICOUNT=$(echo "$INAT_META" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "0")
  
  # 保存元数据
  if [ -n "$INAT_META" ] && [ "$INAT_META" != "[]" ]; then
    python3 -c "import sys,json; data=json.load(open('$METADATA_FILE')); data['inaturalist']=$INAT_META; json.dump(data, open('$METADATA_FILE','w'), indent=2)" 2>/dev/null || true
  fi
fi

echo "  [日志] iNat 下载数量: $ICOUNT"
else
  echo "⏭️  跳过 iNaturalist（未在 --sources 中指定）"
fi
}

# 下载 Wikimedia 照片的函数
download_wikimedia() {
if should_download "wikimedia"; then
echo ""
echo "📥 [3/4] Wikimedia (from Wikipedia: $WIKI_PAGE_NAME)"
WIKI_HTML=$(curl -s "https://en.wikipedia.org/wiki/$WIKI_PAGE_NAME" 2>/dev/null) || {
  echo "  ⚠️  Wikipedia 页面获取失败，跳过"
  WIKI_HTML=""
}

WCOUNT=0
WIKI_META="[]"
if [ -n "$WIKI_HTML" ]; then
  # 提取图片文件名并获取元数据
  echo "$WIKI_HTML" | grep -o 'upload\.wikimedia\.org/wikipedia/commons/thumb/[^/]*/[^/]*/\([^/]*\.jpg\)/[0-9]*px-[^\"]*\.jpg' | head -5 | while read U; do
    [ $WCOUNT -ge 1 ] && break
    
    # 提取原始文件名
    ORIG_FILENAME=$(echo "$U" | sed -n 's|.*/\([^/]*\.jpg\)/.*|\1|p')
    
    # 过滤标本/插图
    if echo "$ORIG_FILENAME" | grep -qi "MHNT\|Dresser\|map\|range\|illustration"; then
      continue
    fi
    
    OUT="$BASE_DIR/wikimedia/${SLUG}_$((WCOUNT+1)).jpg"
    
    # 下载文件
    curl -s -o "$OUT" "https://$U" || {
      echo "  ⚠️  下载失败: $U"
      continue
    }
    
    if file "$OUT" 2>/dev/null | grep -q "JPEG\|PNG"; then
      WCOUNT=$((WCOUNT+1))
      echo "  ✅ Wikimedia: $OUT (原文件: $ORIG_FILENAME)"
      
      # 获取 Wikimedia Commons 元数据
      WIKI_API_URL="https://commons.wikimedia.org/w/api.php?action=query&format=json&prop=imageinfo&titles=File:${ORIG_FILENAME}&iiprop=extmetadata"
      WIKI_METADATA=$(curl -s "$WIKI_API_URL" | python3 -c "
import sys, json, re
try:
    data = json.load(sys.stdin)
    pages = data.get('query', {}).get('pages', {})
    for page in pages.values():
        imageinfo = page.get('imageinfo', [])
        if imageinfo:
            metadata = imageinfo[0].get('extmetadata', {})
            artist = metadata.get('Artist', {}).get('value', 'Unknown')
            license_short = metadata.get('LicenseShortName', {}).get('value', 'Unknown')
            license_url = metadata.get('LicenseUrl', {}).get('value', '')
            attribution = metadata.get('Attribution', {}).get('value', '')
            
            # 清理HTML标签
            artist_clean = re.sub(r'<[^>]+>', '', artist)
            attribution_clean = re.sub(r'<[^>]+>', '', attribution)
            
            if not attribution_clean:
                attribution_clean = f'{artist_clean}, {license_short}, via Wikimedia Commons'
            
            result = {
                'filename': '${SLUG}_$((WCOUNT)).jpg',
                'original_filename': '${ORIG_FILENAME}',
                'commons_url': 'https://commons.wikimedia.org/wiki/File:${ORIG_FILENAME}',
                'photographer': artist_clean,
                'license': license_short,
                'license_url': license_url,
                'credit_format': attribution_clean
            }
            print(json.dumps(result))
            break
except Exception as e:
    print('{}')
" 2>/dev/null)
      
      # 添加到元数据数组
      if [ -n "$WIKI_METADATA" ] && [ "$WIKI_METADATA" != "{}" ]; then
        WIKI_META=$(echo "$WIKI_META" | python3 -c "import sys,json; d=json.load(sys.stdin); d.append($WIKI_METADATA); print(json.dumps(d))")
      fi
    else
      rm -f "$OUT"
    fi
  done
  
  # 保存 Wikimedia 元数据
  if [ -n "$WIKI_META" ] && [ "$WIKI_META" != "[]" ]; then
    python3 -c "import sys,json; data=json.load(open('$METADATA_FILE')); data['wikimedia']=json.loads('$WIKI_META'); json.dump(data, open('$METADATA_FILE','w'), indent=2)" 2>/dev/null || true
  fi
fi

echo "  [日志] Wikimedia 下载数量: $WCOUNT"
else
  echo "⏭️  跳过 Wikimedia（未在 --sources 中指定）"
fi
}

# 下载 Avibase 照片的函数
download_avibase() {
if should_download "avibase"; then
echo ""
echo "📥 [4/4] Avibase (Flickr via CN 清单 + sec=flickr)"
python3 tools/download_from_avibase.py "$EN_NAME" "$SCI_NAME" "$BASE_DIR/avibase" 3 || true
else
  echo "⏭️  跳过 Avibase（未在 --sources 中指定）"
fi
}

# 主流程：调用各个下载函数
download_macaulay
download_inaturalist
download_wikimedia
download_avibase

echo ""
echo "完成: $SLUG"

