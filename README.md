# 🐦 鸟类图片自动搜索工具

一个基于 API 的鸟类图片搜索与展示工具，整合 Macaulay Library、iNaturalist、Avibase（Flickr 社区）、Wikimedia；可本地托管或使用 Cloudinary CDN 生成在线展示页。

---

## ⚠️ AI 操作注意事项

`**feather-flash-quiz/` 目录没有自己的 `.git` 文件**，它是一个普通目录。

在该目录内执行任何 `git` 命令（如 `git remote set-url`、`git reset`），都会意外操作**父级 `bird_download` 仓库**，可能导致主仓库文件被覆盖。

操作 `feather-flash-quiz` 的 git 时，必须先 `cd` 进入该目录，确认 `.git` 存在后再操作。

**分支规则：**

- 主仓库 `bird_download`：只推送到 `main`，**不需要** `develop_lovable` 分支
- 子仓库 `feather-flash-quiz`：需同时维护 `main` 和 `develop_lovable` 两个分支

---

## ✨ 特性

- 🎯 **100% 准确率**：官方 API + 物种标识符 + 自动验证
- 🌐 **多源整合**：Macaulay、iNaturalist、Wikimedia、Avibase（补充）
- 📝 **署名管理**：自动保存照片署名信息，符合各平台许可要求
- 📱 **展示友好**：生成本地版与 Cloudinary 版 HTML
- ⚡ **高效批量**：支持 CSV 批量下载 + 并行处理
- 🔄 **智能缓存**：自动跳过已下载、eBird taxonomy 月度缓存
- 🛡️ **容错机制**：单个源失败不影响其他源

## 🚀 快速开始

### 方式 1：一键处理新增鸟类（推荐）

**适用于：从中国观鸟记录中心复制鸟类列表**

```bash
# 1. 将观鸟记录中心的页面内容复制到 新增鸟单.txt（CTRL+A复制全页面）

# 2. 设置环境变量
export EBIRD_TOKEN=your_token
#从 config/ebird_token.sh 中获取

# 3. 一键处理（自动完成所有步骤）
python3 tools/process_new_birds.py
```

脚本会自动完成：解析鸟单、合并 all_birds.csv、下载图片、上传 Cloudinary、更新 bird_info、补全 CSV、生成 HTML 页面。

### 方式 2：批量下载（适合已有CSV文件）

```bash
# 1) 准备 CSV 文件
# 方式A：快速转换（从对话框粘贴鸟类列表）
python3 tools/convert_to_csv.py --auto - > my_birds.csv
# 粘贴内容后按 Ctrl+D 结束

# 方式B：手动编辑（参考 examples/birds_template.csv）

# 2) 设置 eBird Token
export EBIRD_TOKEN=your_token
#从 config/ebird_token.sh 中获取

# 3) 批量下载并上传
./tools/batch_fetch.sh my_birds.csv --parallel 3
python3 tools/upload_to_cloudinary.py all
python3 tools/update_gallery_from_cloudinary.py
open examples/gallery_all_cloudinary.html
```

### 方式 3：单个物种下载

```bash
export EBIRD_TOKEN=your_token

# 首次使用 Macaulay 时安装浏览器并建立持久会话
python3 -m pip install -r requirements.txt
python3 -m playwright install chromium
python3 tools/macaulay_browser.py setup

./tools/fetch_four_sources.sh bluetail "Red-flanked Bluetail" "Tarsiger cyanurus"
python3 tools/upload_to_cloudinary.py bluetail
python3 tools/update_gallery_from_cloudinary.py
```

Macaulay 搜索使用 `.browser_profiles/macaulay` 中的持久 Chromium 会话。该目录只存在本机且已被 Git 忽略。查询时会短暂打开一个可见浏览器窗口，让站点正常完成验证。如果日志提示会话失效，重新运行 `python3 tools/macaulay_browser.py setup`。批量下载时，Macaulay 查询会自动串行复用同一会话，其他来源仍可并行处理。会话或网络失败不会清空已有 Macaulay 元数据。

### 方式 4：批量/定时刷新（多地点）

```bash
python3 tools/run_weekly_refresh.py --days 7 --min-species 10
# 可用 --locations 仅跑部分地点
```

脚本会遍历 `config/birdreport_locations.json`，自动抓取最近一周的鸟单、下载缺失图片、上传至 Cloudinary，并把最新 JSON 拷贝到 `feather-flash-quiz/location_birds/<城市>/<地点>/<日期>` 目录，供前端使用。

### 方式 5：美国公园近期鸟种（eBird）

eBird recent observations API 最多支持回看 30 天。William O'Brien State Park 可直接使用热点 `L336470`，或使用地址坐标自动寻找附近热点：

```bash
export EBIRD_TOKEN=your_token
python3 tools/fetch_ebird_recent_birds.py --loc-id L336470 --days 30

# 默认坐标为 16821 O'Brien Trl N, Marine on St Croix, MN 55047
python3 tools/fetch_ebird_recent_birds.py --days 30 --fallback-geo
```

如果公园热点 30 天内没有记录，可改用 `--mode geo --radius-km 10` 查询同一区域附近公开记录，或增大半径（eBird 坐标热点接口上限 50 km）。

## 📚 文档

- 📖 **快速指南**：`docs/快速指南.md` - 完整使用说明
- 📋 **CSV 模板**：`examples/birds_template.csv` - 批量下载模板
- 🗺️ **鸟单自动抓取指南**：`docs/鸟单自动抓取指南.md` - 参数/配置化抓取教程
- 📍 **地点配置说明**：`docs/地点配置说明.md` - birdreport_locations.json 配置指南
- 🔊 **鸟叫声使用说明**：`docs/鸟叫声使用说明.md` - 鸟叫声下载与集成说明

## 📁 结构

```
小鸟记忆卡/
├── all_birds.csv                    # 鸟类信息总表（包含中文名、英文名、学名）
├── docs/
│   ├── 快速指南.md                  # 完整使用说明
│   └── 署名信息获取测试报告.md      # 署名功能测试报告（新）
├── tools/
│   ├── parse_birdreport_table.py   # 解析观鸟记录表格（推荐）
│   ├── convert_to_csv.py           # 鸟类列表转 CSV
│   ├── batch_fetch.sh              # 批量下载工具
│   ├── fetch_four_sources.sh       # 单物种下载（含署名）
│   ├── download_from_avibase.py    # Avibase 下载（含署名）
│   ├── upload_to_cloudinary.py     # Cloudinary 上传（含署名）
│   ├── process_new_birds.py        # 一键处理新增鸟类（推荐）
│   ├── load_bird_info_from_all_birds_csv.py  # 加载all_birds.csv工具
│   ├── add_missing_birds_to_csv.py # 补全all_birds.csv
│   ├── update_bird_info_in_json.py # 更新JSON文件的bird_info
│   ├── fetch_macaulay_attribution.py  # 补充 Macaulay 署名（新）
│   ├── add_attribution_fields.py   # 为已有数据添加署名字段（新）
│   ├── update_gallery_from_cloudinary.py   # 生成展示页（支持删除功能）
│   ├── delete_cloudinary_by_list.py  # 根据列表删除 Cloudinary 图片
│   ├── cleanup_references_by_list.py  # 从 JSON 文件中移除引用
│   └── cloudinary_cleanup.py       # 清理所有 Cloudinary 图片
├── images/                          # 本地图片
│   └── <bird_slug>/
│       ├── macaulay/
│       ├── inaturalist/
│       ├── wikimedia/
│       ├── avibase/
│       └── download_metadata.json  # 下载元数据（含署名）（新）
├── examples/
│   ├── birds_template.csv          # CSV 模板
│   ├── birdreport_example.txt      # 观鸟记录列表示例
│   └── gallery_all_cloudinary.html # 展示页面
└── cloudinary_uploads/              # 已上传 URL 记录（含署名）
```

## 🔄 核心概念

### all_birds.csv 的作用

`all_birds.csv` 是鸟类信息的主数据源（格式：`slug,chinese_name,english_name,scientific_name,wikipedia_page`），用于：

- 提供准确的鸟类名称信息（优先于临时CSV）
- 避免重复处理和错误信息
- 自动补全新鸟类信息

处理新鸟类时会自动更新 CSV，也可通过 `tools/add_missing_birds_to_csv.py` 手动补全。

## 🔑 方法论

- **标识符优先级**：`Species Code (eBird) > Taxon ID (iNat) > 学名 > 英文名`
- **数据源优先级**：`all_birds.csv > 临时CSV > JSON文件`
- **质量筛选**：Macaulay 按评分降序；iNat 使用 `quality_grade=research`
- **四源顺序**：Macaulay → iNaturalist → Avibase（Flickr） → Wikimedia
- **容错机制**：单个源失败不影响其他源，自动继续
- **智能缓存**：已下载文件自动跳过，eBird taxonomy 月度缓存

## ⚡ 性能

- **25-30 种鸟类批量下载**：~6 分钟（并行 3 个）
- **重复运行**：~30 秒（智能跳过已有文件）
- **成功率**：100%（容错模式，自动处理学名分类变更）

## 📝 署名信息

工具自动管理照片署名信息（摄影师、许可证、引用格式），确保符合各平台许可要求。每张照片包含完整的 attribution 字段。

**署名状态**：Macaulay（✅ 164 张）、iNaturalist（✅ 126 张）、Wikimedia（📝 未来自动保存）、Avibase（⏸️ 字段已预留）

**补充工具**：

```bash
python3 tools/fetch_macaulay_attribution.py  # 补充 Macaulay 署名
python3 tools/add_attribution_fields.py      # 添加署名字段结构
```

详细测试报告：`docs/署名信息获取测试报告.md`

## 🗑️ 删除图片流程

1. **在HTML页面选择图片**：打开 `examples/gallery_all_cloudinary.html`，勾选要删除的图片，点击"复制删除清单"
2. **保存删除列表**：将复制的JSON保存为 `delete_list.json`
3. **执行删除**：

```bash
python3 tools/delete_cloudinary_by_list.py --file delete_list.json      # 从 Cloudinary 删除
python3 tools/cleanup_references_by_list.py --file delete_list.json      # 从 JSON 文件移除引用
python3 tools/update_gallery_from_cloudinary.py                         # 更新 HTML
```

**注意**：删除操作不可逆，请确认后再执行。

## 📄 许可

- 代码与文档：MIT
- 图片版权归原作者与平台所有（遵循各自许可证）
- 使用照片时请遵循 cloudinary_uploads JSON 中的 attribution 信息

最后更新：2025-11-05（v2.3 - all_birds.csv优化流程版）
