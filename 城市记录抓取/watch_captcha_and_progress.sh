#!/usr/bin/env bash
# Watch captcha_pending.jpg and print ALERT; agent conversation should answer.
set -euo pipefail
cd "$(dirname "$0")"
while true; do
  if [[ -f captcha_pending.jpg && ! -f captcha_answer.txt ]]; then
    if [[ ! -f captcha_agent_alerted ]]; then
      touch captcha_agent_alerted
      echo "ALERT captcha needs agent vision $(date '+%F %T')"
    fi
  else
    rm -f captcha_agent_alerted 2>/dev/null || true
  fi
  # also surface scrape progress lightly
  if [[ -f 上海市_20250801-20251231_checkpoint.json ]]; then
    python3 -c "import json;d=json.load(open('上海市_20250801-20251231_checkpoint.json'));print('PROG shanghai',d.get('next_page'),'/',d.get('expected_pages'), flush=True)" 2>/dev/null || true
  fi
  sleep 5
done
