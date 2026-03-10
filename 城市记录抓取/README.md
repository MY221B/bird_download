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

- 自动打开验证码页面（默认开启）
- 播放提示音并在设定秒数后进行二次提醒（默认 15 秒）
- 停止等待你输入 `y` 后继续重试当前页

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
