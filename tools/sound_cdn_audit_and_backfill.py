#!/usr/bin/env python3
"""
按地点审计 bird JSON 中 sounds.url 在「当前 Cloud」上是否可访问（与前端 rewriteCloudinaryMediaUrl 一致），
并可批量从 Macaulay 重新拉取 mp3 上传到 Cloudinary，写回 cloudinary_uploads 并同步到 feather-flash-quiz。

审计：
  python3 tools/sound_cdn_audit_and_backfill.py audit \\
    --out tmp/sound_audit_report.json

补传（需 .cloudinary_secrets；可先 --dry-run）：
  python3 tools/sound_cdn_audit_and_backfill.py backfill --dry-run
  python3 tools/sound_cdn_audit_and_backfill.py backfill --slugs japanese_tit,pallass_leaf_warbler
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
LOCATION_BIRDS = REPO_ROOT / "feather-flash-quiz" / "location_birds"
UPLOADS_DIR = REPO_ROOT / "cloudinary_uploads"
LEGACY_CLOUD = "dzor6lhz8"
VERSION_RE = re.compile(r"/v\d+/")

sys.path.insert(0, str(REPO_ROOT / "tools"))


def rewrite_cloudinary_media_url(url: str, override_cloud: str) -> str:
    """与 feather-flash-quiz/src/lib/cloudinaryUrl.ts 一致。"""
    if not override_cloud or override_cloud == LEGACY_CLOUD:
        return url
    needle = f"https://res.cloudinary.com/{LEGACY_CLOUD}/"
    if not url.startswith(needle):
        return url
    path = url[len(needle) :]
    clean_path = VERSION_RE.sub("/", path)
    return f"https://res.cloudinary.com/{override_cloud}/{clean_path}"


def http_ok(url: str, timeout: float = 25.0) -> tuple[bool, int, str]:
    """
    用 curl 检测（与「浏览器/终端可访问」一致；避免部分环境 Python SSL 链异常导致全失败）。
    成功：200/206/3xx；失败：其它或无响应。
    """
    import subprocess

    try:
        r = subprocess.run(
            [
                "curl",
                "-sS",
                "-o",
                "/dev/null",
                "-w",
                "%{http_code}",
                "--max-time",
                str(int(timeout)),
                "-L",
                url,
            ],
            capture_output=True,
            text=True,
            timeout=timeout + 5,
        )
        code_str = (r.stdout or "").strip()
        if not code_str.isdigit():
            return False, 0, (r.stderr or "curl no code").strip()[:200]
        code = int(code_str)
        ok = 200 <= code < 400 or code == 416  # Range Not Satisfiable 也算拿到资源
        return ok, code, ""
    except subprocess.TimeoutExpired:
        return False, 0, "timeout"
    except FileNotFoundError:
        return False, 0, "curl not found"
    except Exception as e:
        return False, 0, str(e)[:200]


def resolve_target_cloud(explicit: str | None) -> str:
    if explicit and explicit.strip():
        return explicit.strip()
    from cloudinary_credentials import try_resolve_cloud_name_for_gallery

    cn = try_resolve_cloud_name_for_gallery()
    if cn:
        return cn
    raise SystemExit(
        "未指定目标 cloud：请传 --cloud dunr50niz，或设置 VITE_CLOUDINARY_CLOUD_NAME / .cloudinary_secrets 的 CLOUD_NAME"
    )


def location_key(json_path: Path) -> str:
    """北京/圆明园/260423"""
    rel = json_path.relative_to(LOCATION_BIRDS)
    parts = rel.parts
    if len(parts) < 2:
        return str(rel.parent)
    return str(Path(*parts[:-1]))


def iter_location_bird_jsons() -> list[Path]:
    if not LOCATION_BIRDS.is_dir():
        return []
    return sorted(LOCATION_BIRDS.rglob("*_cloudinary_urls.json"))


def audit_one_sound(
    raw_url: str, cloud: str
) -> tuple[str, bool, int, str]:
    effective = rewrite_cloudinary_media_url(raw_url, cloud)
    ok, code, err = http_ok(effective)
    return effective, ok, code, err


def cmd_audit(args: argparse.Namespace) -> int:
    cloud = resolve_target_cloud(args.cloud)
    print(f"目标 cloud（用于重写旧链接）: {cloud}\n")

    # 阶段 1：只读盘，收集待检测记录（同一 effective URL 多次出现只 HTTP 一次）
    pending: list[dict[str, Any]] = []
    unique_eff: set[str] = set()

    for jf in iter_location_bird_jsons():
        try:
            data = json.loads(jf.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"跳过坏 JSON: {jf}: {e}")
            continue
        sounds = data.get("sounds") or []
        if not isinstance(sounds, list):
            continue
        slug = jf.stem.replace("_cloudinary_urls", "")
        loc = location_key(jf)
        bird_name = (data.get("bird_info") or {}).get("chinese_name") or slug

        for idx, s in enumerate(sounds):
            if not isinstance(s, dict):
                continue
            raw_url = s.get("url")
            if not raw_url:
                continue
            eff = rewrite_cloudinary_media_url(raw_url, cloud)
            unique_eff.add(eff)
            pending.append(
                {
                    "slug": slug,
                    "chinese_name": bird_name,
                    "location": loc,
                    "json_file": str(jf.relative_to(REPO_ROOT)),
                    "sound_index": idx,
                    "original_file": s.get("original_file"),
                    "raw_url": raw_url,
                    "effective_url": eff,
                }
            )

    print(f"扫描 JSON 条数: {len(pending)}，唯一声音 URL: {len(unique_eff)}，开始并发 HEAD/GET …")

    url_cache: dict[str, tuple[bool, int, str]] = {}

    def check_one(eff: str) -> tuple[str, tuple[bool, int, str]]:
        if args.sleep > 0:
            time.sleep(args.sleep)
        return eff, http_ok(eff)

    workers = max(1, int(args.workers))
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(check_one, u) for u in sorted(unique_eff)]
        for fut in as_completed(futs):
            eff, result = fut.result()
            url_cache[eff] = result

    by_location: dict[str, list[dict[str, Any]]] = defaultdict(list)
    failed_unique: dict[str, dict] = {}
    total_sounds = len(pending)
    failed_count = 0

    for row in pending:
        eff = row["effective_url"]
        ok, code, err = url_cache[eff]
        rec = {
            **row,
            "http_ok": ok,
            "http_code": code,
            "error": err,
        }
        loc = row["location"]
        slug = row["slug"]
        by_location[loc].append(rec)
        if not ok:
            failed_count += 1
            failed_unique[slug] = rec

    report = {
        "target_cloud": cloud,
        "total_sound_entries_scanned": total_sounds,
        "failed_entries": failed_count,
        "unique_slugs_failed": sorted(failed_unique.keys()),
        "by_location": {k: v for k, v in sorted(by_location.items())},
        "failed_by_slug": failed_unique,
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已写入: {out_path}")
    print(f"扫描 sounds 条数: {total_sounds}, 不可访问: {failed_count}, 涉及鸟种数: {len(failed_unique)}")

    # 简要按地点打印
    print("\n=== 按地点汇总（仅列出有失败的地点）===\n")
    for loc in sorted(by_location.keys()):
        rows = [r for r in by_location[loc] if not r["http_ok"]]
        if not rows:
            continue
        print(f"【{loc}】 {len(rows)} 条失败")
        for r in rows:
            print(
                f"  - {r['chinese_name']} ({r['slug']})  index={r['sound_index']}  "
                f"code={r['http_code']}  file={r.get('original_file')}"
            )
        print()
    return 0


def sync_json_to_feather_quiz(slug: str) -> int:
    src = UPLOADS_DIR / f"{slug}_cloudinary_urls.json"
    if not src.is_file():
        return 0
    quiz = REPO_ROOT / "feather-flash-quiz"
    n = 0
    for dest in quiz.rglob(f"{slug}_cloudinary_urls.json"):
        shutil.copy2(src, dest)
        n += 1
    return n


def extract_asset_id(sound: dict) -> str | None:
    att = sound.get("attribution") or {}
    sid = att.get("source_id")
    if sid:
        return str(sid).strip()
    orig = sound.get("original_file") or ""
    m = re.search(r"_(\d+)\.(mp3|wav|m4a|ogg)$", orig, re.I)
    if m:
        return m.group(1)
    return None


def cmd_backfill(args: argparse.Namespace) -> int:
    from auto_sounds_refresh import download_sound, upload_sound_to_cloudinary
    from cloudinary_credentials import ensure_cloudinary_config

    ensure_cloudinary_config()
    cloud = resolve_target_cloud(args.cloud)
    temp_root = REPO_ROOT / "tmp" / "sound_backfill_dl"
    temp_root.mkdir(parents=True, exist_ok=True)

    slugs: set[str] = set()
    if args.slugs:
        slugs = {s.strip() for s in args.slugs.split(",") if s.strip()}
    else:
        report_path = Path(args.from_audit or REPO_ROOT / "tmp" / "sound_audit_report.json")
        if not report_path.is_file():
            raise SystemExit(f"未指定 --slugs 且找不到审计报告: {report_path}（请先运行 audit）")
        rep = json.loads(report_path.read_text(encoding="utf-8"))
        slugs = set(rep.get("unique_slugs_failed") or [])

    if not slugs:
        print("没有需要补传的 slug")
        return 0

    print(f"目标 cloud: {cloud}；待处理 slug 数: {len(slugs)}\n", flush=True)

    ok_n = fail_n = 0
    for slug in sorted(slugs):
        jf = UPLOADS_DIR / f"{slug}_cloudinary_urls.json"
        if not jf.is_file():
            print(f"⚠️  无主库 JSON，跳过: {slug}", flush=True)
            fail_n += 1
            continue
        data = json.loads(jf.read_text(encoding="utf-8"))
        sounds = data.get("sounds") or []
        if not sounds:
            print(f"⚠️  {slug}: 无 sounds 字段", flush=True)
            fail_n += 1
            continue

        needs: list[tuple[int, dict]] = []
        for i, s in enumerate(sounds):
            if not isinstance(s, dict):
                continue
            url = s.get("url") or ""
            eff, http_is_ok, _, _ = audit_one_sound(url, cloud)
            if not http_is_ok:
                needs.append((i, s))
                print(f"  待补: [{i}] {eff[:80]}...", flush=True)

        if not needs:
            print(f"✓ {slug}: 声音已可访问，跳过", flush=True)
            continue

        slug_changed = False
        for i, sound in needs:
            asset_id = extract_asset_id(sound)
            if not asset_id:
                print(f"❌ {slug}[{i}]: 无法解析 Macaulay asset id", flush=True)
                fail_n += 1
                continue
            out_path = download_sound(asset_id, temp_root, slug)
            if not out_path or not out_path.is_file():
                print(f"❌ {slug}: Macaulay 下载失败 asset={asset_id}", flush=True)
                fail_n += 1
                continue
            if args.dry_run:
                print(f"  [dry-run] 将上传: {out_path.name} -> Cloudinary", flush=True)
                ok_n += 1
                continue
            info = upload_sound_to_cloudinary(slug, out_path)
            if not info:
                fail_n += 1
                continue
            old_att = sound.get("attribution")
            if old_att and isinstance(old_att, dict):
                for k, v in old_att.items():
                    if info.get("attribution", {}).get(k) in (None, "") and v:
                        info.setdefault("attribution", {})[k] = v
            sounds[i] = info
            slug_changed = True
            print(f"  ✅ {slug}[{i}] 已上传 Cloudinary", flush=True)
            ok_n += 1
            time.sleep(0.2)

        if slug_changed and not args.dry_run:
            data["sounds"] = sounds
            with open(jf, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            ncpy = sync_json_to_feather_quiz(slug)
            print(f"  💾 已写回主库并同步 {ncpy} 份 location JSON", flush=True)

    print(f"\n完成: 成功 {ok_n}, 失败 {fail_n}", flush=True)
    return 0 if fail_n == 0 else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="鸟声音 CDN 审计与补传")
    sub = ap.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("audit", help="扫描 location_birds 下所有 sounds")
    a.add_argument("--out", default="tmp/sound_audit_report.json", help="JSON 报告路径")
    a.add_argument("--cloud", default=None, help="目标 cloud（默认与画廊重写一致）")
    a.add_argument("--workers", type=int, default=16, help="并发检测 URL 数（默认 16）")
    a.add_argument("--sleep", type=float, default=0.0, help="每个 URL 检测前 sleep（单线程调试用，默认 0）")
    a.set_defaults(func=cmd_audit)

    b = sub.add_parser("backfill", help="对不可访问声音从 Macaulay 重下并上传")
    b.add_argument("--cloud", default=None, help="审计用目标 cloud")
    b.add_argument("--slugs", default=None, help="逗号分隔 slug；省略则读 --from-audit")
    b.add_argument("--from-audit", default=None, help="audit 生成的 JSON（默认 tmp/sound_audit_report.json）")
    b.add_argument("--dry-run", action="store_true", help="只检查，不上传")
    b.set_defaults(func=cmd_backfill)

    args = ap.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
