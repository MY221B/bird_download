#!/usr/bin/env python3
"""
根据提供的 public_id 列表删除 Cloudinary 图片。

用法：
  python tools/delete_cloudinary_by_list.py --file delete_list.json

delete_list.json 支持两种结构：
1) { "items": [{"public_id": "bird-gallery/xxx"}, ...] }
2) ["bird-gallery/xxx", "bird-gallery/yyy", ...]

任一资源删除未确认（异常或非 ok/not found）时以非零退出码结束，
避免 delete_images_from_config.sh 在远端失败后继续清本地引用并推送。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Iterable, List, Sequence, Tuple

import cloudinary.uploader

from cloudinary_credentials import ensure_cloudinary_config

# Cloudinary destroy 在资源已不存在时返回 not found；二者均可安全清理本地引用。
SUCCESS_RESULTS = frozenset({"ok", "not found"})

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_FILES = [
    PROJECT_ROOT / "config" / "需要删除图片名单",
    PROJECT_ROOT / "config" / "delete_list.json",
]


def load_public_ids(p: Path) -> List[str]:
    with p.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict) and isinstance(data.get("items"), list):
        return [item["public_id"] for item in data["items"] if item and item.get("public_id")]
    if isinstance(data, list):
        return [x for x in data if isinstance(x, str) and x]
    raise ValueError("无法识别的JSON结构，请参考文件头部注释示例")


def destroy_public_ids(
    public_ids: Sequence[str],
    *,
    resource_type: str = "image",
    destroy=None,
) -> Tuple[List[str], List[Tuple[str, str]]]:
    """删除 public_id 列表。

    Returns:
        (succeeded_ids, failed_pairs) — failed_pairs 为 (public_id, reason)。
    """
    if destroy is None:
        destroy = cloudinary.uploader.destroy

    succeeded: List[str] = []
    failed: List[Tuple[str, str]] = []

    for pid in public_ids:
        try:
            res = destroy(pid, invalidate=True, resource_type=resource_type)
            status = (res or {}).get("result")
            print(f"🗑️  {pid} -> {status}")
            if status in SUCCESS_RESULTS:
                succeeded.append(pid)
            else:
                reason = f"unexpected result: {status!r}"
                print(f"⚠️  删除未确认 {pid}: {reason}")
                failed.append((pid, reason))
        except Exception as exc:
            reason = str(exc) or type(exc).__name__
            print(f"⚠️  删除失败 {pid}: {reason}")
            failed.append((pid, reason))

    return succeeded, failed


def main(argv: Iterable[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", help="包含 public_id 列表的 JSON 文件路径（默认: config/需要删除图片名单）")
    args = ap.parse_args(list(argv) if argv is not None else None)

    if args.file:
        path = Path(args.file)
    else:
        path = next((p for p in DEFAULT_FILES if p.exists()), None)
        if path is None:
            print("用法: python3 tools/delete_cloudinary_by_list.py --file <JSON文件>")
            print("  或 将 public_id 列表写入 config/需要删除图片名单 后直接运行")
            return 1

    if not path.exists():
        print(f"❌ 文件不存在: {path}")
        return 1

    public_ids = load_public_ids(path)
    if not public_ids:
        print("⚠️ 无需删除，列表为空")
        return 0

    ensure_cloudinary_config()
    succeeded, failed = destroy_public_ids(public_ids)

    print(f"✅ Cloudinary 确认删除 {len(succeeded)}/{len(public_ids)} 张图片")
    if failed:
        print(
            f"❌ {len(failed)} 个资源删除未确认，中止后续本地引用清理。"
            " 请修复后重试，避免在远端失败时抹掉 JSON/本地副本。",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
