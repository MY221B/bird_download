#!/usr/bin/env python3
"""
一次性清理脚本：删除 feather-flash-quiz/location_birds/ 下的历史日期文件夹，
每个地点只保留最新的日期文件夹（字符串排序最大值 = 时间最新）。
永不删除 000000（静态永久数据集）。
主仓库的 cloudinary_uploads 等数据文件完全不受影响。
"""

import shutil
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
LOCATION_BIRDS_DIR = REPO_ROOT / "feather-flash-quiz" / "location_birds"


def cleanup_old_date_folders(dry_run: bool = False):
    if not LOCATION_BIRDS_DIR.exists():
        print(f"目录不存在：{LOCATION_BIRDS_DIR}")
        return

    total_deleted = 0
    total_kept = 0

    for city_dir in sorted(LOCATION_BIRDS_DIR.iterdir()):
        if not city_dir.is_dir():
            continue
        for location_dir in sorted(city_dir.iterdir()):
            if not location_dir.is_dir():
                continue

            date_folders = [f for f in location_dir.iterdir() if f.is_dir()]
            if not date_folders:
                continue

            # 分离 000000（永久数据）和普通日期文件夹
            permanent = [f for f in date_folders if f.name == "000000"]
            dated = [f for f in date_folders if f.name != "000000"]

            if not dated:
                # 只有 000000，无需清理
                total_kept += len(permanent)
                continue

            # 保留字符串排序最大的（即时间最新的）
            latest = max(dated, key=lambda f: f.name)
            to_delete = [f for f in dated if f.name != latest.name]

            total_kept += len(permanent) + 1  # 000000(若有) + latest

            for old_folder in to_delete:
                file_count = sum(1 for _ in old_folder.rglob("*.json"))
                print(f"  删除 {old_folder.relative_to(REPO_ROOT)}  ({file_count} 个文件)")
                if not dry_run:
                    shutil.rmtree(old_folder)
                total_deleted += 1

    print()
    print(f"保留文件夹数：{total_kept}")
    print(f"{'[DRY RUN] 将删除' if dry_run else '已删除'}文件夹数：{total_deleted}")


if __name__ == "__main__":
    import sys

    dry_run = "--dry-run" in sys.argv

    print(f"{'=== DRY RUN 模式（不会实际删除） ===' if dry_run else '=== 开始清理历史日期文件夹 ==='}")
    print(f"目标目录：{LOCATION_BIRDS_DIR}")
    print()

    cleanup_old_date_folders(dry_run=dry_run)

    if not dry_run:
        print()
        print("清理完成。请在 feather-flash-quiz/ 目录下运行以下命令重新生成 manifest：")
        print("  node scripts/generate-location-birds-manifest.js")
