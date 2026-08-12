#!/usr/bin/env python3
"""
删除 cloudinary_uploads/*.json 中记录的所有 Cloudinary 资源，并删除对应 JSON 文件。

仅在该 JSON 内全部资源删除均已确认（ok / not found）后才删除记录文件，
避免远端失败时丢掉唯一索引。sounds 使用 resource_type=video。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

import cloudinary.uploader

from cloudinary_credentials import ensure_cloudinary_config

SUCCESS_RESULTS = frozenset({"ok", "not found"})


def resource_type_for_source(source: str) -> str:
    """Cloudinary 将音频归类为 video。"""
    if source == "sounds":
        return "video"
    return "image"


def destroy_from_json(
    json_path: Path,
    *,
    destroy=None,
) -> Tuple[int, List[Tuple[str, str]]]:
    """尝试删除 JSON 中记录的全部资源。

    Returns:
        (confirmed_count, failures) — failures 为 (public_id, reason)。
    """
    if destroy is None:
        destroy = cloudinary.uploader.destroy

    with open(json_path, "r", encoding="utf-8") as f:
        data: Dict[str, Any] = json.load(f)

    confirmed = 0
    failures: List[Tuple[str, str]] = []

    for source, images in (data or {}).items():
        if source == "bird_info" or not isinstance(images, list):
            continue
        resource_type = resource_type_for_source(source)
        for img in images or []:
            if not isinstance(img, dict):
                continue
            public_id = img.get("public_id")
            if not public_id:
                continue
            try:
                res = destroy(
                    public_id, invalidate=True, resource_type=resource_type
                )
                status = (res or {}).get("result")
                print(
                    f"🗑️  {json_path.name} :: {source} :: {public_id} -> {status}"
                )
                if status in SUCCESS_RESULTS:
                    confirmed += 1
                else:
                    reason = f"unexpected result: {status!r}"
                    print(f"⚠️  删除未确认 {public_id}: {reason}")
                    failures.append((public_id, reason))
            except Exception as exc:
                reason = str(exc) or type(exc).__name__
                print(f"⚠️  删除失败 {public_id}: {reason}")
                failures.append((public_id, reason))

    return confirmed, failures


def main() -> int:
    uploads_dir = Path("cloudinary_uploads")
    if not uploads_dir.exists():
        print("⚠️  无 cloudinary_uploads 目录，跳过 Cloudinary 清理")
        return 0

    json_files = sorted(uploads_dir.glob("*_cloudinary_urls.json"))
    if not json_files:
        print("⚠️  未发现 *_cloudinary_urls.json，跳过 Cloudinary 清理")
        return 0

    ensure_cloudinary_config()
    total_confirmed = 0
    files_removed = 0
    files_kept = 0

    for jf in json_files:
        confirmed, failures = destroy_from_json(jf)
        total_confirmed += confirmed
        if failures:
            files_kept += 1
            print(
                f"⛔ 保留记录文件（{len(failures)} 个资源未确认删除）: {jf}"
            )
            continue
        try:
            jf.unlink()
            files_removed += 1
            print(f"🧹 已删除记录文件: {jf}")
        except Exception as exc:
            files_kept += 1
            print(f"⚠️  删除记录文件失败 {jf}: {exc}")

    print(
        f"✅ Cloudinary 清理完成，确认删除 {total_confirmed} 个资源；"
        f"移除 JSON {files_removed}，保留 JSON {files_kept}"
    )
    return 1 if files_kept else 0


if __name__ == "__main__":
    raise SystemExit(main())
