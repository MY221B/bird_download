# 自动化删除图片脚本使用说明

## ⚡ TL;DR（只需3步）

1. 打开 `examples/gallery_all_cloudinary.html`，选择要删除的图片
2. 把删除列表复制粘贴到 `config/需要删除图片名单`
3. 运行 `bash tools/delete_images_from_config.sh --yes`

**就这么简单！** 脚本会自动完成所有操作并推送到 GitHub。

---

## 📋 概述

这是一个自动化脚本，可以批量删除图片并自动完成所有相关操作，包括：
- 从 Cloudinary 云端删除
- 清理 JSON 文件引用
- 删除本地文件
- 重新生成 HTML 画廊
- 自动提交并推送到 GitHub（子模块推送到 main + develop_lovable，主仓库推送到 main）

## 🚀 快速开始（详细步骤）

### 1️⃣ 打开画廊选择要删除的图片

在浏览器中打开 `examples/gallery_all_cloudinary.html`，浏览并选择需要删除的图片，点击复制按钮获取图片信息。

### 2️⃣ 粘贴到删除名单

将复制的图片信息粘贴到 `config/需要删除图片名单` 文件中。

### 3️⃣ 运行脚本

```bash
bash tools/delete_images_from_config.sh --yes
```

**就这么简单！** 脚本会自动完成从 Cloudinary 删除、清理引用、删除本地文件、更新画廊、提交并推送到 GitHub 的所有操作。

## 📝 使用示例

### 示例：删除不合适的图片

```bash
# 步骤1：打开画廊 HTML 文件，选择要删除的图片
open examples/gallery_all_cloudinary.html

# 步骤2：复制图片信息，粘贴到配置文件
# （在编辑器中打开 config/需要删除图片名单，粘贴）

# 步骤3：运行脚本
bash tools/delete_images_from_config.sh --yes
```

### 执行过程

脚本会自动执行以下操作：

```
🔄 从 Lovable 同步最新改动...
✅ Lovable 同步完成

📋 读取配置文件: config/需要删除图片名单
🔢 待删除图片数量: 188

⚠️  即将执行以下操作：
  1. 从 Cloudinary 删除 188 张图片
  2. 从 JSON 文件清理引用
  3. 删除本地图片文件
  4. 重新生成 HTML 画廊
  5. 提交并推送到 GitHub

✅ 自动确认模式，继续执行...

[1/5] 从 Cloudinary 删除图片...
🗑️  bird-gallery/xxx -> ok
✅ 完成，尝试删除 188/188 张图片

[2/5] 清理 JSON 文件引用...
✂️  移除引用...
✅ 引用清理完成

[3/5] 删除本地图片文件...
🗑️  删除本地文件...
✅ 本地文件删除完成

[4/5] 重新生成 HTML 画廊...
✅ HTML 画廊重新生成完成

[5/5] 提交并推送到 GitHub...
🚀 推送子模块到 origin/main...
🚀 推送子模块到 origin/develop_lovable...
✅ 子模块已推送到 main 和 develop_lovable 分支
📦 更新主仓库...
🚀 推送主仓库到 origin/main...
✅ 主仓库已推送到 main 分支

✨ 所有操作完成！
✅ 已成功删除 188 张图片
📦 子模块推送到: main + develop_lovable
📦 主仓库推送到: main
```

## 🔧 脚本功能详解

### 自动化步骤

1. **Cloudinary 删除**
   - 调用 `delete_cloudinary_by_list.py`
   - 从云端永久删除图片
   - 显示每张图片的删除状态

2. **JSON 引用清理**
   - 调用 `cleanup_references_by_list.py`
   - 清理 `cloudinary_uploads/` 目录中的引用
   - 清理 `feather-flash-quiz/location_birds/` 目录中的引用

3. **本地文件删除**
   - 调用 `delete_local_images_by_list.py`
   - 删除 `images/` 目录下的图片文件

4. **HTML 画廊更新**
   - 调用 `update_gallery_from_cloudinary.py`
   - 重新生成 `examples/gallery_all_cloudinary.html`

5. **Git 提交推送**
   - 子模块（feather-flash-quiz）：推送到 main 和 develop_lovable 分支
   - 主仓库（小鸟记忆卡）：推送到 main 分支
   - 自动添加所有更改并生成提交信息

## ⚙️ 配置说明

### 命令参数

```bash
# 自动确认模式（推荐）
bash tools/delete_images_from_config.sh --yes
# 或使用短参数
bash tools/delete_images_from_config.sh -y

# 交互式确认模式
bash tools/delete_images_from_config.sh
# 会提示输入 y/N 确认

# 指定自定义配置文件
bash tools/delete_images_from_config.sh 配置文件路径 --yes
```

### 默认配置文件位置

```
config/需要删除图片名单
```

### 自定义配置文件

可以创建多个配置文件用于不同的删除任务：

```bash
# 例如：只删除某个地区的图片
bash tools/delete_images_from_config.sh config/删除云南地区图片.json --yes

# 或者：删除某个鸟种的图片
bash tools/delete_images_from_config.sh config/删除特定鸟种.json --yes
```

## ⚠️ 注意事项

1. **不可逆操作**
   - 从 Cloudinary 删除的图片无法恢复
   - 建议先备份重要图片

2. **确认信息**
   - 脚本会在删除前显示数量
   - 仔细检查后再确认

3. **网络要求**
   - 需要稳定的网络连接
   - Cloudinary API 调用需要网络
   - GitHub 推送需要网络

4. **权限要求**
   - 需要 Cloudinary API 密钥配置正确
   - 需要 Git push 权限

## 🐛 故障排查

### 问题1：Cloudinary 删除失败

```bash
# 检查环境变量是否配置
echo $CLOUDINARY_CLOUD_NAME
echo $CLOUDINARY_API_KEY

# 或检查 .env 文件
cat .env
```

### 问题2：Git 推送失败

```bash
# 检查 Git 配置
git config --list | grep user

# 手动推送
cd feather-flash-quiz
git push origin main
```

### 问题3：脚本权限问题

```bash
# 添加执行权限
chmod +x tools/delete_images_from_config.sh
```

## 📊 实际使用数据

已成功执行的删除任务：
- ✅ 第1次：38张图片（15个鸟种）
- ✅ 第2次：254张图片（多个地区）
- ✅ 第3次：188张图片（脚本优化后测试）
- ✅ 第4次：45张图片
- ✅ 累计删除：525+ 张图片

**脚本稳定性**：✅ 已验证大批量删除（188张）和多次连续删除的稳定性

## 🔗 相关文件

- 脚本文件：`tools/delete_images_from_config.sh`
- 配置文件：`config/需要删除图片名单`
- Python工具：
  - `tools/delete_cloudinary_by_list.py`
  - `tools/cleanup_references_by_list.py`
  - `tools/delete_local_images_by_list.py`
  - `tools/update_gallery_from_cloudinary.py`

## 📖 更多信息

详见项目根目录的 `运行说明.md` 文件第5节。
