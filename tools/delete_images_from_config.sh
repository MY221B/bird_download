#!/bin/bash

# 自动化图片删除脚本
# 用法: ./delete_images_from_config.sh [配置文件路径]
# 
# 功能：从 Cloudinary、本地文件、JSON 引用和 HTML 画廊中删除配置文件中列出的所有图片
# 并自动提交到 Git
#
# 默认配置文件: config/需要删除图片名单

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

# 🔄 开始前：从 Lovable 同步最新改动
echo -e "${BLUE}🔄 从 Lovable 同步最新改动...${NC}"
if bash "${REPO_ROOT}/tools/sync_from_lovable.sh"; then
  echo -e "${GREEN}✅ Lovable 同步完成${NC}"
else
  echo -e "${YELLOW}⚠️  Lovable 同步失败，继续执行...${NC}"
fi
echo ""

# 配置文件路径（默认或从参数获取）
CONFIG_FILE="${1:-config/需要删除图片名单}"

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
read -p "是否继续？[y/N] " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo -e "${RED}❌ 操作已取消${NC}"
    exit 0
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
    echo -e "${YELLOW}⚠️  没有文件更改，跳过提交${NC}"
    exit 0
fi

# 统计更改
MODIFIED_COUNT=$(git status --porcelain | wc -l | tr -d ' ')
echo -e "📊 修改了 ${MODIFIED_COUNT} 个文件"

# 添加所有更改
git add -A

# 生成提交信息
COMMIT_MSG="批量删除${IMAGE_COUNT}张图片 - 使用自动化脚本"
echo -e "📝 提交信息: ${COMMIT_MSG}"

# 提交
git commit -m "${COMMIT_MSG}"

# 推送
CURRENT_BRANCH="$(git rev-parse --abbrev-ref HEAD)"
echo -e "🚀 推送到 origin/${CURRENT_BRANCH}..."
git push origin "${CURRENT_BRANCH}"

echo ""
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}✨ 所有操作完成！${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "${GREEN}✅ 已成功删除 ${IMAGE_COUNT} 张图片并推送到 GitHub${NC}"
echo ""

# 返回项目根目录
cd "${REPO_ROOT}"

# 🔄 结束后：同步改动到 Lovable
echo ""
echo -e "${BLUE}🔄 同步改动到 Lovable...${NC}"
if bash "${REPO_ROOT}/tools/sync_to_lovable.sh"; then
  echo -e "${GREEN}✅ 已同步到 Lovable 的 develop_lovable 分支${NC}"
  echo ""
  echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
  echo -e "${GREEN}🎉 全部完成！请到 Lovable 网站 Publish 推送最新更改${NC}"
  echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
else
  echo -e "${RED}❌ 同步到 Lovable 失败${NC}"
  exit 1
fi
