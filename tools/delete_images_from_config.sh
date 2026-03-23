#!/bin/bash

# 自动化图片删除脚本
# 用法: ./delete_images_from_config.sh [配置文件路径] [--yes|-y]
#
# 功能：从 Cloudinary、本地文件、JSON 引用和 HTML 画廊中删除配置文件中列出的所有图片
# 并自动提交到 Git
#
# Cloudinary 与上传脚本一致：使用仓库根目录 .cloudinary_secrets（CLOUD_NAME / API_KEY / API_SECRET），
# 或环境变量 CLOUDINARY_CLOUD_NAME、CLOUDINARY_API_KEY、CLOUDINARY_API_SECRET。
# 详见 tools/cloudinary_credentials.py
#
# 默认配置文件: config/需要删除图片名单
# 参数:
#   --yes, -y: 自动确认，跳过交互式确认

set -e  # 遇到错误立即退出

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 获取项目根目录
REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"

# Cloudinary：与周更上传、delete_cloudinary_by_list.py 相同凭证源
check_cloudinary_credentials() {
    python3 -c "
import sys
sys.path.insert(0, '${REPO_ROOT}/tools')
from cloudinary_credentials import ensure_cloudinary_config
print(ensure_cloudinary_config())
"
}

# 解析参数
CONFIG_FILE="config/需要删除图片名单"
AUTO_YES=0

for arg in "$@"; do
    case $arg in
        --yes|-y)
            AUTO_YES=1
            shift
            ;;
        *)
            CONFIG_FILE="$arg"
            shift
            ;;
    esac
done

# 🔄 开始前：从 Lovable 同步最新改动
echo -e "${BLUE}🔄 从 Lovable 同步最新改动...${NC}"
if bash "${REPO_ROOT}/tools/sync_from_lovable.sh"; then
  echo -e "${GREEN}✅ Lovable 同步完成${NC}"
else
  echo -e "${YELLOW}⚠️  Lovable 同步失败，继续执行...${NC}"
fi
echo ""

echo -e "${BLUE}☁️  检查 Cloudinary 凭证（.cloudinary_secrets 或 CLOUDINARY_* 环境变量）...${NC}"
if ! GALLERY_CLOUD="$(check_cloudinary_credentials)"; then
    echo -e "${RED}❌ 未找到有效 Cloudinary 凭证。${NC}"
    echo "  请在仓库根目录创建 .cloudinary_secrets（含 CLOUD_NAME、API_KEY、API_SECRET），"
    echo "  或导出 CLOUDINARY_CLOUD_NAME、CLOUDINARY_API_KEY、CLOUDINARY_API_SECRET。"
    exit 1
fi
echo -e "${GREEN}✅ 将使用 Cloudinary cloud: ${GALLERY_CLOUD}${NC}"
echo ""

# 检查配置文件是否存在
if [[ ! -f "${CONFIG_FILE}" ]]; then
    echo -e "${RED}❌ 错误：配置文件不存在: ${CONFIG_FILE}${NC}"
    echo "请确保配置文件存在，或指定正确的路径"
    exit 1
fi

# 显示配置文件信息
echo -e "${BLUE}📋 读取配置文件: ${CONFIG_FILE}${NC}"
IMAGE_COUNT=$(python3 -c "import json; data=json.load(open('${CONFIG_FILE}')); print(data.get('count', len(data.get('items', []))))")
echo -e "${YELLOW}🔢 待删除图片数量: ${IMAGE_COUNT}${NC}"

# 确认删除
echo ""
echo -e "${YELLOW}⚠️  即将执行以下操作：${NC}"
echo "  1. 从 Cloudinary 删除 ${IMAGE_COUNT} 张图片"
echo "  2. 从 JSON 文件清理引用"
echo "  3. 删除本地图片文件"
echo "  4. 重新生成 HTML 画廊"
echo "  5. 提交并推送到 GitHub"
echo ""

if [[ $AUTO_YES -eq 0 ]]; then
    read -p "是否继续？[y/N] " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo -e "${RED}❌ 操作已取消${NC}"
        exit 0
    fi
else
    echo -e "${GREEN}✅ 自动确认模式，继续执行...${NC}"
fi

echo ""
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}开始删除流程...${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# 步骤 1: 从 Cloudinary 删除
echo -e "${BLUE}[1/5]${NC} 从 Cloudinary 删除图片..."
python3 tools/delete_cloudinary_by_list.py --file "${CONFIG_FILE}"
echo -e "${GREEN}✅ Cloudinary 删除完成${NC}"
echo ""

# 步骤 2: 清理 JSON 引用
echo -e "${BLUE}[2/5]${NC} 清理 JSON 文件引用..."
python3 tools/cleanup_references_by_list.py --file "${CONFIG_FILE}"
echo -e "${GREEN}✅ JSON 引用清理完成${NC}"
echo ""

# 步骤 3: 删除本地文件
echo -e "${BLUE}[3/5]${NC} 删除本地图片文件..."
python3 tools/delete_local_images_by_list.py "${CONFIG_FILE}"
echo -e "${GREEN}✅ 本地文件删除完成${NC}"
echo ""

# 步骤 4: 重新生成 HTML 画廊
echo -e "${BLUE}[4/5]${NC} 重新生成 HTML 画廊..."
python3 tools/update_gallery_from_cloudinary.py
echo -e "${GREEN}✅ HTML 画廊重新生成完成${NC}"
echo ""

# 步骤 5: Git 提交并推送
echo -e "${BLUE}[5/5]${NC} 提交并推送到 GitHub..."

QUIZ_DIR="${REPO_ROOT}/feather-flash-quiz"
cd "${QUIZ_DIR}"

# 检查是否有更改
if [[ -z "$(git status --porcelain)" ]]; then
    echo -e "${YELLOW}⚠️  子模块没有文件更改，跳过子模块提交${NC}"
else
    # 统计更改
    MODIFIED_COUNT=$(git status --porcelain | wc -l | tr -d ' ')
    echo -e "📊 子模块修改了 ${MODIFIED_COUNT} 个文件"

    # 添加所有更改
    git add -A

    # 生成提交信息
    COMMIT_MSG="批量删除${IMAGE_COUNT}张图片 - 使用自动化脚本"
    echo -e "📝 提交信息: ${COMMIT_MSG}"

    # 提交
    git commit -m "${COMMIT_MSG}"

    # 推送到 main 分支
    echo -e "🚀 推送子模块到 origin/main..."
    git checkout main 2>/dev/null || git checkout -b main
    echo -e "🔄 拉取远程 main 最新改动..."
    git pull origin main --no-rebase
    git push origin main

    # 同时推送到 develop_lovable 分支
    echo -e "🚀 推送子模块到 origin/develop_lovable..."
    git push origin main:develop_lovable
    
    echo -e "${GREEN}✅ 子模块已推送到 main 和 develop_lovable 分支${NC}"
fi

echo ""

# 返回主仓库
cd "${REPO_ROOT}"

# 检查主仓库是否有任何改动
if [[ -n "$(git status --porcelain)" ]]; then
    echo -e "${BLUE}📦 提交主仓库的改动...${NC}"
    
    # 显示改动统计
    MAIN_MODIFIED_COUNT=$(git status --porcelain | wc -l | tr -d ' ')
    echo -e "📊 主仓库修改了 ${MAIN_MODIFIED_COUNT} 个文件/目录"
    
    # 添加所有改动（包括子模块引用和其他文件）
    git add -A
    
    # 生成提交信息
    if [[ -n "$(git status --porcelain feather-flash-quiz)" ]]; then
        MAIN_COMMIT_MSG="chore: 更新子模块引用和相关文件 - 批量删除${IMAGE_COUNT}张图片"
    else
        MAIN_COMMIT_MSG="chore: 批量删除${IMAGE_COUNT}张图片相关改动"
    fi
    echo -e "📝 提交信息: ${MAIN_COMMIT_MSG}"
    
    # 提交
    git commit -m "${MAIN_COMMIT_MSG}"
    
    # 推送到 main 分支（主仓库只推送到 main）
    echo -e "🚀 推送主仓库到 origin/main..."
    git checkout main 2>/dev/null || git checkout -b main
    echo -e "🔄 拉取远程 main 最新改动..."
    git pull origin main --no-rebase
    git push origin main
    
    echo -e "${GREEN}✅ 主仓库已推送到 main 分支${NC}"
else
    echo -e "${YELLOW}⚠️  主仓库没有改动，跳过提交${NC}"
fi

echo ""
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}✨ 所有操作完成！${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "${GREEN}✅ 已成功删除 ${IMAGE_COUNT} 张图片${NC}"
echo -e "${BLUE}📦 子模块推送到: main + develop_lovable${NC}"
echo -e "${BLUE}📦 主仓库推送到: main${NC}"
echo ""
