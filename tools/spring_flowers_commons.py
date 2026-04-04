#!/usr/bin/env python3
"""
春日赏花指南：从 Wikimedia Commons 为每种花选取并下载 3 张图。

流程（与 docs/wikimedia-image-download-guide.md 一致）：
  MediaWiki API 取 thumburl（同时传 iiurlwidth / iiurlheight，控制竖图高度）→ curl + 浏览器 UA 下载 → file 校验 JPEG/PNG。

选图：按物种关键词搜索 File 命名空间，过滤非照片文件名后，用 imageinfo 校验存在性，取前 3 个。

用法：
  python3 tools/spring_flowers_commons.py build    # 生成 tools/spring_flowers_manifest.json
  python3 tools/spring_flowers_commons.py download
"""

from __future__ import annotations

import json
import os
import re
import ssl
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from typing import Iterable

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_BASE = os.path.join(REPO_ROOT, "feather-flash-quiz", "public", "flowers")
MANIFEST_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "spring_flowers_manifest.json")

# 缩略图最大边：同时限制宽高，使卡片内图片高度更可控（Commons 按「适配框内」缩放）
WIDTH = 720
THUMB_MAX_HEIGHT = 420
API_DELAY = 1.5
SEARCH_DELAY = 0.4
DOWNLOAD_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
API_UA = "FeatherFlashQuiz/1.0 (educational; bird-flashcard project)"

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

BAD_SUBSTR = re.compile(
    r"price list|bulletin|\.webm|\.svg|\.pdf|diagram|range map|illustration|"
    r"herbarium|MHNT\.|icon\.|logo\.|coat of arms|stamp|postcard|drawing\b|"
    r"poster\b",
    re.I,
)

# 每种花：依次尝试的搜索词，直到凑满 3 个文件
FLOWER_SEARCH_QUERIES: dict[str, list[str]] = {
    "cherry_blossom": ["Prunus serrulata flower", "Prunus serrulata blossom"],
    "xifu_crabapple": ["Malus micromalus flower", "西府海棠 Malus"],
    "chuisi_crabapple": ["Malus halliana flower", "垂絲海棠 Malus halliana"],
    "february_orchid": ["Orychophragmus violaceus flower", "二月兰 Orychophragmus"],
    "white_magnolia": ["Magnolia denudata flower", "Yulan magnolia flower"],
    "purple_magnolia": ["Magnolia liliiflora flower", "Magnolia liliiflora blossom"],
    "lilac": ["Syringa oblata flower", "Syringa vulgaris flower"],
    "tree_peony": ["Paeonia suffruticosa flower", "tree peony Paeonia suffruticosa"],
    "pear_blossom": ["Pyrus flower blossom white", "pear tree blossom"],
    "forsythia": ["Forsythia suspensa flower", "Forsythia flower yellow"],
    "mountain_peach": ["Prunus davidiana flower", "Prunus davidiana blossom"],
    "apricot_blossom": ["Prunus armeniaca flower", "apricot blossom"],
    "plum_blossom": ["Prunus mume flower", "Japanese apricot flower Prunus mume"],
    "tulip": ["Tulipa flower garden", "Tulip flower"],
    "flowering_plum": ["Prunus triloba flower", "flowering plum Prunus triloba"],
    "rapeseed": ["Brassica napus flower yellow", "rapeseed flower field"],
    "wisteria": ["Wisteria sinensis flower", "Chinese wisteria flower"],
    "fringe_tree": ["Chionanthus retusus flower", "fringe tree flower white"],
    "snowball": ["Viburnum macrocephalum flower", "Chinese snowball viburnum"],
    "corn_poppy": ["Papaver rhoeas flower", "corn poppy red"],
    "banksia_rose": ["Rosa banksiae flower yellow", "Rosa banksiae Lutea"],
    "qiong_hua": ["Viburnum keteleeri", "琼花 Viburnum"],
    "azalea": ["Rhododendron simsii flower", "azalea flower rhododendron"],
    "camellia": ["Camellia japonica flower", "Japanese camellia flower"],
    "iris": ["Iris tectorum flower", "roof iris flower"],
    "herbaceous_peony": ["Paeonia lactiflora flower", "Chinese peony Paeonia lactiflora"],
    "chinese_rose": ["Rosa chinensis flower", "China rose Rosa chinensis"],
    "rugosa_rose": ["Rosa rugosa flower", "beach rose Rosa rugosa"],
    "flame_vine": ["Pyrostegia venusta flower", "Pyrostegia venusta"],
    "pink_shower_tree": ["Cassia bakeriana flower", "Cassia bakeriana"],
    "peach_blossom": ["Prunus persica flower blossom", "peach flower Prunus persica"],
}


def _get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": API_UA})
    with urllib.request.urlopen(req, context=ctx) as resp:
        return json.loads(resp.read())


def commons_search(query: str, limit: int = 20) -> list[str]:
    params = urllib.parse.urlencode(
        {
            "action": "query",
            "format": "json",
            "list": "search",
            "srsearch": query,
            "srnamespace": 6,
            "srlimit": limit,
        }
    )
    url = "https://commons.wikimedia.org/w/api.php?" + params
    d = _get_json(url)
    out: list[str] = []
    for h in d.get("query", {}).get("search", []):
        title = h.get("title", "")
        if title.startswith("File:"):
            title = title[5:]
        out.append(title)
    time.sleep(SEARCH_DELAY)
    return out


def file_has_imageinfo(wiki_filename: str) -> bool:
    encoded = urllib.parse.quote("File:" + wiki_filename)
    api_url = (
        "https://commons.wikimedia.org/w/api.php"
        f"?action=query&titles={encoded}"
        "&prop=imageinfo&iiprop=url&format=json"
    )
    try:
        d = _get_json(api_url)
    except Exception:
        return False
    pages = d.get("query", {}).get("pages", {})
    p = list(pages.values())[0] if pages else {}
    time.sleep(SEARCH_DELAY)
    return bool(p.get("imageinfo"))


def is_acceptable_title(name: str) -> bool:
    lower = name.lower()
    if not lower.endswith((".jpg", ".jpeg", ".png", ".JPG", ".JPEG", ".PNG")):
        return False
    if BAD_SUBSTR.search(name):
        return False
    if len(name) < 8:
        return False
    return True


def pick_three_wiki_files(flower_id: str) -> list[str]:
    seen: set[str] = set()
    chosen: list[str] = []
    queries = FLOWER_SEARCH_QUERIES.get(flower_id, [])
    if not queries:
        raise SystemExit(f"未配置搜索词: {flower_id}")
    for q in queries:
        if len(chosen) >= 3:
            break
        for title in commons_search(q, limit=25):
            if title in seen:
                continue
            if not is_acceptable_title(title):
                continue
            if not file_has_imageinfo(title):
                continue
            seen.add(title)
            chosen.append(title)
            if len(chosen) >= 3:
                break
    if len(chosen) < 3:
        raise SystemExit(f"{flower_id}: 只找到 {len(chosen)} 张，请补充搜索词或手工编辑 manifest")
    return chosen[:3]


def build_manifest() -> None:
    manifest: dict[str, list[str]] = {}
    ids = sorted(FLOWER_SEARCH_QUERIES.keys())
    for i, fid in enumerate(ids):
        print(f"[{i+1}/{len(ids)}] 选取 {fid} ...", flush=True)
        manifest[fid] = pick_three_wiki_files(fid)
        time.sleep(API_DELAY)
    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"已写入 {MANIFEST_PATH}")


def get_thumb_url(
    wiki_filename: str,
    max_width: int | None = None,
    max_height: int | None = None,
) -> str | None:
    mw = WIDTH if max_width is None else max_width
    mh = THUMB_MAX_HEIGHT if max_height is None else max_height
    encoded = urllib.parse.quote("File:" + wiki_filename)
    api_url = (
        "https://commons.wikimedia.org/w/api.php"
        f"?action=query&titles={encoded}"
        "&prop=imageinfo&iiprop=url"
        f"&iiurlwidth={mw}&iiurlheight={mh}&format=json"
    )
    req = urllib.request.Request(api_url, headers={"User-Agent": API_UA})
    with urllib.request.urlopen(req, context=ctx) as resp:
        d = json.loads(resp.read())
    pages = d["query"]["pages"]
    p = list(pages.values())[0]
    if "imageinfo" not in p:
        return None
    info = p["imageinfo"][0]
    return info.get("thumburl", info["url"])


def get_full_url(wiki_filename: str) -> str | None:
    encoded = urllib.parse.quote("File:" + wiki_filename)
    api_url = (
        "https://commons.wikimedia.org/w/api.php"
        f"?action=query&titles={encoded}"
        "&prop=imageinfo&iiprop=url&format=json"
    )
    req = urllib.request.Request(api_url, headers={"User-Agent": API_UA})
    with urllib.request.urlopen(req, context=ctx) as resp:
        d = json.loads(resp.read())
    pages = d["query"]["pages"]
    p = list(pages.values())[0]
    if "imageinfo" not in p:
        return None
    return p["imageinfo"][0]["url"]


def download_with_curl(url: str, output_path: str) -> bool:
    result = subprocess.run(
        [
            "curl",
            "-sL",
            "-H",
            f"User-Agent: {DOWNLOAD_UA}",
            "-H",
            "Referer: https://commons.wikimedia.org/",
            "-o",
            output_path,
            url,
        ],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def verify_image(path: str) -> bool:
    result = subprocess.run(["file", "-b", path], capture_output=True, text=True)
    return "JPEG" in result.stdout or "PNG" in result.stdout


def maybe_downscale_max_height(path: str, max_h: int) -> None:
    """Commons 的 thumburl 有时仍指向较大衍生图；在 macOS 上把过高的图压到 max_h（仅缩小不放大）。"""
    if sys.platform != "darwin" or max_h <= 0:
        return
    try:
        r = subprocess.run(
            ["sips", "-g", "pixelHeight", path],
            capture_output=True,
            text=True,
        )
        h = 0
        for line in r.stdout.splitlines():
            if "pixelHeight" in line:
                h = int(line.split(":", 1)[1].strip())
                break
        if h > max_h:
            subprocess.run(
                ["sips", "--resampleHeight", str(max_h), path],
                capture_output=True,
                check=False,
            )
    except (ValueError, OSError):
        pass


def download_one(wiki_filename: str, output_path: str) -> tuple[bool, str]:
    try:
        thumb_url = get_thumb_url(wiki_filename)
    except Exception as e:
        return False, f"API: {e}"
    time.sleep(API_DELAY)
    if not thumb_url:
        return False, "无 thumburl"
    if not download_with_curl(thumb_url, output_path):
        return False, "curl 失败"
    if not verify_image(output_path):
        for mw, mh in ((560, 360), (480, 320)):
            time.sleep(API_DELAY)
            try:
                u2 = get_thumb_url(wiki_filename, max_width=mw, max_height=mh)
            except Exception:
                u2 = None
            if u2 and download_with_curl(u2, output_path) and verify_image(output_path):
                maybe_downscale_max_height(output_path, THUMB_MAX_HEIGHT)
                return True, "OK"
        full = None
        try:
            full = get_full_url(wiki_filename)
        except Exception:
            pass
        time.sleep(API_DELAY)
        if full:
            download_with_curl(full, output_path)
        if not verify_image(output_path):
            return False, "非 JPEG/PNG"
    maybe_downscale_max_height(output_path, THUMB_MAX_HEIGHT)
    return True, "OK"


def download_from_manifest() -> None:
    if not os.path.isfile(MANIFEST_PATH):
        print("请先运行: python3 tools/spring_flowers_commons.py build", file=sys.stderr)
        raise SystemExit(1)
    with open(MANIFEST_PATH, encoding="utf-8") as f:
        manifest: dict[str, list[str]] = json.load(f)
    failed: list[tuple[str, str, str]] = []
    for flower_id, wiki_list in manifest.items():
        out_dir = os.path.join(OUTPUT_BASE, flower_id)
        os.makedirs(out_dir, exist_ok=True)
        for idx, wiki_name in enumerate(wiki_list[:3], start=1):
            out_path = os.path.join(out_dir, f"{idx}.jpg")
            print(f"{flower_id}/{idx}.jpg ← {wiki_name[:60]}...", end=" ", flush=True)
            ok, msg = download_one(wiki_name, out_path)
            print(msg if ok else msg, flush=True)
            if not ok:
                failed.append((flower_id, wiki_name, msg))
    print(f"\n完成，失败 {len(failed)} 项")
    if failed:
        for a, b, c in failed:
            print(f"  - {a}: {b[:70]} ({c})")
        raise SystemExit(1)


def main() -> None:
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "build":
        build_manifest()
    elif cmd == "download":
        download_from_manifest()
    else:
        print("用法: python3 tools/spring_flowers_commons.py build|download", file=sys.stderr)
        raise SystemExit(2)


if __name__ == "__main__":
    main()
