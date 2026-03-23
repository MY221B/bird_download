#!/usr/bin/env python3
"""
迁移脚本：把本地 images/ 里的所有鸟类图片重新上传到新的 Cloudinary 账号。
公共路径（public_id）与原始结构相同，迁移完成后只需在前端设置
VITE_CLOUDINARY_CLOUD_NAME=<新cloud名> 即可让网站使用新 cloud。

用法：
  python3 tools/migrate_to_new_cloudinary.py \
      --cloud NEW_CLOUD_NAME \
      --api-key NEW_API_KEY \
      --api-secret NEW_API_SECRET

选项：
  --dry-run       只检查本地文件，不真正上传
  --bird SLUG     只迁移指定鸟（可重复多次），如 --bird marsh_tit --bird mallard
  --workers N     并行上传线程数（默认 4）
  --skip-existing 如果 Cloudinary 上已有同 public_id 的资源则跳过（默认覆盖）
"""

import os
import sys
import json
import time
import argparse
import threading
from pathlib import Path
from queue import Queue

try:
    import cloudinary
    import cloudinary.uploader
    import cloudinary.api
except ImportError:
    sys.exit("请先安装: pip install cloudinary")

REPO_ROOT = Path(__file__).parent.parent
IMAGES_DIR = REPO_ROOT / "images"
UPLOADS_DIR = REPO_ROOT / "cloudinary_uploads"

SOURCES = ["macaulay", "inaturalist", "birdphotos", "wikimedia", "avibase"]


def load_existing_upload_record(bird: str) -> dict:
    """读取 cloudinary_uploads/ 里原始上传记录（用于保留署名）"""
    p = UPLOADS_DIR / f"{bird}_cloudinary_urls.json"
    if p.exists():
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    return {}


def find_attribution(bird: str, source: str, filename: str, record: dict) -> dict:
    """从旧上传记录里找到对应文件的署名，保持不变"""
    default = {"source": source, "note": "迁移自旧 cloud"}
    for img in record.get(source, []):
        if img.get("original_file") == filename or img.get("original_file") == filename:
            return img.get("attribution", default)
    return default


def upload_bird(bird: str, args: argparse.Namespace, lock: threading.Lock, counters: dict) -> dict:
    """上传单个鸟的所有图片，返回该鸟的 cloudinary_urls 结构"""
    bird_dir = IMAGES_DIR / bird
    record = load_existing_upload_record(bird)
    result: dict = {"bird_info": record.get("bird_info", {"slug": bird})}

    for source in SOURCES:
        src_dir = bird_dir / source
        if not src_dir.exists():
            continue

        images = sorted(
            list(src_dir.glob("*.jpg"))
            + list(src_dir.glob("*.jpeg"))
            + list(src_dir.glob("*.png"))
        )
        if not images:
            continue

        # 可选：限制每个来源的图片数（节省带宽 credits）
        if args.max_per_source and len(images) > args.max_per_source:
            images = images[: args.max_per_source]

        result.setdefault(source, [])
        for img_path in images:
            folder = f"bird-gallery/{bird}/{source}"
            public_id = img_path.stem
            full_public_id = f"{folder}/{public_id}"

            if args.dry_run:
                with lock:
                    print(f"  [dry-run] 会上传 {full_public_id}")
                    counters["ok"] += 1
                result[source].append({"original_file": img_path.name, "public_id": full_public_id, "url": f"(dry-run)"})
                continue

            for attempt in range(3):
                try:
                    up = cloudinary.uploader.upload(
                        str(img_path),
                        folder=folder,
                        public_id=public_id,
                        overwrite=not args.skip_existing,
                        resource_type="image",
                        timeout=90,
                    )
                    attribution = find_attribution(bird, source, img_path.name, record)
                    entry = {
                        "original_file": img_path.name,
                        "url": up["secure_url"],
                        "public_id": up["public_id"],
                        "width": up["width"],
                        "height": up["height"],
                        "format": up["format"],
                        "bytes": up["bytes"],
                        "attribution": attribution,
                    }
                    result[source].append(entry)
                    with lock:
                        counters["ok"] += 1
                        print(f"  ✅ {full_public_id}")
                    break
                except cloudinary.exceptions.Error as e:
                    if "already exists" in str(e) and args.skip_existing:
                        with lock:
                            counters["skipped"] += 1
                        break
                    if attempt < 2:
                        time.sleep(2 ** attempt)
                    else:
                        with lock:
                            counters["fail"] += 1
                            print(f"  ❌ {full_public_id}: {e}", file=sys.stderr)

    # 声音跳过（video 资源单独处理，免费 cloud 可能不支持）
    return result


def worker(q: Queue, args: argparse.Namespace, lock: threading.Lock, counters: dict, all_results: dict):
    while True:
        bird = q.get()
        if bird is None:
            q.task_done()
            break
        with lock:
            print(f"\n=== {bird} ===")
        data = upload_bird(bird, args, lock, counters)
        with lock:
            all_results[bird] = data
        q.task_done()


def main():
    parser = argparse.ArgumentParser(description="迁移 Cloudinary 图片到新 cloud")
    parser.add_argument("--cloud", required=True, help="新 cloud name")
    parser.add_argument("--api-key", required=True, help="新账号 API Key")
    parser.add_argument("--api-secret", required=True, help="新账号 API Secret")
    parser.add_argument("--dry-run", action="store_true", help="只检查，不上传")
    parser.add_argument("--bird", action="append", dest="birds", help="只迁移指定鸟（可重复）")
    parser.add_argument("--workers", type=int, default=4, help="并行线程数")
    parser.add_argument("--skip-existing", action="store_true", help="已有资源则跳过")
    parser.add_argument("--max-per-source", type=int, default=0,
                        help="每个来源最多上传几张（0=不限制，推荐新账号用 --max-per-source 1 保留每来源最佳图）")
    args = parser.parse_args()

    # 配置新 Cloudinary
    cloudinary.config(
        cloud_name=args.cloud,
        api_key=args.api_key,
        api_secret=args.api_secret,
        secure=True,
    )

    if not args.dry_run:
        try:
            cloudinary.api.ping()
            print(f"✅ 新 cloud '{args.cloud}' 连接成功\n")
        except Exception as e:
            sys.exit(f"❌ 连接新 cloud 失败: {e}")

    # 确定要迁移的鸟列表
    if args.birds:
        birds = args.birds
    else:
        birds = sorted(d.name for d in IMAGES_DIR.iterdir() if d.is_dir())

    print(f"共 {len(birds)} 种鸟要迁移，使用 {args.workers} 个线程")

    lock = threading.Lock()
    counters = {"ok": 0, "fail": 0, "skipped": 0}
    all_results: dict = {}

    q: Queue = Queue()
    threads = [threading.Thread(target=worker, args=(q, args, lock, counters, all_results), daemon=True)
               for _ in range(args.workers)]
    for t in threads:
        t.start()
    for b in birds:
        q.put(b)
    for _ in threads:
        q.put(None)
    q.join()
    for t in threads:
        t.join()

    # 保存结果到 cloudinary_uploads_new/
    if not args.dry_run:
        out_dir = REPO_ROOT / "cloudinary_uploads_new"
        out_dir.mkdir(exist_ok=True)
        for bird, data in all_results.items():
            out = out_dir / f"{bird}_cloudinary_urls.json"
            with open(out, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"\n✅ 结果保存到 cloudinary_uploads_new/（共 {len(all_results)} 个 JSON）")
        print(f"\n接下来：")
        print(f"  1. 在 feather-flash-quiz/.env 中设置: VITE_CLOUDINARY_CLOUD_NAME={args.cloud}")
        print(f"  2. 在 Vercel 项目设置里添加同名环境变量")
        print(f"  3. 重新部署（git push）即可")

    print(f"\n统计：成功 {counters['ok']}，跳过 {counters['skipped']}，失败 {counters['fail']}")


if __name__ == "__main__":
    main()
