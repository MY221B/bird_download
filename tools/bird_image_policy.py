"""
鸟类本地图片大小策略：weekly refresh 与上传流水线共用。

小于 MIN_BIRD_IMAGE_BYTES 的文件视为无效占位图（如错误页、透明像素），
下载后会删除，且不计入「有本地图」、也不会上传 Cloudinary。
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

# 10 KB：过小文件几乎不可能是可用鸟图
MIN_BIRD_IMAGE_BYTES = 10 * 1024

# 与 batch_fetch / upload 使用的子目录一致
SOURCE_SUBDIRS = ("macaulay", "inaturalist", "wikimedia", "avibase", "birdphotos")


def iter_image_files(source_path: Path):
    """遍历单个来源目录下的常见图片扩展名。"""
    if not source_path.is_dir():
        return
    for pattern in ("*.jpg", "*.jpeg", "*.png"):
        yield from source_path.glob(pattern)


def list_acceptable_images_in_source(source_path: Path) -> list[Path]:
    """仅包含达到最小字节数的图片文件。"""
    out = []
    for p in iter_image_files(source_path):
        try:
            if p.is_file() and p.stat().st_size >= MIN_BIRD_IMAGE_BYTES:
                out.append(p)
        except OSError:
            continue
    return sorted(out)


def bird_dir_has_acceptable_local_images(bird_path: Path) -> bool:
    """某物种 images/<slug> 下是否存在至少一张合格本地图。"""
    if not bird_path.is_dir():
        return False
    for name in SOURCE_SUBDIRS:
        sp = bird_path / name
        if list_acceptable_images_in_source(sp):
            return True
    return False


def count_acceptable_images_in_bird_dir(bird_path: Path) -> int:
    n = 0
    for name in SOURCE_SUBDIRS:
        sp = bird_path / name
        if sp.is_dir():
            n += len(list_acceptable_images_in_source(sp))
    return n


def prune_tiny_images_in_bird_dir(bird_path: Path) -> int:
    """删除该物种目录下过小的图片，返回删除文件数。"""
    removed = 0
    for name in SOURCE_SUBDIRS:
        sp = bird_path / name
        if not sp.is_dir():
            continue
        for p in iter_image_files(sp):
            try:
                if p.is_file() and p.stat().st_size < MIN_BIRD_IMAGE_BYTES:
                    p.unlink()
                    removed += 1
            except OSError:
                continue
    return removed


def prune_tiny_images_for_slugs(images_root: Path, slugs: Iterable[str]) -> int:
    """对给定 slug 列表在 images_root 下执行过小文件清理。"""
    total = 0
    for slug in slugs:
        bp = images_root / slug
        if bp.is_dir():
            total += prune_tiny_images_in_bird_dir(bp)
    return total
