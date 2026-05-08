#!/usr/bin/env python3
"""
Import the static Beijing breeding-bird lists from the two PDF checklists.

The source PDFs live in examples/ and are intentionally not fetched from
birdreport.cn. The script backfills missing media in the shared Cloudinary JSON
library, then copies the relevant JSON files into location_birds.
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
QUIZ_ROOT = PROJECT_ROOT / "feather-flash-quiz"
LOCATION_BIRDS_ROOT = QUIZ_ROOT / "location_birds"
CLOUDINARY_DIR = PROJECT_ROOT / "cloudinary_uploads"
ALL_BIRDS_CSV = PROJECT_ROOT / "all_birds.csv"
DATE_FOLDER = "000000"

sys.path.insert(0, str(PROJECT_ROOT / "tools"))

import auto_sounds_refresh
import process_new_birds


MANUAL_BIRD_INFO: Dict[str, Dict[str, str]] = {
    "勺鸡": {
        "slug": "koklass_pheasant",
        "english_name": "Koklass Pheasant",
        "scientific_name": "Pucrasia macrolopha",
    },
    "东方中杜鹃": {
        "slug": "oriental_cuckoo",
        "english_name": "Oriental Cuckoo",
        "scientific_name": "Cuculus optatus",
    },
    "鹮嘴鹬": {
        "slug": "ibisbill",
        "english_name": "Ibisbill",
        "scientific_name": "Ibidorhyncha struthersii",
    },
    "小星头啄木鸟": {
        "slug": "japanese_pygmy_woodpecker",
        "english_name": "Japanese Pygmy Woodpecker",
        "scientific_name": "Yungipicus kizuki",
    },
    "厚嘴苇莺": {
        "slug": "thick_billed_warbler",
        "english_name": "Thick-billed Warbler",
        "scientific_name": "Arundinax aedon",
    },
    "北短翅蝗莺": {
        "slug": "baikal_bush_warbler",
        "english_name": "Baikal Bush Warbler",
        "scientific_name": "Locustella davidi",
    },
    "棕眉柳莺": {
        "slug": "yellow_streaked_warbler",
        "english_name": "Yellow-streaked Warbler",
        "scientific_name": "Phylloscopus armandii",
    },
    "褐头鸫": {
        "slug": "grey_sided_thrush",
        "english_name": "Grey-sided Thrush",
        "scientific_name": "Turdus feae",
    },
    "绿背姬鹟": {
        "slug": "green_backed_flycatcher",
        "english_name": "Green-backed Flycatcher",
        "scientific_name": "Ficedula elisae",
    },
    "白腹暗蓝鹟": {
        "slug": "zappeys_flycatcher",
        "english_name": "Zappey's Flycatcher",
        "scientific_name": "Cyanoptila cumatilis",
    },
    "石鸡": {
        "slug": "chukar",
        "english_name": "Chukar",
        "scientific_name": "Alectoris chukar",
    },
    "褐马鸡": {
        "slug": "brown_eared_pheasant",
        "english_name": "Brown Eared Pheasant",
        "scientific_name": "Crossoptilon mantchuricum",
    },
    "小杜鹃": {
        "slug": "lesser_cuckoo",
        "english_name": "Lesser Cuckoo",
        "scientific_name": "Cuculus poliocephalus",
    },
    "北领角鸮": {
        "slug": "japanese_scops_owl",
        "english_name": "Japanese Scops-Owl",
        "scientific_name": "Otus semitorques",
    },
    "中华短翅蝗莺": {
        "slug": "chinese_bush_warbler",
        "english_name": "Chinese Bush Warbler",
        "scientific_name": "Locustella tacsanowskia",
    },
    "祁连山蓝尾鸲": {
        "slug": "qilian_bluetail",
        "english_name": "Qilian Bluetail",
        "scientific_name": "Tarsiger albocoeruleus",
    },
}


LOCATION_BIRD_NAMES: Dict[str, List[str]] = {
    "密云区繁殖鸟类": """
环颈雉 勺鸡 斑嘴鸭 绿头鸭 鸳鸯 小䴙䴘 凤头䴙䴘 山斑鸠 灰斑鸠 珠颈斑鸠 岩鸽
普通夜鹰 普通雨燕 噪鹃 四声杜鹃 大杜鹃 大鹰鹃 小鸦鹃 北棕腹鹰鹃 东方中杜鹃
黑水鸡 白骨顶 普通秧鸡 白胸苦恶鸟 红胸田鸡 鹮嘴鹬 黑翅长脚鹬 长嘴剑鸻 金眶鸻
彩鹬 白腰草鹬 普通燕鸥 灰翅浮鸥 白翅浮鸥 白额燕鸥 黑鹳 普通鸬鹚 白鹭 绿鹭
池鹭 苍鹭 大白鹭 夜鹭 牛背鹭 中白鹭 黄斑苇鳽 栗苇鳽 赤腹鹰 灰脸鵟鹰 黑鸢 金雕
日本松雀鹰 雕鸮 纵纹腹小鸮 红角鸮 灰林鸮 戴胜 三宝鸟 普通翠鸟 冠鱼狗 斑鱼狗 蓝翡翠
大斑啄木鸟 灰头绿啄木鸟 星头啄木鸟 小星头啄木鸟 白背啄木鸟 红脚隼 红隼 燕隼
黑枕黄鹂 小灰山椒鸟 长尾山椒鸟 黑卷尾 发冠卷尾 寿带 红尾伯劳 棕背伯劳 喜鹊
红嘴蓝鹊 大嘴乌鸦 灰喜鹊 松鸦 红嘴山鸦 大山雀 沼泽山雀 黄腹山雀 褐头山雀 煤山雀
中华攀雀 棕扇尾莺 东方大苇莺 黑眉苇莺 厚嘴苇莺 北短翅蝗莺 家燕 金腰燕 岩燕
烟腹毛脚燕 白头鹎 冕柳莺 冠纹柳莺 云南柳莺 淡眉柳莺 棕眉柳莺 乌嘴柳莺 远东树莺
鳞头树莺 银喉长尾山雀 棕头鸦雀 山鹛 暗绿绣眼鸟 山噪鹛 普通䴓 黑头䴓 鹪鹩 褐河乌
灰椋鸟 八哥 乌鸫 灰翅鸫 褐头鸫 宝兴歌鸫 北红尾鸲 白眉姬鹟 蓝矶鸫 绿背姬鹟
红尾水鸲 蓝歌鸲 白腹短翅鸲 白腹暗蓝鹟 麻雀 山麻雀 白鹡鸰 山鹡鸰 灰鹡鸰 粉红胸鹨
金翅雀 黑尾蜡嘴雀 中华朱雀 三道眉草鹀 灰眉岩鹀 黄喉鹀
""".split(),
    "门头沟区繁殖鸟类": """
环颈雉 石鸡 勺鸡 褐马鸡 绿头鸭 鸳鸯 斑嘴鸭 小䴙䴘 凤头䴙䴘 岩鸽 山斑鸠
珠颈斑鸠 灰斑鸠 普通夜鹰 普通雨燕 大鹰鹃 小杜鹃 大杜鹃 噪鹃 四声杜鹃 东方中杜鹃
白胸苦恶鸟 黑水鸡 白骨顶 白腰草鹬 灰翅浮鸥 黑鹳 普通鸬鹚 苍鹭 绿鹭 白鹭 夜鹭 池鹭
大白鹭 金雕 雀鹰 赤腹鹰 灰脸鵟鹰 日本松雀鹰 黑鸢 秃鹫 灰林鸮 北领角鸮 红角鸮 雕鸮
戴胜 三宝鸟 蓝翡翠 普通翠鸟 冠鱼狗 大斑啄木鸟 星头啄木鸟 灰头绿啄木鸟 白背啄木鸟
红隼 燕隼 红脚隼 游隼 黑枕黄鹂 长尾山椒鸟 暗灰鹃鵙 黑卷尾 发冠卷尾 寿带 红尾伯劳
大嘴乌鸦 喜鹊 红嘴山鸦 红嘴蓝鹊 小嘴乌鸦 灰喜鹊 松鸦 星鸦 大山雀 黄腹山雀 褐头山雀
煤山雀 沼泽山雀 中华攀雀 棕扇尾莺 东方大苇莺 黑眉苇莺 厚嘴苇莺 北短翅蝗莺 中华短翅蝗莺
岩燕 家燕 金腰燕 烟腹毛脚燕 白头鹎 冠纹柳莺 云南柳莺 棕眉柳莺 冕柳莺 淡尾鹟莺 淡眉柳莺
暗绿柳莺 远东树莺 鳞头树莺 银喉长尾山雀 棕头鸦雀 山鹛 暗绿绣眼鸟 山噪鹛 普通䴓 黑头䴓
鹪鹩 褐河乌 灰椋鸟 宝兴歌鸫 褐头鸫 乌鸫 北红尾鸲 白眉姬鹟 绿背姬鹟 蓝矶鸫 红尾水鸲
白腹暗蓝鹟 蓝歌鸲 紫啸鸫 白喉矶鸫 白腹短翅鸲 祁连山蓝尾鸲 锈胸蓝姬鹟 麻雀 山麻雀
白鹡鸰 灰鹡鸰 粉红胸鹨 山鹡鸰 金翅雀 中华朱雀 灰眉岩鹀 三道眉草鹀 黄喉鹀
""".split(),
}


def load_bird_maps() -> Tuple[Dict[str, Dict[str, str]], Dict[str, Dict[str, str]]]:
    by_chinese: Dict[str, Dict[str, str]] = {}
    by_slug: Dict[str, Dict[str, str]] = {}
    lines = [
        line
        for line in ALL_BIRDS_CSV.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    reader = csv.DictReader(
        lines,
        fieldnames=[
            "slug",
            "chinese_name",
            "english_name",
            "scientific_name",
            "wikipedia_page",
        ],
    )
    for row in reader:
        slug = row["slug"].strip().strip('"')
        chinese = row["chinese_name"].strip().strip('"')
        if not slug or slug == "slug":
            continue
        info = {
            "slug": slug,
            "chinese_name": chinese,
            "english_name": row["english_name"].strip().strip('"'),
            "scientific_name": row["scientific_name"].strip().strip('"'),
            "wikipedia_page": row["wikipedia_page"].strip(),
        }
        by_slug.setdefault(slug, info)
        if chinese:
            # Keep the first occurrence; later duplicate rows sometimes point to
            # older alternate slugs without sounds.
            by_chinese.setdefault(chinese, info)
    return by_chinese, by_slug


def resolve_birds(
    bird_names: Sequence[str],
    by_chinese: Dict[str, Dict[str, str]],
) -> Tuple[List[Dict[str, str]], List[str]]:
    birds: List[Dict[str, str]] = []
    unresolved: List[str] = []
    for chinese_name in bird_names:
        info = by_chinese.get(chinese_name)
        if not info and chinese_name in MANUAL_BIRD_INFO:
            manual = MANUAL_BIRD_INFO[chinese_name]
            info = {
                "slug": manual["slug"],
                "chinese_name": chinese_name,
                "english_name": manual["english_name"],
                "scientific_name": manual["scientific_name"],
                "wikipedia_page": manual["english_name"].replace(" ", "_"),
            }
        if info:
            birds.append(info)
        else:
            unresolved.append(chinese_name)
    return birds, unresolved


def iter_unique_birds(locations: Dict[str, List[Dict[str, str]]]) -> Iterable[Dict[str, str]]:
    seen = set()
    for birds in locations.values():
        for bird in birds:
            slug = bird["slug"]
            if slug in seen:
                continue
            seen.add(slug)
            yield bird


def append_missing_all_birds_rows(birds: Iterable[Dict[str, str]], by_slug: Dict[str, Dict[str, str]]) -> int:
    rows = []
    for bird in birds:
        if bird["slug"] in by_slug:
            continue
        rows.append(
            f'{bird["slug"]},"{bird["chinese_name"]}","{bird["english_name"]}",'
            f'"{bird["scientific_name"]}",{bird["wikipedia_page"]}\n'
        )

    if not rows:
        return 0

    with ALL_BIRDS_CSV.open("a", encoding="utf-8") as f:
        f.writelines(rows)
    return len(rows)


def write_processing_csv(birds: Iterable[Dict[str, str]]) -> Path:
    tmp_dir = PROJECT_ROOT / "tmp"
    tmp_dir.mkdir(exist_ok=True)
    csv_path = tmp_dir / "beijing_breeding_pdf_birds.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        f.write("# slug,chinese_name,english_name,scientific_name,wikipedia_page\n")
        writer = csv.writer(f)
        for bird in sorted(birds, key=lambda item: item["slug"]):
            writer.writerow(
                [
                    bird["slug"],
                    bird["chinese_name"],
                    bird["english_name"],
                    bird["scientific_name"],
                    bird["wikipedia_page"],
                ]
            )
    return csv_path


def update_bird_info_from_csv(csv_path: Path) -> int:
    updated = 0
    data_lines = [
        line
        for line in csv_path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    reader = csv.DictReader(
        data_lines,
        fieldnames=[
            "slug",
            "chinese_name",
            "english_name",
            "scientific_name",
            "wikipedia_page",
        ],
    )
    for row in reader:
        slug = row["slug"].strip()
        json_file = CLOUDINARY_DIR / f"{slug}_cloudinary_urls.json"
        if not json_file.exists():
            continue
        data = json.loads(json_file.read_text(encoding="utf-8"))
        desired = {
            "slug": slug,
            "chinese_name": row["chinese_name"].strip(),
            "english_name": row["english_name"].strip(),
            "scientific_name": row["scientific_name"].strip(),
        }
        if data.get("bird_info") != desired:
            data["bird_info"] = desired
            json_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            updated += 1
    return updated


def backfill_media(birds: Sequence[Dict[str, str]], skip_media: bool) -> None:
    csv_path = write_processing_csv(birds)
    process_new_birds.merge_with_all_birds_csv(csv_path)

    if skip_media:
        print("⏭️  跳过图片和声音补齐")
        return

    missing_images = process_new_birds.check_missing_birds(csv_path)
    if missing_images:
        process_new_birds.download_birds(csv_path, missing_images)

    missing_cloudinary = process_new_birds.check_missing_cloudinary(csv_path)
    if missing_cloudinary:
        process_new_birds.upload_to_cloudinary(missing_cloudinary, csv_path)

    updated = update_bird_info_from_csv(csv_path)
    print(f"✅ 已更新 {updated} 个 cloudinary JSON 的 bird_info")
    process_new_birds.update_all_birds_csv()
    process_new_birds.generate_html(priority_slugs=[bird["slug"] for bird in birds])

    target_slugs = [bird["slug"] for bird in birds]
    success, failed = auto_sounds_refresh.download_and_upload_sounds(
        target_slugs,
        PROJECT_ROOT / "tmp" / "beijing_breeding_sounds",
    )
    auto_sounds_refresh.print_sounds_summary(success, failed)


def copy_location_json(location_birds: Dict[str, List[Dict[str, str]]]) -> Dict[str, List[str]]:
    missing_by_location: Dict[str, List[str]] = {}
    for location, birds in location_birds.items():
        target_dir = LOCATION_BIRDS_ROOT / "北京" / location / DATE_FOLDER
        target_dir.mkdir(parents=True, exist_ok=True)
        missing: List[str] = []
        for bird in birds:
            src = CLOUDINARY_DIR / f"{bird['slug']}_cloudinary_urls.json"
            if not src.exists():
                missing.append(f"{bird['chinese_name']} ({bird['slug']})")
                continue
            shutil.copy2(src, target_dir / src.name)
        missing_by_location[location] = missing
        print(f"📍 {location}: 写入 {len(birds) - len(missing)}/{len(birds)} 种")
    return missing_by_location


def generate_manifest() -> None:
    subprocess.run(
        ["node", "scripts/generate-location-birds-manifest.js"],
        cwd=QUIZ_ROOT,
        check=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--skip-media",
        action="store_true",
        help="只复制已有 JSON，不下载/上传缺失图片和声音",
    )
    args = parser.parse_args()

    by_chinese, by_slug = load_bird_maps()
    location_birds: Dict[str, List[Dict[str, str]]] = {}
    unresolved_all: Dict[str, List[str]] = {}

    for location, names in LOCATION_BIRD_NAMES.items():
        birds, unresolved = resolve_birds(names, by_chinese)
        location_birds[location] = birds
        unresolved_all[location] = unresolved
        print(f"📋 {location}: PDF {len(names)} 种，已解析 {len(birds)} 种")

    unresolved = {loc: names for loc, names in unresolved_all.items() if names}
    if unresolved:
        print("❌ 还有鸟名无法解析:")
        for location, names in unresolved.items():
            print(f"  {location}: {', '.join(names)}")
        return 1

    unique_birds = list(iter_unique_birds(location_birds))
    added_rows = append_missing_all_birds_rows(unique_birds, by_slug)
    if added_rows:
        print(f"✅ 已向 all_birds.csv 追加 {added_rows} 个缺失物种")

    backfill_media(unique_birds, args.skip_media)
    missing_by_location = copy_location_json(location_birds)
    generate_manifest()

    any_missing = False
    for location, missing in missing_by_location.items():
        if missing:
            any_missing = True
            print(f"⚠️  {location} 仍缺少 {len(missing)} 个 JSON: {', '.join(missing)}")

    return 1 if any_missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
