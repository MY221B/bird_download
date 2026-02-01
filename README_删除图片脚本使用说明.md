# 自动化删除图片脚本使用说明

## 📋 概述

这是一个自动化脚本，可以批量删除图片并自动完成所有相关操作，包括：
- 从 Cloudinary 云端删除
- 清理 JSON 文件引用
- 删除本地文件
- 重新生成 HTML 画廊
- 自动提交并推送到 GitHub

## 🚀 快速开始

### 1. 准备删除列表

编辑配置文件 `config/需要删除图片名单`，格式如下：

```json
{
  "count": 3,
  "items": [
    {
      "public_id": "bird-gallery/鸟种名/来源/图片名"
    },
    {
      "public_id": "bird-gallery/另一只鸟/来源/图片名"
    }
  ]
}
```

**提示：** 可以直接从 `examples/gallery_all_cloudinary.html` 中复制图片信息

### 2. 运行脚本

```bash
# 使用默认配置文件
bash tools/delete_images_from_config.sh

# 或指定其他配置文件
bash tools/delete_images_from_config.sh 自定义配置文件.json
```

### 3. 确认删除

脚本会显示待删除图片数量，输入 `y` 确认后自动执行所有操作。

## 📝 完整示例

### 示例1：删除几张不合适的图片

1. 在浏览器打开 `examples/gallery_all_cloudinary.html`
2. 找到需要删除的图片，点击复制按钮
3. 将复制的内容粘贴到 `config/需要删除图片名单`
4. 运行脚本：

```bash
cd /Users/my/Desktop/Code/小鸟记忆卡
bash tools/delete_images_from_config.sh
```

5. 确认删除信息，输入 `y`
6. 等待脚本自动完成所有操作

### 示例2：大批量删除（254张图片）

实际执行过的案例：

```bash
# 配置文件已包含254张图片信息
bash tools/delete_images_from_config.sh config/需要删除图片名单

# 输出示例：
# 📋 读取配置文件: config/需要删除图片名单
# 🔢 待删除图片数量: 254
# 
# ⚠️  即将执行以下操作：
#   1. 从 Cloudinary 删除 254 张图片
#   2. 从 JSON 文件清理引用
#   3. 删除本地图片文件
#   4. 重新生成 HTML 画廊
#   5. 提交并推送到 GitHub
# 
# 是否继续？[y/N] y
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
   - 自动添加所有更改
   - 生成提交信息
   - 推送到 GitHub main 分支

## ⚙️ 配置说明

### 默认配置文件位置

```
config/需要删除图片名单
```

### 自定义配置文件

可以创建多个配置文件用于不同的删除任务：

```bash
# 例如：只删除某个地区的图片
bash tools/delete_images_from_config.sh config/删除云南地区图片.json

# 或者：删除某个鸟种的图片
bash tools/delete_images_from_config.sh config/删除特定鸟种.json
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
- ✅ 累计删除：292张图片

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
