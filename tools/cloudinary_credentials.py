"""
Cloudinary 凭证：优先环境变量，否则读取仓库根目录 .cloudinary_secrets（与 .gitignore 一致，勿提交）。

环境变量（可选）：
  CLOUDINARY_CLOUD_NAME / CLOUDINARY_API_KEY / CLOUDINARY_API_SECRET
  若仅设置了 VITE_CLOUDINARY_CLOUD_NAME，上传仍需要 API Key/Secret，须来自文件或 CLOUDINARY_API_*。
"""

from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

LEGACY_CLOUD_NAME = "dzor6lhz8"

_applied = False
_last_cloud_name = ""


def parse_dot_cloudinary_secrets(path: Path) -> dict[str, str]:
    """解析 KEY=value 行，返回小写键 cloud_name / api_key / api_secret。"""
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return out
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        key = key.strip().upper()
        val = val.strip().strip('"').strip("'")
        if key == "CLOUD_NAME":
            out["cloud_name"] = val
        elif key == "API_KEY":
            out["api_key"] = val
        elif key == "API_SECRET":
            out["api_secret"] = val
    return out


def try_resolve_cloud_name_for_gallery() -> str | None:
    """仅 cloud name（画廊 URL 重写）；不需要 API 密钥。"""
    env = (os.environ.get("VITE_CLOUDINARY_CLOUD_NAME") or "").strip()
    if env and env != LEGACY_CLOUD_NAME:
        return env
    data = parse_dot_cloudinary_secrets(PROJECT_ROOT / ".cloudinary_secrets")
    cn = (data.get("cloud_name") or "").strip()
    if cn and cn != LEGACY_CLOUD_NAME:
        return cn
    return None


def resolve_cloudinary_credentials() -> tuple[str, str, str]:
    """上传/删除 API 使用的 (cloud_name, api_key, api_secret)。"""
    data = parse_dot_cloudinary_secrets(PROJECT_ROOT / ".cloudinary_secrets")
    cn = (
        os.environ.get("CLOUDINARY_CLOUD_NAME")
        or os.environ.get("VITE_CLOUDINARY_CLOUD_NAME")
        or data.get("cloud_name", "")
        or ""
    ).strip()
    key = (os.environ.get("CLOUDINARY_API_KEY") or data.get("api_key", "") or "").strip()
    secret = (os.environ.get("CLOUDINARY_API_SECRET") or data.get("api_secret", "") or "").strip()
    if cn and key and secret:
        return cn, key, secret
    raise SystemExit(
        "未找到 Cloudinary 凭证：请在仓库根目录创建 .cloudinary_secrets（CLOUD_NAME、API_KEY、API_SECRET），\n"
        "或设置环境变量 CLOUDINARY_CLOUD_NAME、CLOUDINARY_API_KEY、CLOUDINARY_API_SECRET。"
    )


def ensure_cloudinary_config() -> str:
    """初始化 cloudinary SDK（幂等）；返回当前 cloud_name。"""
    global _applied, _last_cloud_name
    if _applied:
        return _last_cloud_name
    import cloudinary

    cn, key, secret = resolve_cloudinary_credentials()
    cloudinary.config(cloud_name=cn, api_key=key, api_secret=secret, secure=True)
    _applied = True
    _last_cloud_name = cn
    return cn
