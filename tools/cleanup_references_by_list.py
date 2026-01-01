#!/usr/bin/env python3
"""
按 public_id 清单，从以下目录的记录文件中移除对应项：
1) cloudinary_uploads/*_cloudinary_urls.json
2) feather-flash-quiz/location_birds/**/**/*_cloudinary_urls.json

用法：
  python tools/cleanup_references_by_list.py --file delete_list.json
支持两种清单结构：
  {"items": [{"public_id": "..."}, ...]} 或 ["..."]
"""

import argparse
import json
from pathlib import Path
from typing import List, Dict, Any


def load_public_ids(p: Path) -> List[str]:
    data = json.loads(p.read_text(encoding="utf-8"))
    if isinstance(data, dict) and isinstance(data.get("items"), list):
        return [i["public_id"] for i in data["items"] if i and i.get("public_id")]
    if isinstance(data, list):
        return [x for x in data if isinstance(x, str) and x]
    raise ValueError("无法识别的JSON结构")


def clean_file(fp: Path, to_remove: set) -> int:
    try:
        obj: Dict[str, Any] = json.loads(fp.read_text(encoding="utf-8"))
    except Exception:
        return 0
    changed = 0

    # 这些 key 的值是数组，里面每项可能含有 public_id
    for key, val in list(obj.items()):
        if not isinstance(val, list):
            continue
        new_list = []
        for item in val:
            if isinstance(item, dict) and item.get("public_id") in to_remove:
                changed += 1
                continue
            new_list.append(item)
        if len(new_list) != len(val):
            obj[key] = new_list

    if changed:
        fp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    return changed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", required=True)
    args = ap.parse_args()

    ids = set(load_public_ids(Path(args.file)))
    if not ids:
        print("无要移除的 public_id")
        return

    roots = [
        Path("cloudinary_uploads"),
        Path("feather-flash-quiz/location_birds"),
    ]

    total = 0
    files = []
    for root in roots:
        if not root.exists():
            continue
        files.extend(root.rglob("*_cloudinary_urls.json"))

    for f in sorted(files):
        removed = clean_file(f, ids)
        if removed:
            total += removed
            print(f"✂️  {f} - 移除 {removed} 项")

    print(f"✅ 引用清理完成：合计移除 {total} 项")


if __name__ == "__main__":
    main()


