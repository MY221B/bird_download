#!/bin/bash

# 批量下载鸟类图片工具
# 支持 CSV 输入和并行下载

# 进程替换管道下 Python  stdout 可能非 UTF-8；bash 也需一致 locale，否则中文会变成
export LC_ALL="${LC_ALL:-en_US.UTF-8}"
export LANG="${LANG:-en_US.UTF-8}"
export PYTHONIOENCODING=utf-8

usage() {
  cat << 'EOF'
用法: ./batch_fetch.sh <birds_file> [--parallel N] [--skip-existing]

参数:
  birds_file       CSV 文件路径，支持两种格式：
                   1. slug,english_name,scientific_name[,wikipedia_page]
                   2. slug,chinese_name,english_name,scientific_name,wikipedia_page
  --parallel N     并行下载数量（默认：3，推荐：3-5）
  --skip-existing  跳过已存在的目录（默认：否）

CSV 格式示例:
  # 格式1（不含中文名）:
  # slug,english_name,scientific_name,wikipedia_page
  bluetail,Red-flanked Bluetail,Tarsiger cyanurus,Red-flanked_Bluetail
  
  # 格式2（含中文名，支持引号）:
  # slug,chinese_name,english_name,scientific_name,wikipedia_page
  bluetail,"红胁蓝尾鸲",Red-flanked Bluetail,Tarsiger cyanurus,Red-flanked_Bluetail

示例:
  ./batch_fetch.sh birds.csv
  ./batch_fetch.sh birds.csv --parallel 5
  ./batch_fetch.sh birds.csv --skip-existing

环境变量:
  EBIRD_TOKEN      eBird API Token（必需）
EOF
  exit 1
}

# 参数解析
BIRDS_FILE="$1"
PARALLEL=3
SKIP_EXISTING=0

if [ -z "$BIRDS_FILE" ]; then
  usage
fi

if [ ! -f "$BIRDS_FILE" ]; then
  echo "❌ 文件不存在: $BIRDS_FILE"
  exit 1
fi

shift
while [ $# -gt 0 ]; do
  case "$1" in
    --parallel)
      PARALLEL="$2"
      shift 2
      ;;
    --skip-existing)
      SKIP_EXISTING=1
      shift
      ;;
    *)
      echo "❌ 未知参数: $1"
      usage
      ;;
  esac
done

# 检查 eBird Token，如果不存在则尝试从 config/ebird_token.sh 加载
if [ -z "$EBIRD_TOKEN" ]; then
  TOKEN_FILE="config/ebird_token.sh"
  if [ -f "$TOKEN_FILE" ]; then
    echo "📋 从 $TOKEN_FILE 自动加载 EBIRD_TOKEN..."
    source "$TOKEN_FILE"
  fi
fi

if [ -z "$EBIRD_TOKEN" ]; then
  echo "❌ 缺少环境变量 EBIRD_TOKEN"
  echo "请设置: export EBIRD_TOKEN=your_token"
  echo "或确保 config/ebird_token.sh 文件存在"
  exit 1
fi

echo "╔═══════════════════════════════════════════════════════════════╗"
echo "║               🐦 批量下载鸟类图片                              ║"
echo "╚═══════════════════════════════════════════════════════════════╝"
echo ""
echo "配置:"
echo "  - 输入文件: $BIRDS_FILE"
echo "  - 并行数量: $PARALLEL"
echo "  - 跳过已存在: $([ $SKIP_EXISTING -eq 1 ] && echo '是' || echo '否')"
echo ""

# 统计信息
TOTAL_BIRDS=$(grep -v '^#' "$BIRDS_FILE" | grep -v '^$' | wc -l | tr -d ' ')
PROCESSED=0
SKIPPED=0
SUCCESS=0
FAILED=0

echo "总共 $TOTAL_BIRDS 种鸟类"
echo "=========================================="
echo ""

START_TIME=$(date +%s)

# 读取 CSV 并处理（使用 Python 正确解析 CSV，支持引号和 chinese_name 字段）
# 使用进程替换避免子 shell 问题，确保变量修改在父 shell 中生效
while IFS='|' read -r slug en_name chinese_name sci_name wiki_page; do
  
  # 跳过空行
  [[ -z "$slug" ]] && continue
  
  PROCESSED=$((PROCESSED + 1))
  
  # 检查是否跳过已存在
  if [ $SKIP_EXISTING -eq 1 ] && [ -d "images/$slug" ]; then
    if [ -n "$chinese_name" ]; then
      echo "[$PROCESSED/$TOTAL_BIRDS] ⏭️  跳过已存在: $slug ($en_name（$chinese_name）)"
    else
      echo "[$PROCESSED/$TOTAL_BIRDS] ⏭️  跳过已存在: $slug ($en_name)"
    fi
    SKIPPED=$((SKIPPED + 1))
    continue
  fi
  
  # 显示下载信息，如果有中文名则显示
  if [ -n "$chinese_name" ]; then
    echo "[$PROCESSED/$TOTAL_BIRDS] 📥 下载: $slug ($en_name（$chinese_name）)"
  else
    echo "[$PROCESSED/$TOTAL_BIRDS] 📥 下载: $slug ($en_name)"
  fi
  
  # 后台执行下载
  (
    if ./tools/fetch_four_sources.sh "$slug" "$en_name" "$sci_name" "$wiki_page" > "/tmp/${slug}_download.log" 2>&1; then
      echo "[$PROCESSED/$TOTAL_BIRDS] ✅ 完成: $slug"
      echo "1" > "/tmp/${slug}_status.txt"
    else
      echo "[$PROCESSED/$TOTAL_BIRDS] ❌ 失败: $slug (查看日志: /tmp/${slug}_download.log)"
      echo "0" > "/tmp/${slug}_status.txt"
    fi
  ) &
  
  # 控制并发数
  while [ $(jobs -r | wc -l) -ge $PARALLEL ]; do
    sleep 1
  done
  
done < <(python3 - "$BIRDS_FILE" << 'PYTHON_EOF'
import csv
import sys

csv_file = sys.argv[1]
# utf-8-sig：去掉 BOM，避免首行 # 注释无法识别
with open(csv_file, 'r', encoding='utf-8-sig') as f:
    lines = f.readlines()

def _stripped(line):
    return line.strip().lstrip('\ufeff')

# 跳过注释与空行
data_lines = [line for line in lines if _stripped(line) and not _stripped(line).startswith('#')]

# 格式检测：优先看首行数据列数（5 列 = slug + 中文名 + 英文学名 + wiki）
has_chinese = False
if data_lines:
    try:
        ncol = len(next(csv.reader([data_lines[0]])))
        if ncol >= 5:
            has_chinese = True
        elif ncol <= 4:
            has_chinese = False
    except (StopIteration, csv.Error):
        ncol = 0
    # 列数暧昧时再看所有 # 注释里是否声明 chinese_name
    if ncol not in (4, 5):
        for line in lines:
            s = _stripped(line)
            if s.startswith('#') and 'chinese_name' in s.lower():
                has_chinese = True
                break

if data_lines:
    if has_chinese:
        reader = csv.DictReader(data_lines, fieldnames=['slug', 'chinese_name', 'english_name', 'scientific_name', 'wikipedia_page'])
    else:
        reader = csv.DictReader(data_lines, fieldnames=['slug', 'english_name', 'scientific_name', 'wikipedia_page'])

    for row in reader:
        slug = row.get('slug', '').strip().strip('"')
        if not slug or slug == 'slug':
            continue

        en_name = row.get('english_name', '').strip().strip('"')
        chinese_name = row.get('chinese_name', '').strip().strip('"') if has_chinese else ''
        sci_name = row.get('scientific_name', '').strip().strip('"')
        wiki_page = row.get('wikipedia_page', '').strip().strip('"')

        # 使用 | 作为分隔符，避免与字段内容冲突
        # 格式: slug|en_name|chinese_name|sci_name|wiki_page
        print(f"{slug}|{en_name}|{chinese_name}|{sci_name}|{wiki_page}")
PYTHON_EOF
)

# 等待所有任务完成
echo ""
echo "等待所有下载任务完成..."
wait

# 统计结果
for slug_file in /tmp/*_status.txt; do
  if [ -f "$slug_file" ]; then
    status=$(cat "$slug_file")
    if [ "$status" = "1" ]; then
      SUCCESS=$((SUCCESS + 1))
    else
      FAILED=$((FAILED + 1))
    fi
    rm -f "$slug_file"
  fi
done

END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))

echo ""
echo "╔═══════════════════════════════════════════════════════════════╗"
echo "║                      📊 下载完成                               ║"
echo "╚═══════════════════════════════════════════════════════════════╝"
echo ""
echo "统计:"
echo "  - 总数: $TOTAL_BIRDS"
echo "  - 成功: $SUCCESS"
echo "  - 失败: $FAILED"
echo "  - 跳过: $SKIPPED"
echo "  - 耗时: ${DURATION}秒"
echo ""

if [ $FAILED -gt 0 ]; then
  echo "⚠️  部分下载失败，查看日志: /tmp/*_download.log"
fi

echo "下一步："
echo "  1. 上传到 Cloudinary:"
echo "     python3 tools/upload_to_cloudinary.py all"
echo ""
echo "  2. 生成统一 HTML:"
echo "     python3 tools/generate_unified_cloudinary_html.py"
echo ""

exit $([ $FAILED -eq 0 ] && echo 0 || echo 1)

