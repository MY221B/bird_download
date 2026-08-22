#!/usr/bin/env python3
"""鸟类图片质检、删除未通过图、不足 3 张时补下。

依赖 taiwan_bird_web 的 bird-photo-qa。默认用其 .venv-bioclip 跑检测。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_QA_PYTHON = Path("/Users/my/代码/taiwan_bird_web/.venv-bioclip/bin/python")
DEFAULT_QA_SRC = Path("/Users/my/代码/taiwan_bird_web/packages/bird_photo_qa/src")
OUT_DIR = PROJECT_ROOT / "tmp" / "photo_qa"
CACHE_DIR = OUT_DIR / "detect_cache"
REJECTED_FILE = OUT_DIR / "rejected_files.txt"
DELETE_LIST = PROJECT_ROOT / "config" / "需要删除图片名单"
WEEKLY_SUMMARY = PROJECT_ROOT / "tmp" / "weekly_refresh" / "latest_summary.json"
QUIZ = PROJECT_ROOT / "feather-flash-quiz"
IMAGES = PROJECT_ROOT / "images"
CLOUDINARY = PROJECT_ROOT / "cloudinary_uploads"
MIN_KEEP_DEFAULT = 3
IMAGE_KEYS = ("macaulay", "inaturalist", "wikimedia", "avibase", "birdphotos")
HOST_PYTHON = os.environ.get("BIRD_DOWNLOAD_PYTHON", sys.executable)


def qa_python() -> Path:
    return Path(os.environ.get("BIRD_PHOTO_QA_PYTHON", str(DEFAULT_QA_PYTHON)))


def qa_src() -> Path:
    return Path(os.environ.get("BIRD_PHOTO_QA_SRC", str(DEFAULT_QA_SRC)))


def ensure_qa_interpreter() -> None:
    """检测关需要 torch，切到 bioclip 虚拟环境；上传仍用原来的 python。"""
    target = qa_python()
    if not target.is_file():
        return
    if Path(sys.executable).resolve() == target.resolve():
        return
    os.environ["BIRD_DOWNLOAD_PYTHON"] = sys.executable
    os.execv(str(target), [str(target), *sys.argv])


def load_bird_photo_qa():
    src = qa_src()
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))
    from bird_photo_qa import evaluate_image, detector_available  # noqa: PLC0415

    return evaluate_image, detector_available


def file_sha1(path: Path) -> str:
    digest = hashlib.sha1()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_all_birds() -> dict[str, dict]:
    sys.path.insert(0, str(PROJECT_ROOT / "tools"))
    from process_new_birds import load_all_birds_csv  # noqa: PLC0415

    return load_all_birds_csv()


def collect_quiz_images(
    slugs: set[str] | None = None,
    *,
    include_master: bool | None = None,
) -> dict[str, dict]:
    by_id: dict[str, dict] = {}
    json_paths = list((QUIZ / "src/data/birds").glob("*_cloudinary_urls.json"))
    json_paths.extend((QUIZ / "location_birds").glob("**/*_cloudinary_urls.json"))
    if include_master is None:
        include_master = slugs is not None
    if include_master:
        json_paths.extend(CLOUDINARY.glob("*_cloudinary_urls.json"))
    for path in json_paths:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        info = data.get("bird_info") or {}
        slug = info.get("slug") or path.name.replace("_cloudinary_urls.json", "")
        if slugs is not None and slug not in slugs:
            continue
        chinese = info.get("chinese_name") or ""
        english = info.get("english_name") or ""
        in_builtin = "src/data/birds" in str(path)
        for source, items in data.items():
            if source not in IMAGE_KEYS or not isinstance(items, list):
                continue
            for item in items:
                if not isinstance(item, dict):
                    continue
                url = item.get("url") or ""
                if "/image/" not in url:
                    continue
                public_id = item.get("public_id") or url
                orig = item.get("original_file") or Path(url).name
                attr = item.get("attribution") or {}
                local = IMAGES / slug / source / orig
                rec = {
                    "public_id": public_id,
                    "slug": slug,
                    "chinese": chinese,
                    "english": english,
                    "source": source,
                    "original_file": orig,
                    "url": url,
                    "local": str(local),
                    "photographer": attr.get("photographer") or "",
                    "credit": attr.get("credit_format") or "",
                    "photographer_url": attr.get("photographer_url") or "",
                    "in_builtin": in_builtin,
                }
                prev = by_id.get(public_id)
                if prev is None:
                    by_id[public_id] = rec
                    continue
                if rec["in_builtin"] and not prev["in_builtin"]:
                    rec["chinese"] = rec["chinese"] or prev["chinese"]
                    rec["english"] = rec["english"] or prev["english"]
                    by_id[public_id] = rec
                elif not prev["chinese"] and rec["chinese"]:
                    prev["chinese"] = rec["chinese"]
                    prev["english"] = rec["english"] or prev["english"]
                if rec["in_builtin"]:
                    prev["in_builtin"] = True
    return by_id


def count_images_by_slug(slugs: set[str] | None = None) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    seen: dict[str, set[str]] = defaultdict(set)
    for rec in collect_quiz_images(slugs).values():
        slug = rec["slug"]
        pid = rec["public_id"]
        if pid in seen[slug]:
            continue
        seen[slug].add(pid)
        counts[slug] += 1
    return dict(counts)


def load_latest_results(path: Path) -> dict[str, dict]:
    latest: dict[str, dict] = {}
    if not path.is_file():
        return latest
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        pid = row.get("public_id")
        if pid:
            latest[pid] = row
    return latest


def load_keep_marks(path: Path | None) -> set[str]:
    if path is None or not path.is_file():
        return set()
    data = json.loads(path.read_text(encoding="utf-8"))
    marks = data.get("marks", data) if isinstance(data, dict) else {}
    return {key for key, value in marks.items() if value == "keep"}


def remaining_reasons(row: dict, min_bird_frac: float) -> list[str]:
    reasons = list(row.get("reasons") or [])
    quality = row.get("quality") or {}
    bird_max = quality.get("bird_max")
    if (
        "quality_small_bird" in reasons
        and isinstance(bird_max, (int, float))
        and bird_max > min_bird_frac
    ):
        reasons = [reason for reason in reasons if reason != "quality_small_bird"]
    return reasons


def decide_drops(
    rows: dict[str, dict],
    keep_marks: set[str],
    min_bird_frac: float = 0.025,
) -> tuple[list[dict], dict]:
    """未通过且不应留下的图。主题过宽但主体 > 2.5%、以及误伤该留的留下。"""
    drops: list[dict] = []
    stats = Counter()
    for pid, row in rows.items():
        orig_keep = bool(row.get("keep"))
        reasons = remaining_reasons(row, min_bird_frac)
        if orig_keep and not reasons:
            stats["already_keep"] += 1
            continue
        if pid in keep_marks:
            stats["keep_marked"] += 1
            continue
        if not reasons:
            stats["keep_relaxed_small"] += 1
            continue
        item = dict(row)
        item["reasons"] = reasons
        drops.append(item)
        stats["drop"] += 1
    return drops, dict(stats)


def write_delete_list(drops: list[dict], dest: Path = DELETE_LIST) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    ids = [row["public_id"] for row in drops if row.get("public_id")]
    if dest.is_file():
        try:
            old = json.loads(dest.read_text(encoding="utf-8"))
            for item in old.get("items") or []:
                pid = item.get("public_id") if isinstance(item, dict) else None
                if pid and pid not in ids:
                    ids.append(pid)
        except (OSError, json.JSONDecodeError, AttributeError):
            pass
    payload = {
        "count": len(ids),
        "items": [{"public_id": pid} for pid in ids],
    }
    dest.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return dest


def append_rejected(drops: list[dict]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    existing = set()
    if REJECTED_FILE.is_file():
        existing = {line.strip() for line in REJECTED_FILE.read_text(encoding="utf-8").splitlines() if line.strip()}
    for row in drops:
        slug = row.get("slug") or ""
        source = row.get("source") or ""
        filename = row.get("original_file") or ""
        if slug and source and filename:
            existing.add(f"{slug}/{source}/{filename}")
    REJECTED_FILE.write_text("\n".join(sorted(existing)) + ("\n" if existing else ""), encoding="utf-8")


def run_delete(delete_file: Path, no_git: bool, no_sync: bool) -> int:
    cmd = ["bash", str(PROJECT_ROOT / "tools" / "delete_images_from_config.sh"), str(delete_file), "-y"]
    if no_git:
        cmd.append("--no-git")
    if no_sync:
        cmd.append("--no-sync")
    print("🗑️  删除未通过图片:", " ".join(cmd))
    import subprocess

    return subprocess.run(cmd, cwd=str(PROJECT_ROOT), check=False).returncode


def resolve_file(rec: dict) -> Path | None:
    local = Path(rec["local"])
    if local.is_file() and local.stat().st_size > 0:
        return local
    return None


def score_images(recs: list[dict], results_path: Path) -> dict[str, dict]:
    evaluate_image, detector_available = load_bird_photo_qa()
    if not detector_available():
        raise SystemExit("bird-photo-qa 检测器不可用：请用 taiwan_bird_web/.venv-bioclip/bin/python 运行")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    results_path.parent.mkdir(parents=True, exist_ok=True)
    start = time.time()
    scored = 0
    with results_path.open("w", encoding="utf-8") as handle:
        for rec in recs:
            path = resolve_file(rec)
            row = {
                "public_id": rec["public_id"],
                "slug": rec["slug"],
                "chinese": rec["chinese"],
                "english": rec["english"],
                "source": rec["source"],
                "original_file": rec["original_file"],
                "url": rec["url"],
                "in_builtin": rec["in_builtin"],
                "file": str(path) if path else None,
            }
            if path is None:
                row.update({"keep": False, "reasons": ["download_failed"], "quality": None})
            else:
                result = evaluate_image(
                    path,
                    source=rec["source"],
                    source_url=rec["photographer_url"] or rec["url"],
                    photographer=rec["photographer"],
                    credit=rec["credit"],
                    sha1=file_sha1(path),
                    cache_dir=CACHE_DIR,
                    quality=True,
                    specimen=True,
                    dead=False,
                )
                payload = result.to_dict()
                row["keep"] = payload["keep"]
                row["reasons"] = payload["reasons"]
                row["quality"] = payload["quality"]
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            handle.flush()
            scored += 1
            if scored % 25 == 0 or scored == len(recs):
                elapsed = time.time() - start
                rate = scored / elapsed if elapsed else 0
                print(f"  质检 {scored}/{len(recs)} ({rate:.2f}/s)", flush=True)
    return load_latest_results(results_path)


def sync_slug_json(slug: str) -> int:
    src = CLOUDINARY / f"{slug}_cloudinary_urls.json"
    if not src.is_file():
        return 0
    master = json.loads(src.read_text(encoding="utf-8"))
    updated = 0
    dests = list((QUIZ / "location_birds").rglob(f"{slug}_cloudinary_urls.json"))
    builtin = QUIZ / "src/data/birds" / f"{slug}_cloudinary_urls.json"
    if builtin.is_file():
        dests.append(builtin)
    for dest in dests:
        try:
            existing = json.loads(dest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            existing = {}
        if "bird_info" in master:
            existing["bird_info"] = master["bird_info"]
        for key in IMAGE_KEYS:
            if key in master:
                existing[key] = master[key]
        dest.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
        updated += 1
    return updated


def download_additional(slugs: list[str], count: int) -> None:
    import subprocess

    birds = load_all_birds()
    env = os.environ.copy()
    env["PHOTO_QA_REJECTED"] = str(REJECTED_FILE)
    token_file = PROJECT_ROOT / "config" / "ebird_token.sh"
    if token_file.is_file() and not env.get("EBIRD_TOKEN"):
        for line in token_file.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("export EBIRD_TOKEN"):
                env["EBIRD_TOKEN"] = line.split("=", 1)[1].strip().strip('"').strip("'")
    for index, slug in enumerate(slugs, 1):
        info = birds.get(slug) or {}
        english = info.get("english_name") or slug.replace("_", " ").title()
        scientific = info.get("scientific_name") or ""
        wiki = info.get("wikipedia_page") or english.replace(" ", "_")
        if not scientific:
            print(f"⚠️  {slug} 缺少学名，跳过补下")
            continue
        print(f"\n📥 补图 [{index}/{len(slugs)}] {slug} 每源 {count} 张")
        cmd = [
            "bash",
            str(PROJECT_ROOT / "tools" / "fetch_four_sources.sh"),
            slug,
            english,
            scientific,
            wiki,
            "--count",
            str(count),
        ]
        result = subprocess.run(cmd, cwd=str(PROJECT_ROOT), env=env, check=False)
        if result.returncode != 0:
            print(f"⚠️  {slug} 下载返回 {result.returncode}")


def upload_slugs(slugs: list[str]) -> None:
    import subprocess

    for slug in slugs:
        print(f"☁️  上传 {slug}")
        result = subprocess.run(
            [HOST_PYTHON, str(PROJECT_ROOT / "tools" / "upload_to_cloudinary.py"), slug],
            cwd=str(PROJECT_ROOT),
            check=False,
        )
        if result.returncode != 0:
            print(f"⚠️  {slug} 上传返回 {result.returncode}")
            continue
        copied = sync_slug_json(slug)
        print(f"   已同步 JSON 到 {copied} 个地点/内置副本")


def short_species(min_keep: int, slugs: set[str] | None = None) -> list[tuple[str, int]]:
    counts = count_images_by_slug(slugs)
    if slugs is not None:
        for slug in slugs:
            counts.setdefault(slug, 0)
    return sorted(
        ((slug, n) for slug, n in counts.items() if n < min_keep),
        key=lambda item: (item[1], item[0]),
    )


def qa_and_delete(
    slugs: set[str] | None,
    *,
    no_git: bool,
    no_sync: bool,
    keep_marks: set[str],
) -> tuple[list[dict], dict[str, dict]]:
    inventory = collect_quiz_images(slugs)
    recs = list(inventory.values())
    print(f"🔎 质检 {len(recs)} 张图")
    results_path = OUT_DIR / "results.jsonl"
    latest = score_images(recs, results_path)
    drops, stats = decide_drops(latest, keep_marks)
    print(f"   结果: {stats}")
    if not drops:
        print("✅ 没有需要删除的图")
        return [], latest
    write_delete_list(drops)
    append_rejected(drops)
    code = run_delete(DELETE_LIST, no_git=no_git, no_sync=no_sync)
    if code != 0:
        print(f"⚠️  删除脚本退出码 {code}")
    return drops, latest


def supplement_until_min(
    short: list[tuple[str, int]],
    *,
    min_keep: int,
    no_git: bool,
    no_sync: bool,
    keep_marks: set[str],
) -> list[dict]:
    still: list[dict] = []
    if not short:
        return still
    rounds = [(10, "第一轮每源 10 张"), (20, "第二轮每源 20 张")]
    remaining = {slug for slug, _ in short}
    birds = load_all_birds()
    for count, label in rounds:
        if not remaining:
            break
        print(f"\n🔁 补图{label}：{len(remaining)} 种")
        download_additional(sorted(remaining), count)
        upload_slugs(sorted(remaining))
        qa_and_delete(remaining, no_git=no_git, no_sync=no_sync, keep_marks=keep_marks)
        still_short = short_species(min_keep, remaining)
        remaining = {slug for slug, _ in still_short}
        print("   本轮后仍不足:", still_short or "无")
    for slug in sorted(remaining):
        info = birds.get(slug) or {}
        still.append(
            {
                "slug": slug,
                "chinese": info.get("chinese_name") or "",
                "english": info.get("english_name") or "",
                "count": count_images_by_slug({slug}).get(slug, 0),
            }
        )
    return still


def merge_weekly_summary(photo_qa: dict) -> None:
    if not WEEKLY_SUMMARY.is_file():
        return
    try:
        data = json.loads(WEEKLY_SUMMARY.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return
    data["photo_qa"] = photo_qa
    WEEKLY_SUMMARY.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="图片质检、删除未通过、不足则补下")
    parser.add_argument("--from-results", type=Path, help="已有 results.jsonl，不再跑检测")
    parser.add_argument("--marks", type=Path, help="审阅页导出的误伤该留 JSON")
    parser.add_argument("--slugs", default="", help="逗号分隔 slug；空则扫描网页全部图")
    parser.add_argument("--from-weekly-summary", type=Path, help="周更新摘要，质检其中的新鸟")
    parser.add_argument("--delete", action="store_true", help="调用删除脚本去掉未通过图")
    parser.add_argument("--supplement", action="store_true", help="不足 3 张则补下")
    parser.add_argument("--no-git", action="store_true")
    parser.add_argument("--no-sync", action="store_true")
    parser.add_argument("--min-keep", type=int, default=MIN_KEEP_DEFAULT)
    parser.add_argument("--min-bird-frac", type=float, default=0.025)
    return parser.parse_args()


def main() -> int:
    os.chdir(PROJECT_ROOT)
    args = parse_args()
    if not args.from_results or args.supplement:
        ensure_qa_interpreter()
    keep_marks = load_keep_marks(args.marks)
    slugs: set[str] | None = None
    if args.slugs.strip():
        slugs = {part.strip() for part in args.slugs.split(",") if part.strip()}
    if args.from_weekly_summary and args.from_weekly_summary.is_file():
        summary = json.loads(args.from_weekly_summary.read_text(encoding="utf-8"))
        new_birds = [str(item) for item in (summary.get("new_birds") or []) if item]
        missing_local = set(summary.get("missing_local") or [])
        slugs = {slug for slug in new_birds if slug not in missing_local}
        if not slugs:
            print("ℹ️  本周没有新下载的鸟类图片，跳过质检")
            merge_weekly_summary(
                {
                    "checked": 0,
                    "deleted": 0,
                    "supplemented": [],
                    "still_short": [],
                    "skipped": "no_new_birds",
                }
            )
            return 0
        print(f"📅 周更新新鸟 {len(slugs)} 种，开始质检")

    deleted_ids: list[str] = []
    latest: dict[str, dict] = {}
    if args.from_results:
        latest = load_latest_results(args.from_results)
        drops, stats = decide_drops(latest, keep_marks, args.min_bird_frac)
        print(f"📋 按已有结果判定: {stats}，将删除 {len(drops)} 张", flush=True)
        if args.delete and drops:
            write_delete_list(drops)
            append_rejected(drops)
            run_delete(DELETE_LIST, no_git=args.no_git, no_sync=args.no_sync)
            deleted_ids = [row["public_id"] for row in drops]
        elif drops:
            write_delete_list(drops)
            print(f"已写入 {DELETE_LIST}，未执行删除")
    elif args.delete or args.supplement or slugs is not None:
        drops, latest = qa_and_delete(
            slugs,
            no_git=args.no_git,
            no_sync=args.no_sync,
            keep_marks=keep_marks,
        )
        deleted_ids = [row["public_id"] for row in drops]
    else:
        print("请指定 --from-results、--slugs 或 --from-weekly-summary")
        return 2

    still_short: list[dict] = []
    supplemented: list[str] = []
    if args.supplement:
        scope = slugs
        if args.from_results:
            scope = None
        short = short_species(args.min_keep, scope)
        print(f"📉 去掉未通过后不足 {args.min_keep} 张: {short or '无'}", flush=True)
        supplemented = [slug for slug, _ in short]
        still_short = supplement_until_min(
            short,
            min_keep=args.min_keep,
            no_git=args.no_git,
            no_sync=args.no_sync,
            keep_marks=keep_marks,
        )
        if still_short:
            print("⚠️  补图后仍不足 3 张：")
            for item in still_short:
                name = item["chinese"] or item["english"] or item["slug"]
                print(f"  - {name}（{item['slug']}）现有 {item['count']} 张")

    photo_qa = {
        "checked": len(latest),
        "deleted": len(deleted_ids),
        "keep_marked": len(keep_marks),
        "supplemented": supplemented,
        "still_short": still_short,
    }
    merge_weekly_summary(photo_qa)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "last_run.json").write_text(
        json.dumps(photo_qa, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"✅ 质检管线完成：检查 {photo_qa['checked']}，删除 {photo_qa['deleted']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
