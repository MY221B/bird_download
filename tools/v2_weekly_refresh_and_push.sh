#!/usr/bin/env bash
set -euo pipefail

# V2: 三阶段流程 + 抓取重试 + 下载进度流式输出
# 使用 run_weekly_refresh_v2.py 替代 run_weekly_refresh.py

# Allows overriding with REFRESH_DAYS env var (defaults to 7).
REFRESH_DAYS="${REFRESH_DAYS:-7}"
# Optional custom commit message via COMMIT_MSG env var.
COMMIT_MSG="${COMMIT_MSG:-chore: weekly refresh $(date +%Y-%m-%d)}"

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
QUIZ_DIR="${REPO_ROOT}/feather-flash-quiz"
QUIZ_PUSH="未执行"
MAIN_PUSH="未执行"
LOVABLE="未执行"

_wxpusher_notify() {
  local code="$1"
  python3 "${REPO_ROOT}/tools/wxpusher_notify.py" \
    --from-json "${REPO_ROOT}/tmp/weekly_refresh/latest_summary.json" \
    --pipeline-exit "${code}" \
    --quiz-push "${QUIZ_PUSH}" \
    --main-push "${MAIN_PUSH}" \
    --lovable "${LOVABLE}" \
    || echo "⚠️  WxPusher 推送失败（不影响更新结果）"
}
trap '_wxpusher_notify $?' EXIT

cd "${REPO_ROOT}"

# 🔄 开始前：从 Lovable 同步最新改动
echo "🔄 从 Lovable 同步最新改动..."
if bash "${REPO_ROOT}/tools/sync_from_lovable.sh"; then
  echo "✅ Lovable 同步完成"
else
  echo "⚠️  Lovable 同步失败，继续执行..."
fi
echo ""

# Load eBird API Token for bird sounds download
if [[ -f "${REPO_ROOT}/config/ebird_token.sh" ]]; then
  source "${REPO_ROOT}/config/ebird_token.sh"
fi

# 启动前检查密钥（缺失时下载/上传新鸟会失败，避免跑完才发现）
_config_ok=1
if [[ -z "${EBIRD_TOKEN:-}" ]]; then
  echo "⚠️  未配置 EBIRD_TOKEN：无法下载新鸟图片/部分鸟叫声（请复制 config/ebird_token.sh.example → config/ebird_token.sh）"
  _config_ok=0
fi
if ! python3 -c "
import sys
sys.path.insert(0, '${REPO_ROOT}/tools')
from cloudinary_credentials import resolve_cloudinary_credentials
resolve_cloudinary_credentials()
" >/dev/null 2>&1; then
  echo "⚠️  未配置 Cloudinary 凭证：无法上传图片到 CDN（请复制 .cloudinary_secrets.example → .cloudinary_secrets）"
  _config_ok=0
fi
if [[ "${_config_ok}" -eq 0 ]]; then
  echo "   详见 运行说明.md「方案 B」与 docs/快速指南.md"
  echo ""
fi

echo "▶️  Running weekly refresh V2 for the past ${REFRESH_DAYS} days..."
python3 tools/run_weekly_refresh_v2.py --days "${REFRESH_DAYS}"

echo ""
echo "🔎 对新下载的图片做质检、删除未通过，并补足不足 3 张的鸟种..."
PYTHONUNBUFFERED=1 python3 tools/photo_qa_pipeline.py \
  --from-weekly-summary "${REPO_ROOT}/tmp/weekly_refresh/latest_summary.json" \
  --delete --supplement --no-git --no-sync \
  || echo "⚠️  图片质检/补图失败，继续提交已有结果"

cd "${QUIZ_DIR}"

# 在 Cloud Agent 环境中注入 token 到子模块 remote（本地无此环境变量时跳过）
if [[ -n "${FEATHER_FLASH_QUIZ_TOKEN:-}" ]]; then
  git remote set-url origin "https://x-access-token:${FEATHER_FLASH_QUIZ_TOKEN}@github.com/MY221B/feather-flash-quiz.git"
  echo "✅ feather-flash-quiz remote URL 已注入 token"
fi

node scripts/generate-location-birds-manifest.js > /dev/null 2>&1
echo "🔗 刷新懂鸟物种编号对照表..."
if node scripts/generate-dongniao-ids.js; then
  echo "✅ 懂鸟编号对照表已检查"
else
  echo "⚠️  懂鸟编号刷新失败，继续使用现有对照表"
fi
if [[ -z "$(git status --porcelain)" ]]; then
  echo "✅ feather-flash-quiz 无新改动，跳过提交"
  QUIZ_PUSH="无改动跳过"
  MAIN_PUSH="未检查"
  LOVABLE="未执行"
  exit 0
fi

git add -A
if git diff --cached --quiet; then
  echo "✅ feather-flash-quiz 无新改动"
  QUIZ_PUSH="无改动跳过"
  MAIN_PUSH="未检查"
  LOVABLE="未执行"
  exit 0
fi

# 检查 git 用户配置
if ! git config user.name > /dev/null 2>&1 || ! git config user.email > /dev/null 2>&1; then
  echo "⚠️  Git 用户信息未配置，正在检查配置..."
  
  # 尝试从全局配置读取
  GIT_NAME=$(git config --global user.name 2>/dev/null || echo "")
  GIT_EMAIL=$(git config --global user.email 2>/dev/null || echo "")
  
  # 如果全局配置也没有，尝试从本地仓库配置读取
  if [[ -z "$GIT_NAME" ]]; then
    GIT_NAME=$(git config user.name 2>/dev/null || echo "")
  fi
  if [[ -z "$GIT_EMAIL" ]]; then
    GIT_EMAIL=$(git config user.email 2>/dev/null || echo "")
  fi
  
  # 如果还是没有配置，给出提示
  if [[ -z "$GIT_NAME" ]] || [[ -z "$GIT_EMAIL" ]]; then
    echo "❌ Git 用户信息未配置，无法提交代码"
    echo ""
    echo "请运行以下命令配置 Git 用户信息："
    echo "  git config --global user.name \"Your Name\""
    echo "  git config --global user.email \"your.email@example.com\""
    echo ""
    echo "或者仅为当前仓库配置："
    echo "  cd ${QUIZ_DIR}"
    echo "  git config user.name \"Your Name\""
    echo "  git config user.email \"your.email@example.com\""
    exit 1
  fi
  
  # 如果全局有配置但本地没有，设置本地配置
  if [[ -n "$GIT_NAME" ]] && [[ -n "$GIT_EMAIL" ]]; then
    git config user.name "$GIT_NAME" 2>/dev/null || true
    git config user.email "$GIT_EMAIL" 2>/dev/null || true
    echo "✅ 已使用全局 Git 配置：$GIT_NAME <$GIT_EMAIL>"
  fi
fi

git commit --quiet -m "${COMMIT_MSG}"
current_branch="$(git rev-parse --abbrev-ref HEAD)"
if ! git pull --rebase origin "${current_branch}" 2>/dev/null; then
  if git status | grep -q "rebase in progress"; then
    echo "❌ feather-flash-quiz rebase 冲突，请手动解决"
    QUIZ_PUSH="rebase 冲突"
    exit 1
  fi
fi
git push --quiet origin main
git push --quiet origin main:develop_lovable
QUIZ_PUSH="已推送"
echo "✅ feather-flash-quiz 已提交并推送"

# 🔄 推送主仓库改动
cd "${REPO_ROOT}"
echo ""
git add -A
if ! git diff --cached --quiet; then
  CHANGED_FILES=$(git diff --cached --numstat | wc -l | tr -d ' ')
  MAIN_COMMIT_MSG="chore: weekly refresh $(date +%Y-%m-%d) - 更新鸟类数据和子模块引用"
  git commit --quiet -m "${MAIN_COMMIT_MSG}"
  git pull --quiet origin main --no-rebase
  git push --quiet origin main
  MAIN_PUSH="已推送（${CHANGED_FILES} 个文件）"
  echo "✅ 主仓库已提交并推送（${CHANGED_FILES} 个文件）"
else
  MAIN_PUSH="无新改动"
  echo "✅ 主仓库无新改动"
fi

# 🔄 结束后：同步改动到 Lovable
echo ""
echo "🔄 同步改动到 Lovable..."
if bash "${REPO_ROOT}/tools/sync_to_lovable.sh" > /dev/null 2>&1; then
  LOVABLE="已同步"
  echo "✅ 已同步到 Lovable"
else
  LOVABLE="失败"
  echo "⚠️  同步到 Lovable 失败（可运行 tools/sync_to_lovable.sh 排查）"
  exit 1
fi
