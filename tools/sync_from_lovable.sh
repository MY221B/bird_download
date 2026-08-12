#!/bin/bash

# 从 Lovable 的 develop_lovable 分支同步改动到 main
# 使用方法：bash tools/sync_from_lovable.sh

set -e  # 遇到错误就退出

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
SUBMODULE_PATH="$PROJECT_ROOT/feather-flash-quiz"
PUSH_REMOTE="origin"
if [[ -n "${FEATHER_FLASH_QUIZ_TOKEN:-}" ]]; then
    PUSH_REMOTE="https://x-access-token:${FEATHER_FLASH_QUIZ_TOKEN}@github.com/MY221B/feather-flash-quiz.git"
    echo "✅ feather-flash-quiz push token 已可用于本次推送（不会写入 remote URL）"
fi

echo "🔄 开始从 Lovable (develop_lovable) 同步改动..."
echo ""

if [[ ! -e "$SUBMODULE_PATH/.git" ]]; then
    cd "$PROJECT_ROOT"
    git submodule update --init --recursive feather-flash-quiz
fi

cd "$SUBMODULE_PATH"

# 保存当前分支
CURRENT_BRANCH=$(git branch --show-current)

# 1. 拉取 develop_lovable 的改动
echo "📥 拉取 develop_lovable 分支的最新改动..."
git checkout develop_lovable
git pull origin develop_lovable
echo ""

# 2. 切换到 main 并合并
echo "🔀 切换到 main 分支并合并改动..."
git checkout main
git pull origin main

# 检查是否有改动需要合并
if git merge-base --is-ancestor develop_lovable main; then
    echo "✅ develop_lovable 的所有改动已经在 main 中，无需合并"
else
    echo "🔀 合并 develop_lovable 到 main..."
    git merge develop_lovable -m "merge: sync from Lovable develop_lovable branch"
    
    # 3. 推送到 main
    echo "📤 推送到 main 分支..."
    git push "$PUSH_REMOTE" main
    echo ""
    echo "✅ 同步完成！Lovable 的改动已合并到 main"
fi

# 恢复到之前的分支（如果不是 main）
if [ -n "$CURRENT_BRANCH" ] && [ "$CURRENT_BRANCH" != "main" ]; then
    echo ""
    echo "🔙 返回到之前的分支: $CURRENT_BRANCH"
    git checkout "$CURRENT_BRANCH"
elif [ -z "$CURRENT_BRANCH" ]; then
    echo ""
    echo "🔙 初始状态为 detached HEAD，保留在 main 分支"
fi

echo ""
echo "🎉 完成！现在可以开始在 main 分支上工作了"
echo ""
echo "提示：如果主仓库需要更新子模块引用，请运行："
echo "  cd $PROJECT_ROOT"
echo "  git add feather-flash-quiz"
echo "  git commit -m 'chore: update feather-flash-quiz submodule'"
echo "  git push origin main"
