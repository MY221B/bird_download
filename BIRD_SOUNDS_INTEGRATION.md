# 鸟叫声功能集成文档

## 📋 概述

成功实现了从Macaulay Library下载、上传到Cloudinary并集成到项目中的鸟叫声功能。

## ✅ 已完成的工作

### 1. 鸟叫声下载功能
- **文件**: `tools/test_fetch_bird_sounds.py`
- **功能**: 
  - 通过eBird API获取species code
  - 从Macaulay Library搜索音频（按质量排序）
  - 下载最高质量的鸟叫声（MP3格式）
- **使用方法**:
  ```bash
  source config/ebird_token.sh
  python3 tools/test_fetch_bird_sounds.py "English Name" "Scientific Name" slug
  ```
- **示例**:
  ```bash
  python3 tools/test_fetch_bird_sounds.py "Red-flanked Bluetail" "Tarsiger cyanurus" bluetail
  ```

### 2. Cloudinary上传功能
- **文件**: `tools/upload_sounds_to_cloudinary.py`
- **功能**:
  - 上传音频文件到Cloudinary（存储在 `bird-gallery/{slug}/sounds/` 文件夹）
  - 自动更新JSON文件，添加音频信息到 `sounds` 字段
  - 保留元数据（时长、格式、大小等）
  - 从文件名提取Macaulay asset ID并生成署名信息
- **使用方法**:
  ```bash
  python3 tools/upload_sounds_to_cloudinary.py <bird_slug> <sound_file_path>
  ```
- **示例**:
  ```bash
  python3 tools/upload_sounds_to_cloudinary.py bluetail test_sounds/bluetail_134560971.mp3
  ```

### 3. JSON结构更新
- **修改的文件**: 
  - `cloudinary_uploads/{slug}_cloudinary_urls.json` - 添加了 `sounds` 字段
  - `tools/upload_to_cloudinary.py` - 修复了保存逻辑，确保保留 `sounds` 字段

- **新增的JSON结构**:
  ```json
  {
    "bird_info": { ... },
    "macaulay": [ ... ],
    "inaturalist": [ ... ],
    "wikimedia": [ ... ],
    "avibase": [ ... ],
    "sounds": [
      {
        "original_file": "bluetail_134560971.mp3",
        "url": "https://res.cloudinary.com/dzor6lhz8/video/upload/v1764318180/bird-gallery/bluetail/sounds/bluetail_134560971.mp3",
        "public_id": "bird-gallery/bluetail/sounds/bluetail_134560971",
        "duration": 14.472,
        "format": "mp3",
        "bytes": 262028,
        "bit_rate": 144846,
        "audio_codec": "mp3",
        "audio_frequency": 48000,
        "attribution": {
          "recordist": "Unknown",
          "source": "macaulay",
          "source_id": "134560971",
          "asset_url": "https://macaulaylibrary.org/asset/134560971",
          "license": "© Cornell Lab of Ornithology (non-commercial use)",
          "license_url": "https://support.ebird.org/en/support/solutions/articles/48001064570",
          "note": null
        }
      }
    ]
  }
  ```

### 4. HTML展示页面
- **文件**: `examples/bird_sound_demo.html`
- **功能**:
  - 展示鸟类卡片（图片 + 叫声）
  - 自定义音频播放器（带波形进度条）
  - 显示音频元数据和署名信息
  - 响应式设计
- **查看方法**:
  ```bash
  open examples/bird_sound_demo.html
  ```

## 📊 测试和批量下载结果

### 初始测试（3种鸟）
已成功测试了3个鸟类的叫声下载和上传：

| 鸟类 | slug | 时长 | 大小 | 状态 |
|------|------|------|------|------|
| 红胁蓝尾鸲 | bluetail | 14.5秒 | 256KB | ✅ |
| 鹊鸲 | oriental_magpie_robin | 48.7秒 | 699KB | ✅ |
| 麻雀 | eurasian_tree_sparrow | 38.4秒 | 523KB | ✅ |

### 批量下载（新手必看家附近就有）

**完成度**: 16/17 种（94.1%）

成功下载并上传了15种新鸟类的叫声：

| 鸟类 | slug | 时长 | 状态 |
|------|------|------|------|
| 灰喜鹊 | azure_winged_magpie | 13.4秒 | ✅ |
| 夜鹭 | black_crowned_night_heron | 24.7秒 | ✅ |
| 乌鸫 | chinese_blackbird | 201.0秒 | ✅ |
| 白骨顶 | common_coot | 37.8秒 | ✅ |
| 黑水鸡 | common_moorhen | 52.7秒 | ✅ |
| 大斑啄木鸟 | great_spotted_woodpecker | 52.0秒 | ✅ |
| 灰头绿啄木鸟 | grey_faced_woodpecker | 40.4秒 | ✅ |
| 苍鹭 | grey_heron | 25.0秒 | ✅ |
| 大嘴乌鸦 | large_billed_crow | 27.3秒 | ✅ |
| 白头鹎 | light_vented_bulbul | 17.4秒 | ✅ |
| 绿头鸭 | mallard | 56.0秒 | ✅ |
| 鸳鸯 | mandarin_duck | 25.5秒 | ✅ |
| 沼泽山雀 | marsh_tit | 42.1秒 | ✅ |
| 喜鹊 | oriental_magpie | 44.6秒 | ✅ |
| 珠颈斑鸠 | spotted_dove | 13.8秒 | ✅ |

**失败**: 1种
- 星头啄木鸟 (grey_capped_woodpecker) - eBird API无此物种记录

**总计**: 18种鸟类已有叫声（包含测试的3种）

## 🔧 技术要点

### API端点
- **音频搜索**: `https://search.macaulaylibrary.org/api/v1/search?taxonCode={code}&mediaType=a&sort=rating_rank_desc`
  - `mediaType=a` - 音频类型
  - `sort=rating_rank_desc` - 按质量排序
- **音频下载**: `https://cdn.download.ams.birds.cornell.edu/api/v1/asset/{asset_id}/audio`

### Cloudinary配置
- **resource_type**: `video` （音频也使用video类型）
- **存储路径**: `bird-gallery/{slug}/sounds/`
- **URL格式**: `https://res.cloudinary.com/dzor6lhz8/video/upload/v{version}/bird-gallery/{slug}/sounds/{filename}.mp3`

### 兼容性保证
- ✅ 现有脚本不会受影响（使用 `.get()` 方法访问字段）
- ✅ `upload_to_cloudinary.py` 已修复，会保留 `sounds` 字段
- ✅ JSON结构向后兼容

## ✅ 自动化集成

### 集成到Weekly Refresh流程

鸟叫声下载已集成到 `tools/weekly_refresh_and_push.sh` 自动化流程中：

**新增功能**:
1. 自动检查每个鸟类是否已有叫声
2. 对缺少叫声的鸟类，自动下载并上传到Cloudinary
3. 自动更新JSON文件，添加sounds字段
4. 详细的成功/失败日志
5. 在总结中显示声音下载统计

**使用方法**:
```bash
# 正常运行weekly refresh，会自动处理叫声
bash tools/weekly_refresh_and_push.sh

# 或指定特定地点
REFRESH_DAYS=7 bash tools/weekly_refresh_and_push.sh
```

**输出信息**:
- ✅ 成功下载的鸟叫声数量
- ❌ 失败的鸟类及失败原因（如：eBird无记录、Macaulay无音频等）
- 📊 每个地点的声音下载统计

**相关文件**:
- `tools/auto_sounds_refresh.py` - 自动声音检查和下载模块
- `tools/run_weekly_refresh.py` - 已集成声音下载调用

## 🚀 下一步工作

1. ~~**批量下载脚本**~~ ✅ 已完成
   - ~~为项目中所有鸟类批量下载叫声~~ ✅
   - ~~集成到现有的下载流程~~ ✅

2. **Quiz网站集成**
   - 在 `feather-flash-quiz` 中添加音频播放功能
   - 在卡片中显示播放按钮
   - 实现自动播放选项

3. **元数据完善**
   - 获取录音者信息（需要额外API调用）
   - 添加录音地点、日期等详细信息

4. **HTML Gallery更新**
   - 在 `gallery_all_cloudinary.html` 中添加音频播放器
   - 支持批量播放和下载

## 📁 相关文件

```
小鸟记忆卡/
├── tools/
│   ├── test_fetch_bird_sounds.py          # 单个下载测试脚本
│   ├── batch_download_sounds.py           # 批量下载脚本（新增）
│   ├── upload_sounds_to_cloudinary.py     # 单个上传脚本
│   ├── batch_upload_sounds.py             # 批量上传脚本（新增）
│   └── upload_to_cloudinary.py            # 修改：保留sounds字段
├── examples/
│   └── bird_sound_demo.html               # 音频展示页面
├── cloudinary_uploads/
│   ├── *_cloudinary_urls.json             # 18种鸟的JSON已包含sounds字段
│   └── ...
├── feather-flash-quiz/location_birds/
│   └── 新手必看家附近就有/000000/
│       └── *_cloudinary_urls.json         # 16种鸟的JSON已更新sounds字段
├── sounds_download/                       # 批量下载的音频文件
│   ├── *.mp3                              # 15个音频文件（~21MB）
│   └── download_record.json               # 下载记录
└── test_sounds/                           # 测试音频文件
    ├── bluetail_134560971.mp3
    ├── oriental_magpie_robin_203911381.mp3
    └── tree_sparrow_70906781.mp3
```

## 🎵 音频文件在线地址

- **红胁蓝尾鸲**: https://res.cloudinary.com/dzor6lhz8/video/upload/v1764318180/bird-gallery/bluetail/sounds/bluetail_134560971.mp3
- **麻雀**: https://res.cloudinary.com/dzor6lhz8/video/upload/v1764318197/bird-gallery/eurasian_tree_sparrow/sounds/tree_sparrow_70906781.mp3
- **鹊鸲**: https://res.cloudinary.com/dzor6lhz8/video/upload/v1764318191/bird-gallery/oriental_magpie_robin/sounds/oriental_magpie_robin_203911381.mp3

## 📝 注意事项

1. 需要设置 `EBIRD_TOKEN` 环境变量才能下载音频
2. 音频文件较大，建议选择性下载
3. Cloudinary免费账户有存储限制，注意容量管理
4. 音频署名信息需要遵守Cornell Lab的使用条款

## 🔄 批量操作脚本

### 批量下载
```bash
# 1. 准备鸟类列表JSON文件（包含slug, english_name, scientific_name等字段）
# 2. 运行批量下载
source config/ebird_token.sh
python3 tools/batch_download_sounds.py birds_list.json output_dir
```

### 批量上传
```bash
# 使用下载记录文件批量上传并更新JSON
python3 tools/batch_upload_sounds.py sounds_download/download_record.json
```

---

最后更新: 2024-11-28 (批量下载完成)

