#!/usr/bin/env python3
"""通过 WxPusher 发送微信提醒。发送接口对齐 guild_task_bot.WxPusher.send。"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path

import requests

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
WXPUSHER_API = "https://wxpusher.zjiecode.com/api"
DEFAULT_SUMMARY_PATH = PROJECT_ROOT / "tmp" / "weekly_refresh" / "latest_summary.json"
LOCAL_CONFIG_PATH = PROJECT_ROOT / "config" / "wxpusher.json"
DEFAULT_GUILD_CONFIG = PROJECT_ROOT.parent / "公会任务指派" / "config.json"
MAX_LIST_ITEMS = 12


def _split_csv(raw: str) -> list[str]:
    return [part.strip() for part in raw.split(",") if part.strip()]


def _read_wxpusher_file(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    wxcfg = data.get("wxpusher", data) if isinstance(data, dict) else {}
    token = str(wxcfg.get("app_token") or "").strip()
    if not token:
        return {}
    return {
        "app_token": token,
        "uids": list(wxcfg.get("uids") or []),
        "topic_ids": list(wxcfg.get("topic_ids") or []),
        "_source": str(path),
    }


def load_wxpusher_config() -> dict:
    """读取 token / uids。优先环境变量，其次本仓库配置，最后复用 guild_task_bot 的 config.json。"""
    cfg: dict = {}
    for path in (
        Path(os.environ["WXPUSHER_CONFIG"]) if os.environ.get("WXPUSHER_CONFIG") else None,
        LOCAL_CONFIG_PATH,
        Path(os.environ["GUILD_TASK_BOT_CONFIG"]) if os.environ.get("GUILD_TASK_BOT_CONFIG") else None,
        DEFAULT_GUILD_CONFIG,
    ):
        if path is None or not path.is_file():
            continue
        cfg = _read_wxpusher_file(path)
        if cfg:
            break

    env_token = os.environ.get("WXPUSHER_APP_TOKEN", "").strip()
    env_uids = _split_csv(os.environ.get("WXPUSHER_UIDS", ""))
    env_topics = [int(x) for x in _split_csv(os.environ.get("WXPUSHER_TOPIC_IDS", "")) if x.isdigit()]
    if env_token:
        cfg["app_token"] = env_token
        cfg["_source"] = "环境变量"
    if env_uids:
        cfg["uids"] = env_uids
    if env_topics:
        cfg["topic_ids"] = env_topics
    return cfg


class WxPusher:
    """与 guild_task_bot.WxPusher.send 相同的发送方式。"""

    def __init__(self, cfg: dict | None = None):
        self.cfg = cfg if cfg is not None else load_wxpusher_config()
        self.token = self.cfg.get("app_token", "")

    @property
    def enabled(self) -> bool:
        return bool(self.token)

    def _post(self, path: str, payload: dict) -> dict:
        payload = dict(payload, appToken=self.token)
        response = requests.post(WXPUSHER_API + path, json=payload, timeout=15)
        response.raise_for_status()
        return response.json()

    def send(self, content: str, summary: str, uids=None, topic_ids=None) -> bool:
        uids = list(uids if uids is not None else self.cfg.get("uids") or [])
        topic_ids = list(topic_ids if topic_ids is not None else self.cfg.get("topic_ids") or [])
        if not self.enabled or not (uids or topic_ids):
            return False
        try:
            res = self._post("/send/message", {
                "content": content,
                "summary": summary[:99],
                "contentType": 1,
                "uids": uids,
                "topicIds": topic_ids,
            })
            if not res.get("success"):
                print(f"⚠️  WxPusher 发送失败: {str(res)[:200]}")
            return bool(res.get("success"))
        except Exception as exc:
            print(f"⚠️  WxPusher 发送异常: {exc}")
            return False


def _fmt_list(items, empty="无") -> str:
    values = [str(item) for item in items if item]
    if not values:
        return empty
    if len(values) <= MAX_LIST_ITEMS:
        return "、".join(values)
    shown = "、".join(values[:MAX_LIST_ITEMS])
    return f"{shown} 等共 {len(values)} 项"


def build_weekly_message(
    summary: dict | None,
    pipeline_exit: int,
    quiz_push: str,
    main_push: str,
    lovable: str,
) -> tuple[str, str]:
    today = (summary or {}).get("date") or date.today().isoformat()
    ok = pipeline_exit == 0
    title = f"小鸟记忆卡周更新{'完成' if ok else '失败'} {today[5:]}"

    lines = [f"小鸟记忆卡 · 周更新{'完成' if ok else '失败'}", f"日期：{today}"]
    if summary:
        days = summary.get("days")
        updated = summary.get("updated_count", 0)
        total = summary.get("total_locations", 0)
        failed_locs = [
            loc.get("location")
            for loc in summary.get("locations") or []
            if not str(loc.get("status") or "").startswith("已更新")
        ]
        loc_line = f"地点：已更新 {updated}/{total}"
        if failed_locs:
            loc_line += f"，未成功 {_fmt_list(failed_locs)}"
        lines.append(f"数据刷新：{'成功' if summary.get('ok') else '有失败'}（最近 {days} 天）")
        lines.append(loc_line)

        new_birds = summary.get("new_birds") or []
        missing_local = summary.get("missing_local") or []
        missing_json = summary.get("missing_json") or []
        if new_birds:
            lines.append(
                f"新鸟：{len(new_birds)} 种（下载 {summary.get('downloaded_count', 0)}，"
                f"上传 {summary.get('uploaded_count', 0)}）"
            )
            lines.append(f"  {_fmt_list(new_birds)}")
        else:
            lines.append("新鸟：无")
        if missing_local:
            lines.append(f"仍缺图：{_fmt_list(missing_local)}")
        if missing_json:
            lines.append(f"缺 JSON：{_fmt_list(missing_json)}")
        photo_qa = summary.get("photo_qa") or {}
        if photo_qa:
            deleted = photo_qa.get("deleted", 0)
            checked = photo_qa.get("checked", 0)
            if photo_qa.get("skipped"):
                lines.append("图片质检：本周无新图，已跳过")
            else:
                lines.append(f"图片质检：检查 {checked} 张，删除未通过 {deleted} 张")
            still_short = photo_qa.get("still_short") or []
            if still_short:
                labels = []
                for item in still_short:
                    if isinstance(item, dict):
                        labels.append(
                            f"{item.get('chinese') or item.get('slug')}({item.get('count', 0)}张)"
                        )
                    else:
                        labels.append(str(item))
                lines.append(f"补图后仍不足 3 张：{_fmt_list(labels)}")
        sounds_success = summary.get("sounds_success") or 0
        sounds_failed = summary.get("sounds_failed") or 0
        if sounds_success or sounds_failed:
            lines.append(f"鸟叫声：成功 {sounds_success} / 失败 {sounds_failed}")
        extended = summary.get("extended_range") or []
        if extended:
            lines.append(f"扩展 30 天才抓到：{_fmt_list(extended)}")
    elif pipeline_exit != 0:
        lines.append(f"数据刷新异常退出（exit {pipeline_exit}），未生成摘要。请查看终端日志。")
    else:
        lines.append("数据刷新完成，但没有摘要文件。")

    if quiz_push or main_push or lovable:
        lines.append("")
        lines.append(f"子模块推送：{quiz_push or '未执行'}")
        lines.append(f"主仓库推送：{main_push or '未执行'}")
        lines.append(f"Lovable 同步：{lovable or '未执行'}")

    if ok and summary and (summary.get("new_birds") or summary.get("missing_local")):
        lines.extend([
            "",
            "请手动检查：",
            "1. 新上传的鸟叫声质量",
        ])
        still_short = (summary.get("photo_qa") or {}).get("still_short") or []
        if still_short:
            lines.append("2. 补图后仍不足 3 张的鸟种（见上方名单）")
    elif not ok:
        lines.extend(["", "请查看终端日志后重跑：bash tools/v2_weekly_refresh_and_push.sh"])

    return "\n".join(lines), title


def parse_args():
    parser = argparse.ArgumentParser(description="通过 WxPusher 发送微信提醒")
    parser.add_argument("--test", action="store_true", help="发送一条测试消息")
    parser.add_argument("--from-json", type=Path, default=None, help="周更新摘要 JSON")
    parser.add_argument("--pipeline-exit", type=int, default=0)
    parser.add_argument("--quiz-push", default="")
    parser.add_argument("--main-push", default="")
    parser.add_argument("--lovable", default="")
    parser.add_argument("--content", default="")
    parser.add_argument("--summary", default="")
    return parser.parse_args()


def main() -> int:
    if os.environ.get("WXPUSHER_SKIP", "").strip() in {"1", "true", "yes"}:
        print("ℹ️  已设置 WXPUSHER_SKIP，跳过微信推送")
        return 0

    args = parse_args()
    wx = WxPusher()
    if not wx.enabled:
        print("⚠️  未找到 WxPusher app_token，跳过推送")
        print("   可设置 WXPUSHER_APP_TOKEN，或复制 config/wxpusher.json.example → config/wxpusher.json")
        print(f"   也可沿用 guild_task_bot：{DEFAULT_GUILD_CONFIG}")
        return 0
    if not (wx.cfg.get("uids") or wx.cfg.get("topic_ids")):
        print("⚠️  未配置 WxPusher uids / topic_ids，跳过推送")
        return 0

    if args.test:
        content = f"小鸟记忆卡 WxPusher 测试\n日期：{date.today().isoformat()}\n配置来源：{wx.cfg.get('_source', '环境变量')}"
        summary = "小鸟记忆卡推送测试"
    elif args.content:
        content = args.content
        summary = args.summary or content.split("\n", 1)[0][:99]
    else:
        summary_path = args.from_json or DEFAULT_SUMMARY_PATH
        data = None
        if summary_path.is_file():
            try:
                data = json.loads(summary_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                print(f"⚠️  无法读取摘要 {summary_path}: {exc}")
        content, summary = build_weekly_message(
            data,
            args.pipeline_exit,
            args.quiz_push,
            args.main_push,
            args.lovable,
        )

    if wx.send(content, summary):
        print("✅ 已通过 WxPusher 发送微信提醒")
        return 0
    print("⚠️  WxPusher 未发送成功")
    return 1


if __name__ == "__main__":
    sys.exit(main())
