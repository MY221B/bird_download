#!/usr/bin/env python3
"""
删除 cloudinary_uploads/*.json 中记录的所有 Cloudinary 图片，并删除对应 JSON 文件。
"""

import os
import sys
import json
from pathlib import Path

import cloudinary
import cloudinary.uploader

from cloudinary_credentials import ensure_cloudinary_config

def destroy_from_json(json_path: Path) -> int:
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    total = 0
    for source, images in (data or {}).items():
        # 跳过 bird_info 字段（它是字典，不是图片列表）
        if source == 'bird_info' or not isinstance(images, list):
            continue
        for img in images or []:
            public_id = img.get('public_id')
            if not public_id:
                continue
            try:
                res = cloudinary.uploader.destroy(public_id, invalidate=True, resource_type='image')
                status = res.get('result')
                print(f"🗑️  {json_path.name} :: {source} :: {public_id} -> {status}")
                total += 1
            except Exception as e:
                print(f"⚠️  删除失败 {public_id}: {e}")
    return total

def main():
    uploads_dir = Path('cloudinary_uploads')
    if not uploads_dir.exists():
        print("⚠️  无 cloudinary_uploads 目录，跳过 Cloudinary 清理")
        return

    json_files = sorted(uploads_dir.glob('*_cloudinary_urls.json'))
    if not json_files:
        print("⚠️  未发现 *_cloudinary_urls.json，跳过 Cloudinary 清理")
        return

    ensure_cloudinary_config()
    total_deleted = 0
    for jf in json_files:
        total_deleted += destroy_from_json(jf)
        try:
            jf.unlink()
            print(f"🧹 已删除记录文件: {jf}")
        except Exception as e:
            print(f"⚠️  删除记录文件失败 {jf}: {e}")

    print(f"✅ Cloudinary 清理完成，尝试删除 {total_deleted} 张图片")

if __name__ == '__main__':
    main()


