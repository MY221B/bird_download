#!/usr/bin/env python3
"""按 docs/wikimedia-image-download-guide.md 从 Commons 拉取香蜜公园赏花图。

已迁移：全量赏花图（含香蜜 6 种）请用 `tools/spring_flowers_commons.py`，
图片目录为 `public/flowers/<flower_id>/1.jpg` … `3.jpg`。
本脚本仅保留历史参考，勿再用于新流程。
"""
import json
import os
import ssl
import subprocess
import time
import urllib.parse
import urllib.request

OUTPUT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "feather-flash-quiz",
    "public",
    "flowers",
)
WIDTH = 800
API_DELAY = 1.5
DOWNLOAD_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
API_UA = "FeatherFlashQuiz/1.0 (educational; bird-flashcard project)"

FILES_TO_DOWNLOAD = {
    "chinese_rose.jpg": "Flowers of Rosa chinensis.jpg",
    "rugosa_rose.jpg": "Rosa rugosa bloom.jpg",
    "flame_vine.jpg": "Pyrostegia venusta flowers.jpg",
    "pink_shower_tree.jpg": "Cassia bakeriana in China.jpg",
    "peach_blossom.jpg": "Prunus persica flower 01.jpg",
}

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE


def get_thumb_url(wiki_filename: str):
    encoded = urllib.parse.quote("File:" + wiki_filename)
    api_url = (
        "https://commons.wikimedia.org/w/api.php"
        f"?action=query&titles={encoded}"
        "&prop=imageinfo&iiprop=url&iiurlwidth="
        f"{WIDTH}&format=json"
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


def get_full_url(wiki_filename: str):
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
        ["curl", "-sL", "-H", f"User-Agent: {DOWNLOAD_UA}", "-o", output_path, url],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def verify_image(path: str) -> bool:
    result = subprocess.run(
        ["file", "-b", path], capture_output=True, text=True
    )
    return "JPEG" in result.stdout or "PNG" in result.stdout


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    failed = []
    for output_name, wiki_name in FILES_TO_DOWNLOAD.items():
        output_path = os.path.join(OUTPUT_DIR, output_name)
        print(f"处理: {output_name} ...", end=" ", flush=True)
        try:
            thumb_url = get_thumb_url(wiki_name)
        except Exception as e:
            print(f"API 失败: {e}")
            failed.append((output_name, wiki_name, str(e)))
            time.sleep(API_DELAY)
            continue

        if not thumb_url:
            print("文件不存在于 Wikimedia Commons")
            failed.append((output_name, wiki_name, "文件不存在"))
            time.sleep(API_DELAY)
            continue

        if not download_with_curl(thumb_url, output_path):
            print("curl 下载失败")
            failed.append((output_name, wiki_name, "curl 失败"))
            time.sleep(API_DELAY)
            continue

        if not verify_image(output_path):
            size_kb = os.path.getsize(output_path) // 1024
            print(f"非图片 ({size_kb}KB)，试原图 ...", end=" ", flush=True)
            try:
                full_url = get_full_url(wiki_name)
                time.sleep(API_DELAY)
                if full_url:
                    download_with_curl(full_url, output_path)
            except Exception:
                pass
            if not verify_image(output_path):
                print("仍失败")
                failed.append((output_name, wiki_name, "内容非图片"))
                time.sleep(API_DELAY)
                continue

        size_kb = os.path.getsize(output_path) // 1024
        print(f"OK ({size_kb}KB)")
        time.sleep(API_DELAY)

    print(f"\n完成: {len(FILES_TO_DOWNLOAD) - len(failed)}/{len(FILES_TO_DOWNLOAD)} 成功")
    if failed:
        print("\n失败列表:")
        for name, wiki, reason in failed:
            print(f"  - {name} ({wiki}): {reason}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
