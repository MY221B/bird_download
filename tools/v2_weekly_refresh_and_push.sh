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

echo "▶️  Running weekly refresh V2 for the past ${REFRESH_DAYS} days..."
python3 tools/run_weekly_refresh_v2.py --days "${REFRESH_DAYS}"

if [[ ! -e "${QUIZ_DIR}/.git" ]]; then
  echo "❌ feather-flash-quiz 子模块未初始化，无法安全执行子模块 git 操作"
  echo "   请先运行: git submodule update --init feather-flash-quiz"
  exit 1
fi

cd "${QUIZ_DIR}"

QUIZ_REMOTE_URL="https://github.com/MY221B/feather-flash-quiz.git"
QUIZ_ASKPASS_SCRIPT=""

cleanup_quiz_auth() {
  if [[ -n "${QUIZ_ASKPASS_SCRIPT}" && -f "${QUIZ_ASKPASS_SCRIPT}" ]]; then
    rm -f "${QUIZ_ASKPASS_SCRIPT}"
  fi
}

run_quiz_git() {
  if [[ -n "${FEATHER_FLASH_QUIZ_TOKEN:-}" && -n "${QUIZ_ASKPASS_SCRIPT}" ]]; then
    FEATHER_FLASH_QUIZ_TOKEN="${FEATHER_FLASH_QUIZ_TOKEN}" \
      GIT_ASKPASS="${QUIZ_ASKPASS_SCRIPT}" \
      GIT_TERMINAL_PROMPT=0 \
      git -c remote.origin.url="${QUIZ_REMOTE_URL}" \
        -c remote.origin.pushurl="${QUIZ_REMOTE_URL}" "$@"
  else
    git "$@"
  fi
}

# 在 Cloud Agent 环境中使用一次性凭据，不把 token 写入 .git/config
if [[ -n "${FEATHER_FLASH_QUIZ_TOKEN:-}" ]]; then
  QUIZ_ASKPASS_SCRIPT="$(mktemp)"
  cat > "${QUIZ_ASKPASS_SCRIPT}" <<'EOF'
#!/usr/bin/env bash
case "$1" in
  *Username*) printf '%s\n' "x-access-token" ;;
  *) printf '%s\n' "${FEATHER_FLASH_QUIZ_TOKEN}" ;;
esac
EOF
  chmod 700 "${QUIZ_ASKPASS_SCRIPT}"
  trap cleanup_quiz_auth EXIT

  current_origin_url="$(git config --get remote.origin.url 2>/dev/null || true)"
  if [[ "${current_origin_url}" == https://x-access-token:*@github.com/MY221B/feather-flash-quiz.git ]]; then
    git remote set-url origin "${QUIZ_REMOTE_URL}"
    echo "✅ 已清理 feather-flash-quiz remote URL 中的持久化 token"
  fi
  current_push_url="$(git config --get remote.origin.pushurl 2>/dev/null || true)"
  if [[ "${current_push_url}" == https://x-access-token:*@github.com/MY221B/feather-flash-quiz.git ]]; then
    git remote set-url --push origin "${QUIZ_REMOTE_URL}"
    echo "✅ 已清理 feather-flash-quiz push URL 中的持久化 token"
  fi
  echo "✅ feather-flash-quiz 已配置一次性 push token"
fi

node scripts/generate-location-birds-manifest.js > /dev/null 2>&1
if [[ -z "$(git status --porcelain)" ]]; then
  echo "✅ feather-flash-quiz 无新改动，跳过提交"
else
  git add -A
  if git diff --cached --quiet; then
    echo "✅ feather-flash-quiz 无新改动"
  else

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
    if ! run_quiz_git pull --rebase origin "${current_branch}" 2>/dev/null; then
      if git status | grep -q "rebase in progress"; then
        echo "❌ feather-flash-quiz rebase 冲突，请手动解决"
        exit 1
      fi
    fi
    run_quiz_git push --quiet origin main
    run_quiz_git push --quiet origin main:develop_lovable
    echo "✅ feather-flash-quiz 已提交并推送"
  fi
fi

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
  echo "✅ 主仓库已提交并推送（${CHANGED_FILES} 个文件）"
else
  echo "✅ 主仓库无新改动"
fi

# 🔄 结束后：同步改动到 Lovable
echo ""
echo "🔄 同步改动到 Lovable..."
if bash "${REPO_ROOT}/tools/sync_to_lovable.sh" > /dev/null 2>&1; then
  echo "✅ 已同步到 Lovable"
else
  echo "⚠️  同步到 Lovable 失败（可运行 tools/sync_to_lovable.sh 排查）"
  exit 1
fi
