#!/usr/bin/env bash
set -euo pipefail

# Allows overriding with REFRESH_DAYS env var (defaults to 7).
REFRESH_DAYS="${REFRESH_DAYS:-7}"
# Optional custom commit message via COMMIT_MSG env var.
COMMIT_MSG="${COMMIT_MSG:-chore: weekly refresh $(date +%Y-%m-%d)}"

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
QUIZ_DIR="${REPO_ROOT}/feather-flash-quiz"

push_main_repo_changes() {
  cd "${REPO_ROOT}"
  echo ""
  echo "📦 检查主仓库改动..."
  if [[ -n "$(git status --porcelain)" ]]; then
    echo "🗂️  发现主仓库有改动，准备提交和推送..."

    # 添加所有改动（包括子模块引用更新）
    git add -A

    if ! git diff --cached --quiet; then
      # 统计改动
      CHANGED_FILES=$(git diff --cached --numstat | wc -l | tr -d ' ')
      echo "📊 将提交 ${CHANGED_FILES} 个文件的改动"

      # 提交主仓库改动
      MAIN_COMMIT_MSG="chore: weekly refresh $(date +%Y-%m-%d) - 更新鸟类数据和子模块引用"
      echo "📝 提交主仓库: ${MAIN_COMMIT_MSG}"
      git commit --quiet -m "${MAIN_COMMIT_MSG}"
      echo "$(git diff HEAD~1 --shortstat)"

      # 拉取远程 main 最新改动后再推送
      echo "🔄 拉取远程 main 最新改动..."
      git pull origin main --no-rebase
      echo "🚀 推送主仓库到 main..."
      git push --quiet origin main
      echo "✨ 主仓库推送成功（main）"
    else
      echo "✅ 主仓库无新改动需要提交"
    fi
  else
    echo "✅ 主仓库工作区干净，无需提交"
  fi
}

sync_to_lovable() {
  echo ""
  echo "🔄 同步改动到 Lovable..."
  if bash "${REPO_ROOT}/tools/sync_to_lovable.sh"; then
    echo "✅ 已同步到 Lovable 的 develop_lovable 分支"
  else
    echo "⚠️  同步到 Lovable 失败"
    exit 1
  fi
}

finish_main_repo_and_lovable() {
  push_main_repo_changes
  sync_to_lovable
}

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

echo "▶️  Running weekly refresh for the past ${REFRESH_DAYS} days..."
python3 tools/run_weekly_refresh.py --days "${REFRESH_DAYS}"

echo "🔄 更新 location_birds 路径清单 (manifest)..."
cd "${QUIZ_DIR}"
node scripts/generate-location-birds-manifest.js
if [[ -z "$(git status --porcelain)" ]]; then
  echo "✅ feather-flash-quiz has no changes; skipping commit."
  finish_main_repo_and_lovable
  exit 0
fi

echo "🗂️  Staging changes under feather-flash-quiz..."
git add -A
if git diff --cached --quiet; then
  echo "⚠️  Nothing new to commit after staging."
  finish_main_repo_and_lovable
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

echo "📝 Committing with message: ${COMMIT_MSG}"
git commit --quiet -m "${COMMIT_MSG}"
echo "$(git diff HEAD~1 --shortstat)"

current_branch="$(git rev-parse --abbrev-ref HEAD)"

echo "🔄 Pulling latest changes from origin/${current_branch}..."
if git pull --rebase origin "${current_branch}" 2>&1; then
  echo "✅ Successfully pulled and rebased"
else
  echo "⚠️  Pull failed or has conflicts. Checking status..."
  if git status | grep -q "rebase in progress"; then
    echo "❌ Rebase conflicts detected. Please resolve manually:"
    echo "   cd ${QUIZ_DIR}"
    echo "   git status"
    echo "   # Resolve conflicts, then:"
    echo "   git rebase --continue"
    exit 1
  fi
fi

echo "🚀 Pushing feather-flash-quiz to origin/main..."
git push --quiet origin main
echo "🚀 Pushing feather-flash-quiz to origin/develop_lovable..."
git push --quiet origin main:develop_lovable
echo "✨ feather-flash-quiz pushed successfully (main + develop_lovable)."

finish_main_repo_and_lovable
