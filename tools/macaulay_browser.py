#!/usr/bin/env python3
"""通过持久化 Chromium 会话查询 Macaulay Library 素材编号。

首次使用先运行：
    python3 tools/macaulay_browser.py setup

后续脚本可以非交互查询：
    python3 tools/macaulay_browser.py search --taxon-code azwmag2 --count 20

标准输出只包含 asset id，日志写入标准错误，便于 shell 调用。
"""

from __future__ import annotations

import argparse
import fcntl
import os
import re
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROFILE_DIR = REPO_ROOT / ".browser_profiles" / "macaulay"
DEFAULT_TIMEOUT_MS = 90_000
CATALOG_URL = "https://search.macaulaylibrary.org/catalog"
CHALLENGE_MARKERS = (
    "making sure you're not a bot",
    "protected by anubis",
    "problem occurred while trying to determine if you are a bot",
    "access denied",
    "anubis",
)
ASSET_URL_PATTERN = re.compile(r"/api/v2/asset/(\d+)(?:/|$)")


class BrowserSetupRequired(RuntimeError):
    """持久会话尚未通过 Macaulay 的浏览器验证。"""


def log(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def profile_dir() -> Path:
    configured = os.environ.get("MACAULAY_BROWSER_PROFILE", "").strip()
    return Path(configured).expanduser().resolve() if configured else DEFAULT_PROFILE_DIR


@contextmanager
def profile_lock(directory: Path) -> Iterable[None]:
    """防止批处理的多个进程同时打开同一 Chromium profile。"""
    directory.mkdir(parents=True, exist_ok=True)
    lock_path = directory.parent / f"{directory.name}.lock"
    with lock_path.open("a+", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def import_playwright():
    try:
        from playwright.sync_api import Error, TimeoutError, sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            "未安装 Playwright。请先运行："
            "python3 -m pip install -r requirements.txt && "
            "python3 -m playwright install chromium"
        ) from exc
    return sync_playwright, TimeoutError, Error


def launch_context(playwright: Any, directory: Path, *, headless: bool):
    return playwright.chromium.launch_persistent_context(
        user_data_dir=str(directory),
        headless=headless,
        viewport={"width": 1440, "height": 1000},
        locale="en-US",
    )


def is_challenge(title: str, body: str) -> bool:
    text = f"{title}\n{body[:4000]}".lower()
    return any(marker in text for marker in CHALLENGE_MARKERS)


def catalog_url(taxon_code: str) -> str:
    return (
        f"{CATALOG_URL}?taxonCode={taxon_code}"
        "&mediaType=photo&sort=rating_rank_desc"
    )


def extract_asset_ids(urls: Iterable[str], count: int) -> list[str]:
    asset_ids: list[str] = []
    for url in urls:
        match = ASSET_URL_PATTERN.search(url)
        if not match:
            continue
        value = match.group(1)
        if value not in asset_ids:
            asset_ids.append(value)
        if len(asset_ids) >= count:
            break
    return asset_ids


def catalog_asset_ids(page: Any, taxon_code: str, count: int, timeout_ms: int) -> list[str]:
    page.goto(catalog_url(taxon_code), wait_until="domcontentloaded", timeout=timeout_ms)
    try:
        page.wait_for_function(
            """() => {
                const text = `${document.title}\n${document.body?.innerText || ''}`.toLowerCase();
                return !text.includes("making sure you're not a bot") &&
                       !text.includes('protected by anubis');
            }""",
            timeout=timeout_ms,
        )
    except Exception:
        pass

    title = page.title()
    body = page.locator("body").inner_text(timeout=10_000)
    if is_challenge(title, body):
        raise BrowserSetupRequired(
            "Macaulay 要求重新进行浏览器验证。请运行："
            "python3 tools/macaulay_browser.py setup"
        )

    try:
        page.locator('img[src*="cdn.download.ams.birds.cornell.edu/api/v2/asset/"]').first.wait_for(
            state="attached", timeout=timeout_ms
        )
    except Exception as exc:
        raise RuntimeError(
            f"Macaulay 搜索页未加载图片结果（title={title!r}）"
        ) from exc

    urls = page.locator(
        'img[src*="cdn.download.ams.birds.cornell.edu/api/v2/asset/"]'
    ).evaluate_all("elements => elements.map(element => element.src)")
    return extract_asset_ids(urls, count)


def setup_session(timeout_ms: int) -> int:
    sync_playwright, PlaywrightTimeoutError, PlaywrightError = import_playwright()
    directory = profile_dir()
    log(f"持久会话目录: {directory}")
    log("正在打开 Macaulay Library 并建立验证会话…")

    with profile_lock(directory), sync_playwright() as playwright:
        context = launch_context(playwright, directory, headless=False)
        try:
            page = context.pages[0] if context.pages else context.new_page()
            try:
                asset_ids = catalog_asset_ids(page, "azwmag2", 1, timeout_ms)
            except (BrowserSetupRequired, RuntimeError) as exc:
                log(f"❌ 会话校验失败: {exc}")
                return 2
            if not asset_ids:
                log("❌ 会话已连通，但测试查询没有返回素材编号")
                return 2
            log("✅ Macaulay 持久浏览器会话已就绪")
            return 0
        except (PlaywrightTimeoutError, PlaywrightError) as exc:
            log(f"❌ 浏览器会话初始化失败: {exc}")
            return 2
        finally:
            context.close()


def search_assets(taxon_code: str, count: int, timeout_ms: int, headless: bool) -> int:
    sync_playwright, PlaywrightTimeoutError, PlaywrightError = import_playwright()
    directory = profile_dir()

    with profile_lock(directory), sync_playwright() as playwright:
        context = launch_context(playwright, directory, headless=headless)
        try:
            page = context.pages[0] if context.pages else context.new_page()
            for asset_id in catalog_asset_ids(page, taxon_code, count, timeout_ms):
                print(asset_id)
            return 0
        except BrowserSetupRequired as exc:
            log(f"❌ {exc}")
            return 2
        except (PlaywrightTimeoutError, PlaywrightError, RuntimeError) as exc:
            log(f"❌ Macaulay 浏览器查询失败: {exc}")
            return 3
        finally:
            context.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Macaulay 持久浏览器会话工具")
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=int(os.environ.get("MACAULAY_BROWSER_TIMEOUT", "90")),
        help="页面超时秒数（默认 90）",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("setup", help="可视化完成首次验证并保存会话")

    search = subparsers.add_parser("search", help="使用已保存会话查询 asset id")
    search.add_argument("--taxon-code", required=True)
    search.add_argument("--count", type=int, default=20)
    search.add_argument(
        "--headless",
        action="store_true",
        help="无界面运行（Macaulay 验证可能拒绝，默认使用可见浏览器）",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    timeout_ms = max(1, args.timeout_seconds) * 1000
    try:
        if args.command == "setup":
            return setup_session(timeout_ms)
        return search_assets(args.taxon_code, max(1, args.count), timeout_ms, args.headless)
    except RuntimeError as exc:
        log(f"❌ {exc}")
        return 4


if __name__ == "__main__":
    raise SystemExit(main())
