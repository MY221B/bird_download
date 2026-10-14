# 城市报告抓取与处理说明

## 1. 运行方式

在本目录执行：

```bash
python3 fetch_city_reports.py --output-dir .
```

脚本每次启动都会先询问查询条件：

- 开始日期（`YYYY-MM-DD`）
- 结束日期（`YYYY-MM-DD`）
- 省份/直辖市（必填）
- 城市/区县/观鸟点（可选）

如果是非交互运行，需显式传参：

```bash
python3 fetch_city_reports.py \
  --output-dir . \
  --start 2025-03-01 \
  --end 2026-03-01 \
  --province 北京市
```

## 2. 运行流程（已合并）

脚本会自动执行以下步骤：

1. 先请求第一页统计总量并给出预估（总页数、预计纯运行时长、预计验证码次数）。
2. 分页抓取报告（支持断点续传、重试、风控协作）。
3. 抓取完成后自动调用 `build_point_period_stats.py` 生成分时段鸟点排名。

## 3. 验证码交互

触发验证码时会：

- **默认自动识别**：拉取 4 位图形验证码 → OCR（ddddocr，红色数字预处理）→ 提交  
  OCR 失败时回退到 **Agent 看图**：写出 `captcha_pending.jpg`，等待 `captcha_answer.txt`
- 仍失败后再回退人工浏览器验证

相关参数：

- `--auto-captcha / --no-auto-captcha`（默认开启）
- `--auto-captcha-attempts`（默认 `8`）

## 4. 输出文件命名

所有最终结果都在 `data/`，命名格式为：

`完整地点名_起始日期-结束日期_文件类型`

例如（北京市，2025-03-01 到 2026-03-01）：

- `北京市_20250301-20260301_报告索引.csv`
- `北京市_20250301-20260301_报告原始.jsonl`
- `北京市_20250301-20260301_分时段鸟点排名.csv`

## 5. 运行时文件清理

运行过程中会生成：

- `*_checkpoint.json`
- `*_summary.json`
- `logs/*.log`

当整次任务状态为完整完成（`completed`）时，脚本会自动删除以上运行时文件，并删除空 `logs` 目录。

如果任务中断/失败，会保留这些文件用于续跑与排错。

## 6. 常用参数

- `--resume / --no-resume`：是否使用断点续传（默认开启）
- `--max-retries`：单页重试次数（默认 `5`）
- `--blocked-retry-limit`：单页命中风控后提前停止重试阈值（默认 `2`）
- `--min-sleep --max-sleep`：页间随机等待
- `--batch-pages --batch-cooldown-min --batch-cooldown-max`：批量冷却
- `--auto-open-browser / --no-auto-open-browser`：验证码时是否自动打开网页
- `--alert-sound / --no-alert-sound`：验证码时是否播报提示音
- `--captcha-reminder-seconds`：二次提醒等待秒数（默认 `15`）
- `--post-process / --no-post-process`：抓取后是否自动生成分时段鸟点排名（默认开启）
- `--cleanup-runtime-artifacts / --no-cleanup-runtime-artifacts`：成功后是否自动清理运行时文件（默认开启）

## 7. 当前地址字段兼容

2026-10-14 实测，`front/record/activity/search` 返回的公开报告使用 `address` 全地址，例如 `北京市北京市朝阳区奥森北园河东`，不再分别返回 `province_name`、`city_name`、`district_name`、`point_name`。官网也直接将公开报告的 `address` 映射为显示用的 `point_name`。

抓取与排名脚本共用 `config/birdreport_location_map.json`：从已有 10 份报告索引中提取 9,285 个地点和 217 组省、市、区县组合，保留来源文件名和 SHA-256，方便核对与重建。映射只包含地点，不包含用户或报告标识。

解析规则：

1. 原有短地点名及行政区字段优先保留。
2. 新完整地址先精确匹配历史地点，恢复省、市、区县和短地点名。
3. 尚未出现过的鸟点，只拆分已确认的完整行政区前缀，优先使用最长前缀；不进行模糊匹配，不合并“北园”“北园河东”等不同地点。
4. 未知或冲突地址保留完整原文，不用查询条件代替实际位置。未知行政区需补充完整历史记录后重建映射，或在映射文件中添加核实过的完整地点四元组。

CSV 表头保持一致，支持原有断点续传；原始 JSONL 仍保存接口原文。排名生成器也可处理之前将完整地址写入 `point_name` 的 CSV，新旧同一地点统一计算访问人数、访问次数和最高鸟种数。排名按省、市、区县、地点四项分组；同名异地以 `地点名【省/市/区县】` 区分，避免错误合并。鸟点建议脚本识别此标注，生成搜索词时仅使用实际地点名，并将行政区写入对应查询字段。此次已重建现有 10 份排名，报告索引 CSV 和原始 JSONL 未改写。

重建映射与排名：

```bash
python3 tools/generate_birdreport_location_map.py
python3 城市记录抓取/build_point_period_stats.py \
  --input-csv 城市记录抓取/data/北京市_20250301-20260301_报告索引.csv \
  --output-csv 城市记录抓取/data/北京市_20250301-20260301_分时段鸟点排名.csv \
  --place-name 北京市
```

也可向映射生成器传入核实过的历史 CSV 列表，或用排名生成器的 `--location-map` 指定另一份映射。若曾抓取新格式并把地点写成空值，可从原始 JSONL 恢复，或重新抓取后重建排名。
