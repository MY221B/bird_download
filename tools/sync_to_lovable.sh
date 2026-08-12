#!/bin/bash

# 将本地 main 分支的改动同步到 Lovable 的 develop_lovable 分支
# 使用方法：bash tools/sync_to_lovable.sh

set -e  # 遇到错误就退出

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
SUBMODULE_PATH="$PROJECT_ROOT/feather-flash-quiz"
source "$SCRIPT_DIR/git_submodule_utils.sh"

echo "🔄 开始将本地改动同步到 Lovable (develop_lovable)..."
echo ""

require_independent_git_checkout "$SUBMODULE_PATH" "feather-flash-quiz" || exit 1
cd "$SUBMODULE_PATH"

# 保存当前分支
CURRENT_BRANCH=$(git branch --show-current)

# 1. 确保 main 分支是最新的
echo "📥 确保 main 分支是最新的..."
git checkout main

# 检查是否有未提交的改动
if ! git diff-index --quiet HEAD --; then
    echo "⚠️  警告：检测到未提交的改动"
    echo "请先提交改动："
    echo "  git add ."
    echo "  git commit -m 'your message'"
    exit 1
fi

git pull origin main
echo ""

# 2. 推送 main 到远程
echo "📤 推送 main 分支..."
git push origin main
echo ""

# 3. 切换到 develop_lovable 并合并 main
echo "🔀 切换到 develop_lovable 并合并 main 的改动..."
git checkout develop_lovable
git pull origin develop_lovable

# 检查是否有改动需要合并
if git merge-base --is-ancestor main develop_lovable; then
    echo "✅ main 的所有改动已经在 develop_lovable 中，无需合并"
else
    echo "🔀 合并 main 到 develop_lovable..."
    git merge main -m "merge: sync from main branch"
    
    # 4. 推送到 develop_lovable
    echo "📤 推送到 develop_lovable 分支..."
    git push origin develop_lovable
    echo ""
    echo "✅ 同步完成！本地改动已推送到 Lovable 的 develop_lovable 分支"
fi

# 恢复到之前的分支
if [ "$CURRENT_BRANCH" != "develop_lovable" ]; then
    echo ""
    echo "🔙 返回到之前的分支: $CURRENT_BRANCH"
    git checkout "$CURRENT_BRANCH"
fi

echo ""
echo "🎉 完成！Lovable 现在可以看到你的最新改动了"
echo ""
echo "提示：如果主仓库需要更新子模块引用，请运行："
echo "  cd $PROJECT_ROOT"
echo "  git add feather-flash-quiz"
echo "  git commit -m 'chore: update feather-flash-quiz submodule'"
echo "  git push origin main"
