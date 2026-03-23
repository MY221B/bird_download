#!/usr/bin/env python3
"""
对当前 Cloudinary（.cloudinary_secrets / cloudinary_credentials）检测：
  cloudinary_uploads/*_cloudinary_urls.json 里每条图片若在 CDN 上 404，
  且本地 images/<slug>/<source>/<original_file> 仍存在，则补传并写回 JSON。

不删除任何记录；sounds 等非图片列表字段原样保留。

用法：
  python3 tools/backfill_cloudinary_missing.py --dry-run
  python3 tools/backfill_cloudinary_missing.py --bird tundra_swan
  python3 tools/backfill_cloudinary_missing.py
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

try:
    import cloudinary
    import cloudinary.uploader
except ImportError:
    sys.exit("请先安装: pip install cloudinary")

REPO_ROOT = Path(__file__).resolve().parent.parent
UPLOADS_DIR = REPO_ROOT / "cloudinary_uploads"
IMAGES_DIR = REPO_ROOT / "images"

IMAGE_SOURCES = ("macaulay", "inaturalist", "birdphotos", "wikimedia", "avibase")


def head_ok(url: str, timeout: float = 20.0) -> bool:
    req = urllib.request.Request(url, method="HEAD")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return 200 <= r.status < 400
    except urllib.error.HTTPError as e:
        return 200 <= e.code < 400
    except Exception:
        return False


def sync_json_to_feather_quiz(slug: str) -> int:
    """把主库 cloudinary_uploads 的 JSON 覆盖复制到子模块内所有同名文件。"""
    src = UPLOADS_DIR / f"{slug}_cloudinary_urls.json"
    if not src.is_file():
        return 0
    quiz = REPO_ROOT / "feather-flash-quiz"
    if not quiz.is_dir():
        return 0
    n = 0
    for dest in quiz.rglob(f"{slug}_cloudinary_urls.json"):
        shutil.copy2(src, dest)
        print(f"  📎 {dest.relative_to(REPO_ROOT)}")
        n += 1
    return n


def delivery_url(cloud: str, public_id: str, fmt: str, resource_type: str) -> str:
    fmt = (fmt or "jpg").lower()
    rt_path = "video" if resource_type == "video" else "image"
    return f"https://res.cloudinary.com/{cloud}/{rt_path}/upload/{public_id}.{fmt}"


def main() -> int:
    sys.path.insert(0, str(REPO_ROOT / "tools"))
    from cloudinary_credentials import ensure_cloudinary_config

    ap = argparse.ArgumentParser(description="补传新 Cloudinary 上缺失的图片并更新 JSON")
    ap.add_argument("--dry-run", action="store_true", help="只报告将补传哪些，不上传")
    ap.add_argument("--bird", action="append", dest="birds", help="只处理指定 slug（可多次）")
    ap.add_argument("--sleep", type=float, default=0.0, help="每条记录 HEAD 前的间隔（秒），大量扫描时可设 0.02 略降频")
    ap.add_argument(
        "--sync-feather",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="补传并写回 JSON 后，覆盖复制到 feather-flash-quiz 内所有同名 *_cloudinary_urls.json（默认开启）",
    )
    args = ap.parse_args()

    cloud = ensure_cloudinary_config()
    print(f"☁️  目标 cloud: {cloud}\n")

    json_files = sorted(UPLOADS_DIR.glob("*_cloudinary_urls.json"))
    if args.birds:
        want = set(args.birds)
        json_files = [p for p in json_files if p.stem.replace("_cloudinary_urls", "") in want]

    total_head = total_missing = total_uploaded = total_skip_no_file = total_fail = 0
    changed_slugs: set[str] = set()

    for jf in json_files:
        slug = jf.stem.replace("_cloudinary_urls", "")
        with open(jf, encoding="utf-8") as f:
            data = json.load(f)

        changed = False

        for source in IMAGE_SOURCES:
            items = data.get(source)
            if not isinstance(items, list):
                continue

            for idx, entry in enumerate(items):
                if not isinstance(entry, dict):
                    continue
                public_id = entry.get("public_id")
                orig = entry.get("original_file")
                if not public_id or not orig:
                    continue

                fmt = (entry.get("format") or Path(orig).suffix.lstrip(".") or "jpg").lower()
                check_url = delivery_url(cloud, public_id, fmt, "image")
                total_head += 1
                if args.sleep > 0:
                    time.sleep(args.sleep)

                if head_ok(check_url):
                    continue

                total_missing += 1
                local = IMAGES_DIR / slug / source / orig
                if not local.is_file():
                    print(f"  ⚠️  远端缺图且无本地文件: {slug}/{source}/{orig}")
                    total_skip_no_file += 1
                    continue

                print(f"  📤 补传: {public_id}  <- {local}")
                if args.dry_run:
                    total_uploaded += 1
                    continue

                folder = f"bird-gallery/{slug}/{source}"
                public_id_stem = Path(orig).stem

                for attempt in range(3):
                    try:
                        up = cloudinary.uploader.upload(
                            str(local),
                            folder=folder,
                            public_id=public_id_stem,
                            overwrite=True,
                            resource_type="image",
                            timeout=120,
                        )
                        entry["url"] = up["secure_url"]
                        entry["public_id"] = up["public_id"]
                        entry["width"] = up.get("width")
                        entry["height"] = up.get("height")
                        entry["format"] = up.get("format", fmt)
                        entry["bytes"] = up.get("bytes")
                        changed = True
                        total_uploaded += 1
                        print(f"     ✅ 已上传")
                        time.sleep(0.15)
                        break
                    except Exception as e:
                        if attempt < 2:
                            time.sleep(2 ** attempt)
                        else:
                            print(f"     ❌ 失败: {e}", file=sys.stderr)
                            total_fail += 1

        if changed and not args.dry_run:
            with open(jf, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print(f"💾 已写回 {jf.relative_to(REPO_ROOT)}")
            changed_slugs.add(slug)

    if changed_slugs and not args.dry_run and args.sync_feather:
        print(f"\n🔄 同步 {len(changed_slugs)} 个 slug 到 feather-flash-quiz …")
        for s in sorted(changed_slugs):
            n = sync_json_to_feather_quiz(s)
            if n == 0:
                print(f"  (未找到子模块内 {s}_cloudinary_urls.json，可忽略)")

    print(
        f"\n📊 统计: HEAD {total_head} 次, 远端缺失 {total_missing}, "
        f"补传{'(dry-run)' if args.dry_run else ''} {total_uploaded}, "
        f"无本地文件跳过 {total_skip_no_file}, 失败 {total_fail}"
    )
    if not args.dry_run and total_uploaded:
        print("\n下一步: python3 tools/update_gallery_from_cloudinary.py")
        print("然后在 feather-flash-quiz 目录执行 manifest / 提交推送 / 部署（与推送指南一致）。")
    return 0 if total_fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
