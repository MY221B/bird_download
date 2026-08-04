#!/usr/bin/env python3
"""安全下载本地图片：失败时不得覆盖已有有效文件。"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Optional


def is_valid_image(path: Path) -> bool:
    """用 file(1) 判断路径是否为 JPEG/PNG 图片。"""
    if not path.is_file() or path.stat().st_size <= 0:
        return False
    verify = subprocess.run(
        ["file", str(path)],
        capture_output=True,
        text=True,
        check=False,
    )
    out = verify.stdout or ""
    return "JPEG" in out or "PNG" in out


def download_image_safely(
    url: str,
    dest: Path,
    *,
    timeout_sec: int = 60,
    curl_bin: str = "curl",
) -> str:
    """下载图片到 dest，且绝不在失败路径上毁掉已有有效图。

    返回值:
      - "skipped": dest 已是有效图片，未重新下载
      - "downloaded": 下载并校验成功，已写入 dest
      - "failed": 下载或校验失败；若 dest 原先有效则保持不变
    """
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)

    if is_valid_image(dest):
        return "skipped"

    part = dest.with_name(dest.name + ".part")
    try:
        if part.exists():
            part.unlink()
    except OSError:
        pass

    result = subprocess.run(
        [
            curl_bin,
            "-fsL",
            "--max-time",
            str(timeout_sec),
            "-o",
            str(part),
            url,
        ],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0 or not is_valid_image(part):
        try:
            if part.exists():
                part.unlink()
        except OSError:
            pass
        return "failed"

    part.replace(dest)
    return "downloaded"


def safe_curl_to_path(url: str, dest: str) -> Optional[bool]:
    """兼容旧调用：True=新下载成功，False=失败，None=已存在有效图而跳过。"""
    status = download_image_safely(url, Path(dest))
    if status == "skipped":
        return None
    return status == "downloaded"
