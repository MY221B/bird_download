# 🐦 鸟类记忆卡项目 - AI 助手操作指南

## 📋 任务概述

你好！我需要你帮我处理一批鸟类名单，将它们转化为带有图片的 HTML 展示页面。

**核心任务**：
1. 从提供的鸟类名单中提取中文名和学名
2. 转换成标准 CSV 格式
3. 合并 `all_birds.csv` 信息（优先使用 `all_birds.csv` 中的完整信息）
4. 自动下载不在库中的鸟类图片（从 4 个来源，使用 `all_birds.csv` 中的名称信息）
5. 上传图片到 Cloudinary CDN（优先使用 `all_birds.csv` 构建 `bird_info`）
6. 补全 `all_birds.csv`（新鸟类会自动添加）
7. 更新统一的 HTML 展示页面（支持删除功能）

**重要提示**：
- 请先**完整阅读**项目的 `README.md` 和 `docs/快速指南.md`，理解项目结构和工作流程
- 检查 `images/` 目录，了解已有哪些鸟类，避免重复下载
- 检查 `all_birds.csv`，这是鸟类信息的主数据源
- 所有操作需要验证结果，确保成功后再进行下一步
- **优先使用 `all_birds.csv` 中的信息**，确保数据一致性和准确性

---

## 🎯 详细工作流程

### 步骤 0：环境准备与项目理解（必需）

**0.1 阅读核心文档**
```bash
# 阅读项目说明
cat README.md

# 阅读完整使用指南
cat docs/快速指南.md

# 查看工具目录
ls -la tools/
```

**0.2 检查环境变量**
```bash
# 检查 eBird Token（必需）
echo $EBIRD_TOKEN

# 如果未设置，提醒用户提供
# export EBIRD_TOKEN=your_token_here
```

**0.3 检查已有鸟类**
```bash
# 列出所有已下载的鸟类
ls -d images/*/ | wc -l

# 查看最近添加的鸟类
ls -lt images/ | head -10

# 检查 all_birds.csv（鸟类信息主数据源）
if [ -f "all_birds.csv" ]; then
    echo "📋 all_birds.csv 存在"
    BIRD_COUNT=$(grep -v "^#" all_birds.csv | wc -l | tr -d ' ')
    echo "   包含 $BIRD_COUNT 条鸟类记录"
else
    echo "⚠️  all_birds.csv 不存在，将自动创建"
fi
```

**重要**：如果缺少环境变量或项目结构异常，**立即告知用户**，不要继续执行。

**关于 all_birds.csv**：
- 📋 `all_birds.csv` 是鸟类信息的主数据源，格式：`slug,chinese_name,english_name,scientific_name,wikipedia_page`
- 🔄 整个流程会优先使用 `all_birds.csv` 中的信息，确保数据一致性和准确性
- 🆕 新鸟类会自动添加到 `all_birds.csv` 中，无需手动维护
- 📥 下载时使用 `all_birds.csv` 中的名称信息
- ☁️ 上传时优先使用 `all_birds.csv` 构建 `bird_info`
- 📄 HTML生成时优先从 `all_birds.csv` 读取信息

---

### 步骤 1：提取并转换鸟类名单

**1.1 查找输入文件**
用户通常会提供以下格式之一：
- `@观鸟中心页面复制.txt` - 从中国观鸟记录中心复制的列表
- `@鸟类名单.txt` - 其他格式的鸟类列表
- 直接在对话框中粘贴列表

首先查找文件：
```bash
# 查找可能的输入文件
ls -la | grep -E "鸟|bird|list"

# 如果用户提到文件名，读取内容
cat 观鸟中心页面复制.txt | head -20
```

**1.2 解析鸟类列表**

根据文件格式选择合适的工具：

**格式 A：观鸟记录中心表格格式**（每个鸟类占8行：编号、中文名、英文名、学名、目、科）
```bash
# 示例内容：
# 1
# 4148
# 珠颈斑鸠
# Spotted Dove
# Spilopelia chinensis
# 鸽形目
# 鸠鸽科
# 1 （下一个鸟的开始）

# 使用专门的表格解析工具
python3 tools/parse_birdreport_table.py 观鸟中心页面复制.txt > parsed_birds.txt
```

**格式 B：其他简单格式**（带编号、中文名、学名）
```bash
# 示例内容：
# 39 4770 - 大山雀 Parus minor × 6
# 40 4781 - 云雀 Alauda arvensis × 3

# 使用通用解析工具（支持多种格式）
python3 tools/parse_bird_list.py 鸟类列表.txt > parsed_birds.txt

# 或直接使用（如果格式已经很简单）
cat 鸟类名单.txt > parsed_birds.txt
```

**1.3 转换成 CSV**
```bash
# 转换成标准 CSV 格式
# 这个步骤会自动查询 eBird API 获取英文名
python3 tools/convert_to_csv.py --auto parsed_birds.txt > new_birds.csv 2>&1 | tee convert.log

# 检查转换结果
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "转换结果预览："
cat new_birds.csv
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# 统计数量
BIRD_COUNT=$(grep -v "^#" new_birds.csv | grep -c "^")
echo "✅ 成功转换 $BIRD_COUNT 种鸟类"
```

**重要验证**：
- 确保 CSV 文件格式正确（slug,chinese_name,english_name,scientific_name,wikipedia_page）
- 检查是否有转换失败的鸟类（查看 convert.log）
- 如果有失败，询问用户是否需要手动补充信息

**1.4 合并 all_birds.csv 信息** ⭐ 重要
```bash
# 如果使用 process_new_birds.py，会自动完成这一步
# 如果手动处理，需要先检查 all_birds.csv

if [ -f "all_birds.csv" ]; then
    echo "📋 检查 all_birds.csv..."
    # 脚本会优先使用 all_birds.csv 中的信息
    # 新鸟类会使用临时CSV的信息，并在上传后添加到 all_birds.csv
fi
```

---

### 步骤 2：识别需要下载的鸟类

**2.1 对比已有鸟类**
```bash
# 提取新 CSV 中的 slug
awk -F',' 'NR>1 && !/^#/ {print $1}' new_birds.csv > new_slugs.txt

# 提取已有的 slug
ls -d images/*/ | sed 's|images/||; s|/$||' > existing_slugs.txt

# 找出需要下载的鸟类
comm -23 <(sort new_slugs.txt) <(sort existing_slugs.txt) > birds_to_download.txt

# 显示结果
NEW_COUNT=$(wc -l < birds_to_download.txt | tr -d ' ')
EXISTING_COUNT=$(wc -l < existing_slugs.txt | tr -d ' ')

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📊 下载计划："
echo "  - 已有鸟类：$EXISTING_COUNT 种"
echo "  - 新增鸟类：$NEW_COUNT 种"
echo "  - 总计：$(($EXISTING_COUNT + $NEW_COUNT)) 种"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# 如果有需要下载的，显示列表
if [ $NEW_COUNT -gt 0 ]; then
    echo ""
    echo "需要下载的鸟类："
    cat birds_to_download.txt
fi
```

**2.2 创建下载 CSV**
```bash
# 从 new_birds.csv 中提取需要下载的鸟类
head -1 new_birds.csv > birds_to_download.csv
grep -F -f birds_to_download.txt new_birds.csv >> birds_to_download.csv

echo "✅ 下载清单已创建：birds_to_download.csv"
cat birds_to_download.csv
```

**如果没有新鸟类**：
```bash
if [ $NEW_COUNT -eq 0 ]; then
    echo "✅ 所有鸟类已存在，跳过下载步骤"
    # 直接跳到步骤 4（更新 HTML）
fi
```

---

### 步骤 3：批量下载图片

**3.1 执行批量下载**
```bash
# 设置并行数量（根据鸟类数量调整）
if [ $NEW_COUNT -le 5 ]; then
    PARALLEL=1
elif [ $NEW_COUNT -le 15 ]; then
    PARALLEL=3
else
    PARALLEL=5
fi

echo "开始批量下载（并行数：$PARALLEL）..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# 执行下载
./tools/batch_fetch.sh birds_to_download.csv --parallel $PARALLEL --skip-existing

# 保存退出码
DOWNLOAD_EXIT=$?
```

**3.2 验证下载结果**
```bash
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📊 下载结果验证："
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# 检查每个鸟类的图片数量
while read slug; do
    if [ -d "images/$slug" ]; then
        MAC_COUNT=$(ls images/$slug/macaulay/*.jpg 2>/dev/null | wc -l | tr -d ' ')
        INAT_COUNT=$(ls images/$slug/inaturalist/*.jpg 2>/dev/null | wc -l | tr -d ' ')
        WIKI_COUNT=$(ls images/$slug/wikimedia/*.jpg 2>/dev/null | wc -l | tr -d ' ')
        AVI_COUNT=$(ls images/$slug/avibase/*.jpg 2>/dev/null | wc -l | tr -d ' ')
        TOTAL=$((MAC_COUNT + INAT_COUNT + WIKI_COUNT + AVI_COUNT))
        
        if [ $TOTAL -gt 0 ]; then
            echo "✅ $slug: $TOTAL 张（M:$MAC_COUNT I:$INAT_COUNT W:$WIKI_COUNT A:$AVI_COUNT）"
        else
            echo "⚠️  $slug: 0 张图片（下载可能失败）"
        fi
    else
        echo "❌ $slug: 目录不存在"
    fi
done < birds_to_download.txt

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
```

**3.3 处理下载失败**
```bash
# 如果下载失败，提供诊断信息
if [ $DOWNLOAD_EXIT -ne 0 ]; then
    echo "⚠️  批量下载遇到问题，请检查日志"
    echo ""
    echo "常见问题："
    echo "  1. EBIRD_TOKEN 未设置或已过期"
    echo "  2. 网络连接问题"
    echo "  3. 某些物种在数据库中不存在"
    echo ""
    echo "建议："
    echo "  - 查看 images/*/download.log 了解详情"
    echo "  - 使用 --skip-existing 重新运行可以续传"
fi
```

---

### 步骤 4：上传图片到 Cloudinary

**4.1 检查 Cloudinary 配置**
```bash
# 检查 cloudinary_uploads 目录
if [ ! -d "cloudinary_uploads" ]; then
    mkdir -p cloudinary_uploads
    echo "✅ 创建 cloudinary_uploads 目录"
fi

# 检查已上传的鸟类
if [ -f "cloudinary_uploads/all_birds.json" ]; then
    UPLOADED_COUNT=$(python3 -c "import json; print(len(json.load(open('cloudinary_uploads/all_birds.json'))))" 2>/dev/null || echo "0")
    echo "📊 已上传 $UPLOADED_COUNT 种鸟类到 Cloudinary"
fi
```

**4.2 执行上传**
```bash
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "☁️  上传图片到 Cloudinary..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# 上传所有鸟类（包括新下载的）
# 注意：upload_to_cloudinary.py 会自动从 all_birds.csv 读取信息构建 bird_info
python3 tools/upload_to_cloudinary.py all 2>&1 | tee upload.log

UPLOAD_EXIT=$?

if [ $UPLOAD_EXIT -eq 0 ]; then
    echo "✅ Cloudinary 上传完成"
    echo "   注意：已优先使用 all_birds.csv 中的信息构建 bird_info"
else
    echo "⚠️  Cloudinary 上传遇到问题"
    echo "提示：部分图片可能已上传，脚本会自动跳过重复上传"
fi
```

**关于 bird_info**：
- 📋 上传时会优先从 `all_birds.csv` 读取信息构建 `bird_info`
- ✅ 确保 `bird_info` 包含完整的中文名、英文名、学名
- 🔄 如果 `all_birds.csv` 中没有，使用临时CSV或JSON文件中的信息

**4.3 验证上传结果**
```bash
# 检查上传后的状态
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "验证上传结果："

FINAL_UPLOADED=$(python3 -c "import json; print(len(json.load(open('cloudinary_uploads/all_birds.json'))))" 2>/dev/null || echo "0")
echo "  - Cloudinary 上已有：$FINAL_UPLOADED 种鸟类"

# 检查 JSON 文件大小
if [ -f "cloudinary_uploads/all_birds.json" ]; then
    JSON_SIZE=$(wc -c < cloudinary_uploads/all_birds.json)
    echo "  - 元数据文件大小：$(($JSON_SIZE / 1024)) KB"
fi

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
```

---

### 步骤 5：补全 all_birds.csv

**5.1 从JSON文件提取鸟类信息**
```bash
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📋 补全 all_birds.csv..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# 从JSON文件提取鸟类信息并添加到all_birds.csv
python3 tools/add_missing_birds_to_csv.py 2>&1 | tee csv_update.log

echo "✅ all_birds.csv 已更新"
echo "   新鸟类信息已自动添加"
```

**重要说明**：
- 📋 `all_birds.csv` 是鸟类信息的主数据源
- 🆕 新鸟类会自动添加到 `all_birds.csv` 中
- 🔄 确保所有鸟类信息都记录在 `all_birds.csv` 中，便于后续使用

---

### 步骤 6：更新 HTML 展示页面

**6.1 生成HTML展示页面**
```bash
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🎨 生成 HTML 展示页面..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# 生成支持删除功能的HTML展示页面
# 注意：update_gallery_from_cloudinary.py 会自动从 all_birds.csv 读取信息
python3 tools/update_gallery_from_cloudinary.py 2>&1 | tee html_generation.log

HTML_EXIT=$?

if [ $HTML_EXIT -eq 0 ] && [ -f "examples/gallery_all_cloudinary.html" ]; then
    HTML_SIZE=$(wc -c < examples/gallery_all_cloudinary.html)
    echo "✅ HTML 生成成功"
    echo "  - 文件：examples/gallery_all_cloudinary.html"
    echo "  - 大小：$(($HTML_SIZE / 1024)) KB"
    
    # 统计包含的鸟类数量
    BIRD_IN_HTML=$(grep -c 'class="nav-item"' examples/gallery_all_cloudinary.html || echo "0")
    echo "  - 包含鸟类：$BIRD_IN_HTML 种"
    echo "  - 已优先使用 all_birds.csv 中的信息"
else
    echo "❌ HTML 生成失败"
    echo "请检查 cloudinary_uploads/ 目录中的JSON文件"
fi

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
```

**6.2 预览结果**
```bash
# 在浏览器中打开（macOS）
if command -v open &> /dev/null; then
    echo ""
    echo "🌐 在浏览器中打开预览..."
    open examples/gallery_all_cloudinary.html
fi

# 提供访问路径
echo ""
echo "📄 文件位置："
echo "  $(pwd)/examples/gallery_all_cloudinary.html"
```

---

### 步骤 7：生成任务总结

```bash
echo ""
echo "╔═══════════════════════════════════════════════════════════════╗"
echo "║                    ✅ 任务完成总结                             ║"
echo "╚═══════════════════════════════════════════════════════════════╝"
echo ""
echo "📊 处理统计："
echo "  - 输入鸟类：$BIRD_COUNT 种"
echo "  - 新增鸟类：$NEW_COUNT 种"
echo "  - 已有鸟类：$EXISTING_COUNT 种"
echo "  - 总计鸟类：$FINAL_UPLOADED 种"
echo ""
echo "📁 生成文件："
echo "  ✅ new_birds.csv - 转换后的 CSV"
echo "  ✅ birds_to_download.csv - 下载清单"
echo "  ✅ examples/gallery_all_cloudinary.html - 展示页面"
echo ""
echo "🔗 Cloudinary 状态："
echo "  ✅ 已上传：$FINAL_UPLOADED 种鸟类"
echo "  📦 元数据：cloudinary_uploads/all_birds.json"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
```

---

## 🔍 关键检查点

在执行过程中，请在以下关键点进行验证：

### ✅ 检查点 1：CSV 转换后
- CSV 格式是否正确？
- 所有鸟类都有英文名和学名吗？
- 是否有警告或错误信息？

### ✅ 检查点 2：图片下载后
- 每个鸟类至少有 1 张图片吗？
- 是否有完全失败的鸟类？
- 日志中是否有异常错误？

### ✅ 检查点 3：Cloudinary 上传后
- `cloudinary_uploads/all_birds.json` 是否更新？
- 上传的鸟类数量是否正确？
- 是否有上传失败的记录？

### ✅ 检查点 4：HTML 生成后
- HTML 文件是否存在且大小合理？
- 新鸟类是否出现在页面中？
- 图片链接是否有效？

---

## ⚠️ 常见问题处理

### 问题 1：EBIRD_TOKEN 未设置
**症状**：转换 CSV 时提示无法查询英文名
**解决**：
```bash
export EBIRD_TOKEN=your_token_here
# 或询问用户提供 token
```

### 问题 2：某些鸟类下载失败
**症状**：某个鸟类目录为空或图片很少
**原因**：
- 学名在数据库中不存在
- 网络问题
- API 限流

**解决**：
- 检查 `images/<slug>/download.log`
- 使用正确的学名重试
- 单独下载失败的鸟类

### 问题 3：HTML 中缺少新鸟类
**症状**：新鸟类图片已上传，但 HTML 中看不到
**原因**：`generate_unified_cloudinary_html.py` 中的 `bird_info_lookup` 未更新
**解决**：
- 手动添加新鸟类信息到 `bird_info_lookup`
- 重新运行 `generate_unified_cloudinary_html.py`

### 问题 4：Cloudinary 上传失败
**症状**：上传脚本报错
**原因**：
- Cloudinary 配置缺失（`.env` 文件）
- 网络问题
- 存储空间不足

**解决**：
- 检查 `.env` 文件是否存在
- 验证 Cloudinary API 凭证
- 查看 Cloudinary 控制台

---

## 📝 工作流程简化版（备忘）

```bash
# 快速版本（适用于熟悉流程后）

# 1. 转换
python3 tools/parse_bird_list.py 观鸟中心页面复制.txt | \
  python3 tools/convert_to_csv.py --auto - > new_birds.csv

# 2. 下载（跳过已有）
./tools/batch_fetch.sh new_birds.csv --parallel 3 --skip-existing

# 3. 上传
python3 tools/upload_to_cloudinary.py all

# 4. 更新 HTML（需要先更新 bird_info_lookup）
python3 tools/generate_unified_cloudinary_html.py

# 5. 预览
open examples/gallery_all_cloudinary.html
```

---

## 🎯 输出规范

请在任务完成后提供以下信息：

1. **任务摘要**：
   - 解析到了多少种鸟类
   - 新增了多少种鸟类的照片，每种鸟类成功获取到几张照片
   - 未获取到照片的鸟类名单和个数
   - 最终总共有多少种鸟类

2. **文件清单**：
   - 生成的 CSV 文件
   - 下载的图片统计
   - 更新的 HTML 文件

3. **验证结果**：
   - 每个步骤的成功/失败状态
   - 任何需要用户注意的问题

4. **预览链接**：
   - HTML 文件的本地路径
   - 如何在浏览器中查看

---

## 💡 提示

- **耐心等待**：批量下载可能需要几分钟，属于正常情况
- **保存日志**：所有命令输出都应该记录，便于调试
- **增量操作**：使用 `--skip-existing` 可以安全地重复运行
- **验证优先**：每一步完成后都要验证结果
- **用户沟通**：遇到问题时及时询问用户，不要猜测

---

## 📚 参考文档

- `README.md` - 项目概览
- `docs/快速指南.md` - 完整使用指南
- `examples/birds_template.csv` - CSV 格式示例
- `examples/birdreport_example.txt` - 输入格式示例

---

**最后提醒**：
- 始终先阅读文档，理解项目结构
- 每一步都要验证结果
- 出错时查看日志文件
- 不确定时询问用户

祝你顺利完成任务！🎉

