"""在默认浏览器中打开本地 HTML；支持在无图形会话时跳过。"""

from __future__ import annotations

import os
import subprocess
import sys
import webbrowser
from pathlib import Path


def try_open_local_html(html_file: Path) -> None:
    """
    尝试用系统默认浏览器打开 file:// URL。
    - 设置环境变量 WEEKLY_REFRESH_NO_BROWSER=1 时跳过。
    - Linux 无 DISPLAY/WAYLAND 时跳过并提示手动打开。
    - macOS 使用 `open`（与历史行为一致）。
    """
    if not html_file.is_file():
        return

    env_skip = os.environ.get("WEEKLY_REFRESH_NO_BROWSER", "").strip().lower()
    if env_skip in ("1", "true", "yes", "on"):
        print(f"ℹ️  已跳过自动打开浏览器（WEEKLY_REFRESH_NO_BROWSER）。请手动打开: {html_file}")
        return

    print(f"\n🌐 正在打开 HTML 页面: {html_file}")

    if sys.platform.startswith("linux"):
        if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
            print("⚠️  未检测到 DISPLAY/WAYLAND，无法在此环境自动打开浏览器。")
            print(f"   请在本机用浏览器打开该文件，或在有图形界面的终端中重试: {html_file}")
            return
        print(
            "ℹ️  若终端出现 “Failed to connect to the bus” 等 Chromium/DBus 提示，"
            "在无会话 D-Bus 的环境下较常见，一般可忽略。"
        )

    try:
        if sys.platform == "darwin":
            subprocess.run(["open", str(html_file)], check=False)
        else:
            webbrowser.open(html_file.resolve().as_uri())
    except Exception as e:
        print(f"⚠️  自动打开失败: {e}，请手动打开 {html_file}")
