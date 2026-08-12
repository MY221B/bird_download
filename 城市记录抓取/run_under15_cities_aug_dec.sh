#!/usr/bin/env bash
# Sequentially scrape Aug–Dec 2025 city reports for cities below 15 locations.
# Skips Beijing / Xi'an. Resumes checkpoints. Auto captcha with agent fallback.
set -euo pipefail
cd "$(dirname "$0")"
export PYTHONUNBUFFERED=1

run_one() {
  local label="$1"; shift
  echo "===== START $label $(date '+%F %T') ====="
  python3 fetch_city_reports.py \
    --output-dir . \
    --start 2025-08-01 \
    --end 2025-12-31 \
    --resume \
    --post-process \
    --cleanup-runtime-artifacts \
    --auto-captcha \
    --captcha-reader ocr_then_agent \
    --captcha-agent-wait 300 \
    "$@"
  echo "===== DONE $label $(date '+%F %T') ====="
}

# Shanghai may already be running elsewhere; only run if no live process.
if ! pgrep -f 'fetch_city_reports.py.*上海市' >/dev/null 2>&1; then
  run_one "上海市" --province 上海市
else
  echo "上海市 already running; wait for it to finish..."
  while pgrep -f 'fetch_city_reports.py.*上海市' >/dev/null 2>&1; do
    sleep 10
  done
  echo "上海市 process ended."
fi

run_one "深圳市" --province 广东省 --city 深圳市
run_one "广州市" --province 广东省 --city 广州市
run_one "长沙市" --province 湖南省 --city 长沙市
run_one "桂林市" --province 广西壮族自治区 --city 桂林市
run_one "兰州市" --province 甘肃省 --city 兰州市
run_one "芜湖市" --province 安徽省 --city 芜湖市
run_one "云南省" --province 云南省

echo "ALL CITY SCRAPES COMPLETE $(date '+%F %T')"
