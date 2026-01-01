# Cloudinary Uploads 文件夹和 JSON 数据结构说明

## 概述

`cloudinary_uploads` 文件夹包含了所有已上传到 Cloudinary 平台的鸟类照片及其元数据信息。每个鸟类物种对应一个独立的 JSON 文件，文件名格式为：`{bird_species}_cloudinary_urls.json`

## JSON 数据结构

### 顶层结构

每个 JSON 文件是一个对象，包含以下键：

```json
{
  "bird_info": {          // 鸟类基本信息（位于顶部）
    "slug": "{bird_slug}",
    "chinese_name": "{中文名}",
    "english_name": "{English Name}",
    "scientific_name": "{Scientific Name}"
  },
  "macaulay": [...],      // Macaulay Library 来源的照片数组
  "inaturalist": [...],   // iNaturalist 来源的照片数组
  "birdphotos": [...],    // BirdPhotos 来源的照片数组（通常为空）
  "wikimedia": [...],     // Wikimedia Commons 来源的照片数组
  "avibase": [...]        // Avibase 来源的照片数组
}
```

### bird_info 字段说明

`bird_info` 字段包含鸟类的基本信息，用于在 HTML 页面中显示鸟类名称：

| 字段名 | 类型 | 说明 | 示例 |
|--------|------|------|------|
| `slug` | string | 鸟类标识符（小写+下划线） | `"azure_winged_magpie"` |
| `chinese_name` | string | 中文名称 | `"灰喜鹊"` |
| `english_name` | string | 英文名称 | `"Azure-winged Magpie"` |
| `scientific_name` | string | 学名 | `"Cyanopica cyanus"` |

**注意：** `bird_info` 字段是必需的，用于 HTML 页面正确显示鸟类名称。如果缺少此字段，HTML 会显示 slug 或英文名（不正确）。

### 图片对象结构

每个图片对象包含以下字段：

#### 基本信息字段

| 字段名 | 类型 | 说明 | 示例 |
|--------|------|------|------|
| `original_file` | string | 原始文件名 | `"azure_winged_magpie_205853451.jpg"` |
| `url` | string | Cloudinary 完整 URL | `"https://res.cloudinary.com/.../azure_winged_magpie/..."` |
| `public_id` | string | Cloudinary 公共 ID（不含扩展名） | `"bird-gallery/azure_winged_magpie/macaulay/azure_winged_magpie_205853451"` |
| `width` | number | 图片宽度（像素） | `1200` |
| `height` | number | 图片高度（像素） | `768` |
| `format` | string | 图片格式 | `"jpg"` |
| `bytes` | number | 文件大小（字节） | `66582` |

#### 署名信息字段（attribution 对象）

| 字段名 | 类型 | 说明 | 示例 |
|--------|------|------|------|
| `photographer` | string \| null | 摄影师姓名 | `"Purevsuren Tsolmonjav"` 或 `null` |
| `photographer_url` | string \| null | 摄影师主页 URL | `"https://macaulaylibrary.org/asset/205853451"` 或 `null` |
| `license` | string \| null | 许可协议信息 | `"© Cornell Lab of Ornithology (non-commercial use)"` 或 `null` |
| `license_url` | string \| null | 许可协议 URL | `"https://support.ebird.org/..."` 或 `null` |
| `credit_format` | string \| null | 格式化后的署名信息 | `"Bird by Purevsuren Tsolmonjav; Cornell Lab of Ornithology \| Macaulay Library"` 或 `null` |
| `source` | string | 图片来源标识（必填） | `"macaulay"`, `"inaturalist"`, `"wikimedia"`, `"avibase"` |
| `source_id` | string \| null | 来源网站的 ID | `"205853451"` 或 `null` |
| `note` | string \| null | 备注信息 | `"署名信息待补充"` 或 `null` |

### 完整示例

```json
{
  "bird_info": {
    "slug": "azure_winged_magpie",
    "chinese_name": "灰喜鹊",
    "english_name": "Azure-winged Magpie",
    "scientific_name": "Cyanopica cyanus"
  },
  "macaulay": [
    {
      "original_file": "azure_winged_magpie_205853451.jpg",
      "url": "https://res.cloudinary.com/dzor6lhz8/image/upload/v1761717988/bird-gallery/azure_winged_magpie/macaulay/azure_winged_magpie_205853451.jpg",
      "public_id": "bird-gallery/azure_winged_magpie/macaulay/azure_winged_magpie_205853451",
      "width": 1200,
      "height": 768,
      "format": "jpg",
      "bytes": 66582,
      "attribution": {
        "photographer": "Purevsuren Tsolmonjav",
        "photographer_url": "https://macaulaylibrary.org/asset/205853451",
        "license": "© Cornell Lab of Ornithology (non-commercial use)",
        "license_url": "https://support.ebird.org/en/support/solutions/articles/48001064570",
        "credit_format": "Bird by Purevsuren Tsolmonjav; Cornell Lab of Ornithology | Macaulay Library",
        "source": "macaulay",
        "source_id": "205853451",
        "note": null
      }
    }
  ],
  "inaturalist": [
    {
      "original_file": "azure_winged_magpie_1.jpg",
      "url": "https://res.cloudinary.com/dzor6lhz8/image/upload/v1761715955/bird-gallery/azure_winged_magpie/inaturalist/azure_winged_magpie_1.jpg",
      "public_id": "bird-gallery/azure_winged_magpie/inaturalist/azure_winged_magpie_1",
      "width": 1024,
      "height": 768,
      "format": "jpg",
      "bytes": 119705,
      "attribution": {
        "photographer": null,
        "photographer_url": null,
        "license": null,
        "license_url": null,
        "credit_format": null,
        "source": "inaturalist",
        "source_id": null,
        "note": "署名信息待补充"
      }
    }
  ],
  "birdphotos": [],
  "wikimedia": [...],
  "avibase": [...]
}
```

## 数据特点

### 1. 署名信息完整性
- **Macaulay Library**：通常包含完整的署名信息（摄影师、许可协议等）
- **iNaturalist、Wikimedia、Avibase**：大部分图片的署名信息为 `null`，备注字段标注为 `"署名信息待补充"`

### 2. URL 结构
Cloudinary URL 的路径结构遵循以下模式：
```
https://res.cloudinary.com/{cloud_name}/image/upload/{version}/bird-gallery/{bird_species}/{source}/{filename}
```

### 3. Public ID 结构
Public ID 遵循以下模式：
```
bird-gallery/{bird_species}/{source}/{filename_without_extension}
```

### 4. 文件命名规则
- Macaulay: `{bird_species}_{asset_id}.jpg`
- iNaturalist: `{bird_species}_{index}.jpg`
- Wikimedia: `{bird_species}_{index}.jpg`
- Avibase: `avibase_{index}_{flickr_id}_{hash}_b.jpg`

## 使用建议

1. **读取数据**：可以直接读取 JSON 文件，每个文件代表一个鸟类物种的所有照片信息
2. **鸟类信息**：使用 `bird_info` 字段获取鸟类的中文名、英文名、学名等信息，用于页面显示
3. **图片访问**：使用 `url` 字段可以直接访问 Cloudinary 上的图片
4. **署名展示**：使用 `attribution.credit_format` 或自行组合 `attribution` 字段来展示署名信息
5. **过滤空来源**：`birdphotos` 数组通常为空，可以忽略
6. **处理缺失署名**：对于 `attribution.note` 为 `"署名信息待补充"` 的图片，需要后续补充署名信息

## 数据更新

- 新的鸟类物种会添加新的 JSON 文件（包含 `bird_info` 字段）
- 已有物种的 JSON 文件可能会更新：
  - 添加新照片
  - 补充署名信息（`attribution` 字段从 `null` 更新为具体值）
  - 更新 `bird_info` 字段（确保中文名、英文名、学名准确）

