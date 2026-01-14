# query_level 查询级别使用说明

## 概述

`query_level` 是 `birdreport_locations.json` 配置文件中的一个可选字段，用于指定数据查询的地理范围级别。

## 支持的查询级别

### 1. `"point"` - 地点级别（默认）

查询特定地点的观测数据。

**配置示例：**
```json
{
  "id": "aosen_north",
  "name": "奥森公园",
  "province": "北京市",
  "city": "",
  "district": "",
  "mode": 0,
  "outside_type": 0,
  "default_days": 7,
  "query_level": "point",
  "point_aliases": [
    "奥森北园",
    "奥森",
    "奥森南园",
    "奥林匹克森林公园北园"
  ]
}
```

**特点：**
- 使用 `point_aliases` 数组中的每个别名查询
- 会遍历所有别名并合并去重结果
- 适用于查询具体观鸟点的数据

### 2. `"district"` - 区县级别

查询整个区县范围内所有地点的观测数据。

**单个区县配置示例：**
```json
{
  "id": "haidian_qu",
  "name": "海淀区",
  "province": "北京市",
  "city": "北京市",
  "district": "海淀区",
  "mode": 0,
  "outside_type": 0,
  "default_days": 7,
  "query_level": "district",
  "point_aliases": []
}
```

**多个区县配置示例：**
```json
{
  "id": "guilin_hexin_chengqu",
  "name": "桂林核心城区",
  "province": "广西壮族自治区",
  "city": "桂林市",
  "district": "",
  "mode": 0,
  "outside_type": 0,
  "default_days": 7,
  "query_level": "district",
  "districts": [
    "象山区",
    "七星区",
    "阳朔县"
  ],
  "point_aliases": []
}
```

**特点：**
- 忽略 `point_aliases`，不查询具体地点名称
- **单区县模式**：使用 `district` 字段查询单个区县
- **多区县模式**：使用 `districts` 数组查询多个区县，系统会自动遍历并合并结果
- 使用 `province`、`city`、`district(s)` 字段进行区县级别查询
- 获取该区县内所有观测点的数据

### 3. `"city"` - 城市级别

查询整个城市范围内所有地点的观测数据。

**配置示例：**
```json
{
  "id": "guilin_shi",
  "name": "桂林市",
  "province": "广西壮族自治区",
  "city": "桂林市",
  "district": "",
  "mode": 0,
  "outside_type": 0,
  "default_days": 7,
  "query_level": "city",
  "point_aliases": []
}
```

**特点：**
- 忽略 `point_aliases` 和 `district`
- 使用 `province`、`city` 字段进行城市级别查询
- 获取该城市内所有观测点的数据

### 4. `"province"` - 省级别

查询整个省份范围内所有地点的观测数据。

**配置示例：**
```json
{
  "id": "guangxi",
  "name": "广西壮族自治区",
  "province": "广西壮族自治区",
  "city": "",
  "district": "",
  "mode": 0,
  "outside_type": 0,
  "default_days": 7,
  "query_level": "province",
  "point_aliases": []
}
```

**特点：**
- 忽略 `point_aliases`、`district`、`city`
- 只使用 `province` 字段进行省级别查询
- 获取该省份内所有观测点的数据

## 使用方法

### 命令行使用

```bash
# 查询桂林市整个城市的数据
python3 tools/fetch_from_birdreport.py \
  --location-config config/birdreport_locations.json \
  --location guilin_shi \
  --days 7

# 使用周刷新脚本
python3 tools/run_weekly_refresh.py \
  --days 7 \
  --locations guilin_shi
```

### 输出示例

```
🌍 处理地点: 桂林市 (guilin_shi)
📍 查询级别: 城市级别
🔐 自定义查询1: 调用 API 抓取...
✅ 自定义查询1: 返回 73 条记录
```

## 字段清空规则

不同查询级别会自动清空相应的字段以确保正确的查询范围：

| 查询级别 | pointname | district | city | province |
|---------|-----------|----------|------|----------|
| point   | ✓ 使用    | ✓ 使用   | ✓ 使用 | ✓ 使用    |
| district| ✗ 清空    | ✓ 使用   | ✓ 使用 | ✓ 使用    |
| city    | ✗ 清空    | ✗ 清空   | ✓ 使用 | ✓ 使用    |
| province| ✗ 清空    | ✗ 清空   | ✗ 清空 | ✓ 使用    |

## 配置字段说明

### 必需字段
- `province`：省份名称
- `city`：城市名称（某些情况可为空）
- `query_level`：查询级别（point/district/city/province）

### 可选字段
- `district`：单个区县名称（当 `query_level` 为 "district" 且不使用 `districts` 数组时）
- `districts`：多个区县名称数组（当 `query_level` 为 "district" 且需要查询多个区县时）
- `point_aliases`：地点别名数组（当 `query_level` 为 "point" 时使用）

### 字段优先级
- 当 `query_level` 为 "district" 时：
  - 如果设置了 `districts` 数组，则遍历数组中的每个区县
  - 如果没有 `districts` 数组，则使用 `district` 字段
- 当 `query_level` 为 "point" 时，必须设置 `point_aliases` 数组

## 注意事项

1. **数据量**：级别越高，返回的数据量可能越大，查询时间也会相应增加
2. **point_aliases**：当使用 `city`、`district`、`province` 级别时，`point_aliases` 数组可以留空 `[]`
3. **默认值**：如果不指定 `query_level`，默认使用 `"point"` 级别
4. **时间范围**：建议配合 `default_days` 或命令行 `--days` 参数控制查询的时间范围，避免数据过大
5. **多区县查询**：使用 `districts` 数组时，系统会自动为每个区县发起单独的查询，然后合并去重结果

## 实际案例对比

### 案例 1：桂林市数据查询

**使用地点级别（之前）：**
- 配置：`point_aliases: ["桂林市", "桂林"]`
- 查询方式：查询地点名称包含"桂林市"或"桂林"的观测记录
- 结果：返回 17 条记录（仅包含地点名称为"桂林"的观测点）

**使用城市级别（现在）：**
- 配置：`query_level: "city", point_aliases: []`
- 查询方式：查询桂林市行政范围内所有观测点的记录
- 结果：返回 73 条记录（包含桂林市所有观测点）

### 案例 2：桂林核心城区多区县查询

**使用地点级别（之前）：**
- 配置：`point_aliases: ["核心城区", "象山区", "阳朔县", "七星区"]`
- 查询方式：查询地点名称包含这些关键词的观测记录
- 问题：只能查到地点名称匹配的观测点，遗漏很多数据

**使用多区县级别（现在）：**
- 配置：
  ```json
  {
    "query_level": "district",
    "districts": ["象山区", "七星区", "阳朔县"]
  }
  ```
- 查询方式：分别查询象山区、七星区、阳朔县三个区县的所有观测点
- 查询过程：
  - 象山区：17 条记录
  - 七星区：11 条记录
  - 阳朔县：3 条记录
- 结果：总共 31 条记录，去重后 28 种鸟类（包含三个区县的所有观测点）

## 总结

`query_level` 功能让你可以灵活控制数据查询的地理范围，从具体的观鸟点到整个省份，满足不同场景的需求。对于想要获取某个城市或区域全部观测数据的情况，使用相应的查询级别会比手动维护所有地点别名更加简单高效。
