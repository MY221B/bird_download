#!/usr/bin/env python3
"""
根据提供的 public_id 列表删除 Cloudinary 图片。

用法：
  python tools/delete_cloudinary_by_list.py --file delete_list.json

delete_list.json 支持两种结构：
1) { "items": [{"public_id": "bird-gallery/xxx"}, ...] }
2) ["bird-gallery/xxx", "bird-gallery/yyy", ...]
"""

import argparse
import json
import sys
from pathlib import Path

import cloudinary
import cloudinary.uploader

# 复用项目内置凭证（与 tools/cloudinary_cleanup.py 一致）
CLOUD_NAME = "dzor6lhz8"
API_KEY = "972579995456539"
API_SECRET = "pKXHi4_VR4fasuJ0AanitLGWfCM"

cloudinary.config(
    cloud_name=CLOUD_NAME,
    api_key=API_KEY,
    api_secret=API_SECRET,
    secure=True,
)


def load_public_ids(p: Path):
    with p.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict) and isinstance(data.get("items"), list):
        return [item["public_id"] for item in data["items"] if item and item.get("public_id")]
    if isinstance(data, list):
        return [x for x in data if isinstance(x, str) and x]
    raise ValueError("无法识别的JSON结构，请参考文件头部注释示例")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", required=True, help="包含 public_id 列表的 JSON 文件路径")
    args = ap.parse_args()

    path = Path(args.file)
    if not path.exists():
        print(f"❌ 文件不存在: {path}")
        sys.exit(1)

    public_ids = load_public_ids(path)
    if not public_ids:
        print("⚠️ 无需删除，列表为空")
        return

    ok = 0
    for pid in public_ids:
        try:
            res = cloudinary.uploader.destroy(pid, invalidate=True, resource_type='image')
            status = res.get('result')
            print(f"🗑️  {pid} -> {status}")
            ok += 1
        except Exception as e:
            print(f"⚠️  删除失败 {pid}: {e}")

    print(f"✅ 完成，尝试删除 {ok}/{len(public_ids)} 张图片")


if __name__ == "__main__":
    main()


