#!/usr/bin/env python3
"""
Download BirdReport activity reports with resume, rate-limit, and retry support.

The script prompts for query time/place on each interactive run.
"""

from __future__ import annotations

import argparse
import base64
import csv
import json
import math
import random
import re
import select
import shutil
import subprocess
import sys
import time
import webbrowser
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, TextIO, Tuple
from urllib.parse import quote

import requests


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TOOLS_PATH = PROJECT_ROOT / "tools"
if str(TOOLS_PATH) not in sys.path:
    sys.path.insert(0, str(TOOLS_PATH))

try:
    from fetch_from_birdreport import (
        decrypt_response_data,
        dict_to_json_sorted,
        get_sign,
        get_uuid,
        prepare_api_payload,
        rsa_encrypt_long,
    )
except Exception as exc:  # pragma: no cover
    raise SystemExit(
        "Failed to import encryption helpers from tools/fetch_from_birdreport.py: "
        f"{exc}"
    )


SEARCH_API_URL = "https://api.birdreport.cn/front/record/activity/search"
REPORT_NUM_API_URL = "https://api.birdreport.cn/front/record/activity/reportNum"

CSV_HEADERS = [
    "reportId",
    "serial_id",
    "state",
    "outside_count",
    "taxoncount",
    "start_time",
    "end_time",
    "userid",
    "username",
    "province_name",
    "city_name",
    "district_name",
    "point_name",
    "request_id",
    "query_province",
    "query_city",
    "query_district",
    "query_pointname",
    "query_start",
    "query_end",
    "query_state",
    "query_sort_by",
    "query_order_by",
    "fetched_page",
    "fetched_at",
]

EST_SECONDS_PER_PAGE = 7.6
EST_PAGES_PER_CAPTCHA = 43.4


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def ensure_dirs(base_dir: Path) -> Dict[str, Path]:
    data_dir = base_dir / "data"
    logs_dir = base_dir / "logs"
    data_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)
    return {"data": data_dir, "logs": logs_dir}


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def atomic_write_json(path: Path, payload: Dict[str, Any]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    tmp.replace(path)


def sanitize_filename_component(value: str) -> str:
    text = (value or "").strip()
    if not text:
        return "未命名"
    text = re.sub(r'[\\\\/:*?"<>|]', "_", text)
    text = re.sub(r"\s+", "", text)
    return text or "未命名"


def compact_date_for_filename(value: str) -> str:
    digits = re.sub(r"\D", "", (value or ""))
    if len(digits) >= 8:
        return digits[:8]
    return "00000000"


def pick_place_name(
    *,
    province: str,
    city: str,
    district: str,
    pointname: str,
) -> str:
    return (
        (pointname or "").strip()
        or (district or "").strip()
        or (city or "").strip()
        or (province or "").strip()
        or "未知地点"
    )


def format_duration(seconds: float) -> str:
    if seconds <= 0:
        return "0秒"
    total = int(round(seconds))
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}小时{m}分{s}秒"
    if m:
        return f"{m}分{s}秒"
    return f"{s}秒"


def build_payload(
    *,
    start: str,
    end: str,
    province: str,
    city: str,
    district: str,
    pointname: str,
    state: str,
    page: int,
    page_size: int,
    sort_by: str,
    order_by: str,
) -> Dict[str, str]:
    raw_payload = {
        "taxonid": "",
        "startTime": start,
        "endTime": end,
        "province": province,
        "city": city,
        "district": district,
        "pointname": pointname,
        "username": "",
        "serial_id": "",
        "ctime": "",
        "version": "CH4",
        "state": state,
        "mode": "0",
        "outside_type": "0",
        "limit": str(page_size),
        "page": str(page),
        "sortBy": sort_by,
        "orderBy": order_by,
    }
    return prepare_api_payload(raw_payload)


def build_report_search_url(query: Dict[str, str]) -> str:
    payload = {
        "taxonid": "",
        "startTime": query["start"],
        "endTime": query["end"],
        "province": query["province"],
        "city": query["city"],
        "district": query["district"],
        "pointname": query["pointname"],
        "username": "",
        "serial_id": "",
        "ctime": "",
        "version": "CH4",
        "state": query["state"],
        "mode": 0,
        "outside_type": 0,
    }
    encoded = base64.b64encode(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).decode("ascii")
    return f"https://www.birdreport.cn/home/search/report.html?search={quote(encoded, safe='')}"


def build_headers(payload_str: str) -> Dict[str, str]:
    timestamp = str(int(time.time() * 1000))
    request_id = get_uuid()
    sign = get_sign(payload_str, request_id, timestamp)
    return {
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Origin": "https://www.birdreport.cn",
        "Referer": "https://www.birdreport.cn/",
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "requestId": request_id,
        "sign": sign,
        "timestamp": timestamp,
    }


def encrypt_payload(payload: Dict[str, str]) -> Tuple[str, str]:
    payload_str = dict_to_json_sorted(payload).replace(" ", "")
    return rsa_encrypt_long(payload_str), payload_str


@dataclass
class PageResult:
    ok: bool
    page: int
    total_count: int = 0
    rows: Optional[List[Dict[str, Any]]] = None
    attempts: int = 0
    status_code: Optional[int] = None
    api_code: Optional[Any] = None
    error: str = ""
    blocked: bool = False


def decode_rows(body: Dict[str, Any]) -> List[Dict[str, Any]]:
    data = body.get("data")
    if not data:
        return []
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return [data]
    if isinstance(data, str):
        decoded = decrypt_response_data(data)
        parsed = json.loads(decoded)
        if isinstance(parsed, list):
            return parsed
        if isinstance(parsed, dict):
            return [parsed]
    return []


def fetch_page(
    *,
    payload: Dict[str, str],
    timeout: int,
) -> PageResult:
    encrypted_body, payload_str = encrypt_payload(payload)
    headers = build_headers(payload_str)
    response = requests.post(
        SEARCH_API_URL,
        headers=headers,
        data=encrypted_body,
        timeout=timeout,
        verify=False,
    )
    status_code = response.status_code
    body = response.json()
    api_code = body.get("code")
    if status_code == 200 and api_code == 0:
        rows = decode_rows(body)
        total_count = int(body.get("count") or 0)
        return PageResult(
            ok=True,
            page=int(payload["page"]),
            total_count=total_count,
            rows=rows,
            attempts=1,
            status_code=status_code,
            api_code=api_code,
        )

    msg = body.get("msg") or ""
    blocked = status_code == 403 or api_code in (403, 405, 505) or "Bad request" in msg
    return PageResult(
        ok=False,
        page=int(payload["page"]),
        attempts=1,
        status_code=status_code,
        api_code=api_code,
        error=f"HTTP {status_code}, api_code={api_code}, msg={msg}",
        blocked=blocked,
    )


def fetch_page_with_retry(
    *,
    payload: Dict[str, str],
    timeout: int,
    max_retries: int,
    blocked_retry_limit: int,
) -> PageResult:
    page = int(payload["page"])
    last_error = ""
    blocked = False
    status_code: Optional[int] = None
    api_code: Optional[Any] = None

    for attempt in range(1, max_retries + 1):
        try:
            result = fetch_page(payload=payload, timeout=timeout)
            result.attempts = attempt
            if result.ok:
                return result
            last_error = result.error
            blocked = blocked or result.blocked
            status_code = result.status_code
            api_code = result.api_code
            if result.blocked and attempt >= blocked_retry_limit:
                return PageResult(
                    ok=False,
                    page=page,
                    attempts=attempt,
                    status_code=status_code,
                    api_code=api_code,
                    error=last_error,
                    blocked=True,
                )
            if blocked:
                wait_s = min(180.0, 20.0 * attempt + random.uniform(0.5, 2.0))
            else:
                wait_s = min(120.0, (2 ** (attempt - 1)) + random.uniform(0.3, 1.2))
        except requests.RequestException as exc:
            last_error = f"request_error: {exc}"
            wait_s = min(120.0, (2 ** (attempt - 1)) + random.uniform(0.3, 1.2))
        except json.JSONDecodeError as exc:
            last_error = f"invalid_json: {exc}"
            wait_s = min(120.0, (2 ** (attempt - 1)) + random.uniform(0.3, 1.2))
        except Exception as exc:  # pragma: no cover
            last_error = f"unexpected_error: {exc}"
            wait_s = min(120.0, (2 ** (attempt - 1)) + random.uniform(0.3, 1.2))

        if attempt < max_retries:
            time.sleep(wait_s)

    return PageResult(
        ok=False,
        page=page,
        attempts=max_retries,
        status_code=status_code,
        api_code=api_code,
        error=last_error,
        blocked=blocked,
    )


def fetch_report_num(payload: Dict[str, str], timeout: int) -> Dict[str, Any]:
    encrypted_body, payload_str = encrypt_payload(payload)
    headers = build_headers(payload_str)
    response = requests.post(
        REPORT_NUM_API_URL,
        headers=headers,
        data=encrypted_body,
        timeout=timeout,
        verify=False,
    )
    response.raise_for_status()
    body = response.json()
    data = body.get("data")
    if isinstance(data, str):
        try:
            return json.loads(decrypt_response_data(data))
        except Exception:
            return {}
    if isinstance(data, dict):
        return data
    return {}


def load_seen_ids(csv_path: Path) -> set:
    seen = set()
    if not csv_path.exists():
        return seen
    with csv_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rid = (row.get("reportId") or "").strip()
            if rid:
                seen.add(rid)
    return seen


def normalize_row(
    row: Dict[str, Any],
    *,
    query: Dict[str, str],
    page: int,
    fetched_at: str,
) -> Dict[str, Any]:
    item = {key: row.get(key, "") for key in CSV_HEADERS}
    item["query_province"] = query["province"]
    item["query_city"] = query["city"]
    item["query_district"] = query["district"]
    item["query_pointname"] = query["pointname"]
    item["query_start"] = query["start"]
    item["query_end"] = query["end"]
    item["query_state"] = query["state"]
    item["query_sort_by"] = query["sort_by"]
    item["query_order_by"] = query["order_by"]
    item["fetched_page"] = page
    item["fetched_at"] = fetched_at
    return item


def write_csv_header_if_needed(csv_path: Path) -> None:
    if csv_path.exists() and csv_path.stat().st_size > 0:
        return
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
        writer.writeheader()


def new_log_file(log_dir: Path, *, prefix: str = "run") -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return log_dir / f"{sanitize_filename_component(prefix)}_{stamp}.log"


def log(msg: str, fp: TextIO) -> None:
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line)
    fp.write(line + "\n")
    fp.flush()


def try_auto_open_browser(url: str, log_fp: TextIO) -> None:
    try:
        opened = webbrowser.open(url, new=2, autoraise=True)
    except Exception as exc:
        log(f"Auto-open browser failed: {exc}", log_fp)
        return
    if opened:
        log("Browser auto-open triggered for captcha page.", log_fp)
    else:
        log("Browser auto-open returned False; please open the URL manually.", log_fp)


def try_play_alert_sound(log_fp: TextIO) -> None:
    try:
        print("\a", end="", flush=True)
    except Exception:
        pass

    afplay = shutil.which("afplay")
    if not afplay:
        return

    for sound_path in (
        "/System/Library/Sounds/Glass.aiff",
        "/System/Library/Sounds/Ping.aiff",
    ):
        if not Path(sound_path).exists():
            continue
        try:
            subprocess.Popen(
                [afplay, sound_path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            log(f"Sound alert triggered: {sound_path}", log_fp)
            return
        except Exception as exc:
            log(f"Sound alert failed on {sound_path}: {exc}", log_fp)


def wait_for_captcha_signal_file(
    signal_path: Path,
    *,
    log_fp: TextIO,
    reminder_seconds: float,
    alert_sound: bool,
    poll_seconds: float = 2.0,
) -> bool:
    """Wait until signal_path exists, then consume it. Used for non-TTY sessions."""
    signal_path = signal_path.resolve()
    signal_path.parent.mkdir(parents=True, exist_ok=True)
    if signal_path.exists():
        signal_path.unlink()
    log(
        "Non-interactive session: waiting for captcha signal file. "
        f"After browser captcha, create: {signal_path}",
        log_fp,
    )
    print(
        f"完成浏览器验证码后执行: touch {signal_path}",
        flush=True,
    )
    reminder_sent = False
    waited = 0.0
    while True:
        if signal_path.exists():
            try:
                signal_path.unlink()
            except FileNotFoundError:
                pass
            log(f"Captcha signal file detected and consumed: {signal_path}", log_fp)
            return True
        time.sleep(poll_seconds)
        waited += poll_seconds
        if reminder_seconds > 0 and not reminder_sent and waited >= reminder_seconds:
            log(
                f"No captcha signal after {reminder_seconds:.1f}s, sending reminder alert.",
                log_fp,
            )
            if alert_sound:
                try_play_alert_sound(log_fp)
            reminder_sent = True


def prompt_manual_captcha(
    *,
    query: Dict[str, str],
    page: int,
    log_fp: TextIO,
    reason: str,
    auto_open_browser: bool,
    alert_sound: bool,
    reminder_seconds: float,
    signal_path: Optional[Path] = None,
    auto_solve: bool = True,
    auto_solve_attempts: int = 8,
    captcha_reader: str = "ocr_then_agent",
    captcha_agent_wait: float = 180.0,
    captcha_pending_dir: Optional[Path] = None,
) -> bool:
    url = build_report_search_url(query)
    log(
        f"Manual captcha required ({reason}). Pause before page {page}.",
        log_fp,
    )

    if auto_solve:
        try:
            from auto_captcha import solve_visited_captcha
        except Exception as exc:
            log(f"Auto captcha import failed: {exc}", log_fp)
        else:
            log(
                f"Trying auto captcha solve "
                f"(reader={captcha_reader}, max_attempts={auto_solve_attempts})...",
                log_fp,
            )
            result = solve_visited_captcha(
                max_attempts=auto_solve_attempts,
                log_fp=log_fp,
                reader=captcha_reader,
                pending_dir=captcha_pending_dir,
                agent_wait_seconds=captcha_agent_wait,
            )
            if result.ok:
                log(
                    f"Auto captcha solved in {result.attempts} attempt(s). "
                    f"method={result.method} code={result.code}",
                    log_fp,
                )
                return True
            log(
                f"Auto captcha failed after {result.attempts} attempt(s): "
                f"{result.message}. Falling back to manual.",
                log_fp,
            )

    log(f"Open this URL in browser and complete captcha:\n{url}", log_fp)
    if auto_open_browser:
        try_auto_open_browser(url, log_fp)
    if alert_sound:
        try_play_alert_sound(log_fp)
    if not sys.stdin or not sys.stdin.isatty():
        if signal_path is None:
            log("Non-interactive session; cannot wait for captcha input.", log_fp)
            return False
        return wait_for_captcha_signal_file(
            signal_path,
            log_fp=log_fp,
            reminder_seconds=reminder_seconds,
            alert_sound=alert_sound,
        )
    try:
        print("完成验证码后输入 y 并回车继续（Ctrl+C 退出）: ", end="", flush=True)
        reminder_sent = False
        while True:
            timeout: Optional[float]
            if reminder_seconds > 0 and not reminder_sent:
                timeout = reminder_seconds
            else:
                timeout = None

            ready, _, _ = select.select([sys.stdin], [], [], timeout)
            if ready:
                line = sys.stdin.readline()
                if line == "":
                    log("EOF received while waiting captcha input; stop.", log_fp)
                    return False
                if line.strip().lower() == "y":
                    return True
                log("Input is not 'y'; keep waiting for confirmation.", log_fp)
                print("请输入 y 并回车继续: ", end="", flush=True)

            if reminder_seconds > 0 and not reminder_sent:
                log(
                    f"No confirmation after {reminder_seconds:.1f}s, sending reminder alert.",
                    log_fp,
                )
                if alert_sound:
                    try_play_alert_sound(log_fp)
                reminder_sent = True
    except EOFError:
        log("EOF received while waiting captcha input; stop.", log_fp)
        return False


def save_checkpoint(
    checkpoint_path: Path,
    checkpoint: Dict[str, Any],
) -> None:
    checkpoint["updated_at"] = now_utc_iso()
    atomic_write_json(checkpoint_path, checkpoint)


def run_post_process(
    *,
    project_dir: Path,
    input_csv: Path,
    output_csv: Path,
    place_name: str,
    log_fp: TextIO,
) -> bool:
    script = project_dir / "build_point_period_stats.py"
    if not script.exists():
        log(f"Post-process script not found: {script}", log_fp)
        return False

    cmd = [
        sys.executable,
        str(script),
        "--input-csv",
        str(input_csv),
        "--output-csv",
        str(output_csv),
        "--place-name",
        place_name,
    ]
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=str(project_dir),
    )
    if result.stdout.strip():
        log(f"Post-process stdout:\n{result.stdout.strip()}", log_fp)
    if result.stderr.strip():
        log(f"Post-process stderr:\n{result.stderr.strip()}", log_fp)
    if result.returncode != 0:
        log(f"Post-process failed with code {result.returncode}.", log_fp)
        return False
    log(f"Post-process output written to: {output_csv}", log_fp)
    return True


def cleanup_runtime_artifacts(
    *,
    checkpoint_path: Path,
    summary_path: Path,
    log_path: Path,
    logs_dir: Path,
) -> None:
    for path in (checkpoint_path, summary_path, log_path):
        if path.exists():
            path.unlink()

    if logs_dir.exists():
        for log_file in logs_dir.glob("*.log"):
            if log_file.exists():
                log_file.unlink()
        try:
            logs_dir.rmdir()
        except OSError:
            pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download city reports from birdreport with resume/retry/rate-limit.",
    )
    parser.add_argument("--start", default="")
    parser.add_argument("--end", default="")
    parser.add_argument("--province", default="")
    parser.add_argument("--city", default="")
    parser.add_argument("--district", default="")
    parser.add_argument("--pointname", default="")
    parser.add_argument(
        "--state",
        default="2",
        help='Report visibility filter. Use "2" for public-only, empty string for all.',
    )
    parser.add_argument("--page-size", type=int, default=50)
    parser.add_argument("--sort-by", default="serial_id")
    parser.add_argument("--order-by", default="asc")
    parser.add_argument("--output-dir", default=".")
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--max-retries", type=int, default=5)
    parser.add_argument(
        "--blocked-retry-limit",
        type=int,
        default=2,
        help="Stop page retry early after this many blocked responses.",
    )
    parser.add_argument("--min-sleep", type=float, default=1.2)
    parser.add_argument("--max-sleep", type=float, default=2.0)
    parser.add_argument("--batch-pages", type=int, default=30)
    parser.add_argument("--batch-cooldown-min", type=float, default=6.0)
    parser.add_argument("--batch-cooldown-max", type=float, default=12.0)
    parser.add_argument(
        "--captcha-every",
        type=int,
        default=0,
        help="Proactively pause every N successful pages for manual captcha verification. 0 disables.",
    )
    parser.add_argument(
        "--max-captcha-prompts",
        type=int,
        default=50,
        help="Maximum total manual captcha prompts before hard stop.",
    )
    parser.add_argument("--max-pages", type=int, default=0, help="0 means no limit.")
    parser.add_argument(
        "--resume",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Resume from checkpoint when query settings are identical.",
    )
    parser.add_argument(
        "--interactive-captcha",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="When blocked or near threshold, pause and wait for manual captcha confirmation.",
    )
    parser.add_argument(
        "--auto-open-browser",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Try to auto-open captcha URL in browser when manual verification is required.",
    )
    parser.add_argument(
        "--alert-sound",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Play a local sound alert when manual captcha verification is required.",
    )
    parser.add_argument(
        "--captcha-reminder-seconds",
        type=float,
        default=15.0,
        help="Send one extra sound reminder if captcha confirmation is not received in N seconds. 0 disables.",
    )
    parser.add_argument(
        "--auto-captcha",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Auto OCR+submit BirdReport visited captcha before falling back to manual.",
    )
    parser.add_argument(
        "--auto-captcha-attempts",
        type=int,
        default=8,
        help="Max OCR/verify attempts per blocked event.",
    )
    parser.add_argument(
        "--captcha-reader",
        choices=("ocr", "agent", "ocr_then_agent"),
        default="ocr_then_agent",
        help="How to read captcha digits. ocr_then_agent falls back to agent vision files.",
    )
    parser.add_argument(
        "--captcha-agent-wait",
        type=float,
        default=180.0,
        help="Seconds to wait for captcha_answer.txt when using agent vision.",
    )
    parser.add_argument(
        "--post-process",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Run build_point_period_stats.py after fetch is completed.",
    )
    parser.add_argument(
        "--cleanup-runtime-artifacts",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Delete checkpoint/summary/log files after a successful run.",
    )
    parser.add_argument(
        "--stop-on-blocked",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Stop immediately when blocked responses keep happening.",
    )
    return parser.parse_args()


def prompt_value(
    *,
    label: str,
    default: str,
    required: bool,
) -> str:
    while True:
        suffix = f" [{default}]" if default else ""
        raw = input(f"{label}{suffix}: ").strip()
        if raw:
            return raw
        if default:
            return default
        if not required:
            return ""
        print(f"{label} 不能为空，请重新输入。")


def resolve_query_inputs(args: argparse.Namespace) -> None:
    if not sys.stdin or not sys.stdin.isatty():
        if not args.start or not args.end or not args.province:
            raise SystemExit(
                "Non-interactive mode requires --start --end --province."
            )
        return

    print("请输入本次查询条件（每次运行都会询问）：")
    args.start = prompt_value(
        label="开始日期(YYYY-MM-DD)",
        default=args.start,
        required=True,
    )
    args.end = prompt_value(
        label="结束日期(YYYY-MM-DD)",
        default=args.end,
        required=True,
    )
    args.province = prompt_value(
        label="省份/直辖市(如: 北京市)",
        default=args.province,
        required=True,
    )
    args.city = prompt_value(
        label="城市(可选)",
        default=args.city,
        required=False,
    )
    args.district = prompt_value(
        label="区县(可选)",
        default=args.district,
        required=False,
    )
    args.pointname = prompt_value(
        label="观鸟点名称(可选)",
        default=args.pointname,
        required=False,
    )


def main() -> int:
    args = parse_args()
    resolve_query_inputs(args)

    if args.page_size > 50:
        print("page_size > 50 is not supported by this endpoint, forcing to 50.")
        args.page_size = 50
    if args.page_size < 1:
        raise SystemExit("page_size must be >= 1")
    if args.min_sleep < 0 or args.max_sleep < args.min_sleep:
        raise SystemExit("Invalid sleep settings.")
    if args.batch_pages < 1:
        raise SystemExit("batch_pages must be >= 1")
    if args.blocked_retry_limit < 1:
        raise SystemExit("blocked-retry-limit must be >= 1")
    if args.captcha_every < 0:
        raise SystemExit("captcha-every must be >= 0")
    if args.max_captcha_prompts < 1:
        raise SystemExit("max-captcha-prompts must be >= 1")
    if args.captcha_reminder_seconds < 0:
        raise SystemExit("captcha-reminder-seconds must be >= 0")
    if args.auto_captcha_attempts < 1:
        raise SystemExit("auto-captcha-attempts must be >= 1")
    if args.captcha_agent_wait < 0:
        raise SystemExit("captcha-agent-wait must be >= 0")

    base_dir = Path(args.output_dir).resolve()
    script_dir = Path(__file__).resolve().parent
    dirs = ensure_dirs(base_dir)
    data_dir = dirs["data"]
    logs_dir = dirs["logs"]

    query = {
        "start": args.start,
        "end": args.end,
        "province": args.province,
        "city": args.city,
        "district": args.district,
        "pointname": args.pointname,
        "state": args.state,
        "page_size": str(args.page_size),
        "sort_by": args.sort_by,
        "order_by": args.order_by,
    }

    place_name = pick_place_name(
        province=args.province,
        city=args.city,
        district=args.district,
        pointname=args.pointname,
    )
    safe_place_name = sanitize_filename_component(place_name)
    start_compact = compact_date_for_filename(args.start)
    end_compact = compact_date_for_filename(args.end)
    file_prefix = f"{safe_place_name}_{start_compact}-{end_compact}"

    checkpoint_path = base_dir / f"{file_prefix}_checkpoint.json"
    summary_path = base_dir / f"{file_prefix}_summary.json"
    csv_path = data_dir / f"{file_prefix}_报告索引.csv"
    jsonl_path = data_dir / f"{file_prefix}_报告原始.jsonl"
    processed_path = data_dir / f"{file_prefix}_分时段鸟点排名.csv"
    captcha_signal_path = base_dir / f"{file_prefix}_captcha_continue"
    log_path = new_log_file(logs_dir, prefix=file_prefix)

    write_csv_header_if_needed(csv_path)
    seen_ids = load_seen_ids(csv_path)

    checkpoint: Dict[str, Any] = {}
    if args.resume and checkpoint_path.exists():
        old = load_json(checkpoint_path, {})
        if old.get("query") == query:
            checkpoint = old
        else:
            backup = checkpoint_path.with_name(
                f"{file_prefix}_checkpoint_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            )
            checkpoint_path.replace(backup)

    start_page = int(checkpoint.get("next_page", 1))
    expected_count = int(checkpoint.get("expected_count", 0))
    expected_pages = int(checkpoint.get("expected_pages", 0))
    fetched_pages = int(checkpoint.get("fetched_pages", 0))
    total_rows = int(checkpoint.get("total_rows", 0))
    new_rows = int(checkpoint.get("new_rows", 0))
    duplicate_rows = int(checkpoint.get("duplicate_rows", 0))
    failed_pages = list(checkpoint.get("failed_pages", []))
    requests_since_captcha = int(checkpoint.get("requests_since_captcha", 0))
    manual_captcha_count = int(checkpoint.get("manual_captcha_count", 0))

    run_started_at = now_utc_iso()
    should_cleanup_runtime = False

    with log_path.open("w", encoding="utf-8") as log_fp:
        log(f"Output dir: {base_dir}", log_fp)
        log(f"CSV: {csv_path}", log_fp)
        log(f"RAW JSONL: {jsonl_path}", log_fp)
        log(
            "Query: "
            + json.dumps(
                query,
                ensure_ascii=False,
            ),
            log_fp,
        )
        log(f"Resume: {args.resume}, start_page: {start_page}", log_fp)
        log(f"Existing unique reportIds in CSV: {len(seen_ids)}", log_fp)
        log(
            f"Captcha mode: interactive={args.interactive_captcha}, "
            f"captcha_every={args.captcha_every}, prompts_used={manual_captcha_count}, "
            f"auto_open_browser={args.auto_open_browser}, alert_sound={args.alert_sound}, "
            f"captcha_reminder_seconds={args.captcha_reminder_seconds}",
            log_fp,
        )

        checkpoint = {
            "query": query,
            "next_page": start_page,
            "expected_count": expected_count,
            "expected_pages": expected_pages,
            "fetched_pages": fetched_pages,
            "total_rows": total_rows,
            "new_rows": new_rows,
            "duplicate_rows": duplicate_rows,
            "failed_pages": failed_pages,
            "requests_since_captcha": requests_since_captcha,
            "manual_captcha_count": manual_captcha_count,
            "created_at": checkpoint.get("created_at", run_started_at),
            "run_started_at": run_started_at,
        }
        save_checkpoint(checkpoint_path, checkpoint)

        prefetched_page_1: Optional[PageResult] = None
        if expected_pages <= 0:
            estimate_payload = build_payload(
                start=args.start,
                end=args.end,
                province=args.province,
                city=args.city,
                district=args.district,
                pointname=args.pointname,
                state=args.state,
                page=1,
                page_size=args.page_size,
                sort_by=args.sort_by,
                order_by=args.order_by,
            )
            while True:
                estimate_result = fetch_page_with_retry(
                    payload=estimate_payload,
                    timeout=args.timeout,
                    max_retries=args.max_retries,
                    blocked_retry_limit=args.blocked_retry_limit,
                )
                requests_since_captcha += 1
                checkpoint["requests_since_captcha"] = requests_since_captcha
                save_checkpoint(checkpoint_path, checkpoint)
                if estimate_result.ok:
                    prefetched_page_1 = estimate_result
                    expected_count = estimate_result.total_count
                    expected_pages = (
                        math.ceil(expected_count / args.page_size) if expected_count else 0
                    )
                    checkpoint["expected_count"] = expected_count
                    checkpoint["expected_pages"] = expected_pages
                    checkpoint["requests_since_captcha"] = requests_since_captcha
                    save_checkpoint(checkpoint_path, checkpoint)
                    break

                failure = {
                    "page": 1,
                    "attempts": estimate_result.attempts,
                    "status_code": estimate_result.status_code,
                    "api_code": estimate_result.api_code,
                    "error": f"estimate_failed: {estimate_result.error}",
                    "blocked": estimate_result.blocked,
                    "time": now_utc_iso(),
                }
                failed_pages.append(failure)
                checkpoint["failed_pages"] = failed_pages
                save_checkpoint(checkpoint_path, checkpoint)
                log(
                    f"Estimate request failed after {estimate_result.attempts} attempts: {estimate_result.error}",
                    log_fp,
                )
                if estimate_result.blocked and args.interactive_captcha:
                    if manual_captcha_count >= args.max_captcha_prompts:
                        log(
                            "Blocked during estimate and max-captcha-prompts reached. Stop.",
                            log_fp,
                        )
                        return 2
                    ok = prompt_manual_captcha(
                        query=query,
                        page=1,
                        log_fp=log_fp,
                        reason=f"estimate blocked ({estimate_result.error})",
                        auto_open_browser=args.auto_open_browser,
                        alert_sound=args.alert_sound,
                        reminder_seconds=args.captcha_reminder_seconds,
                        signal_path=captcha_signal_path,
                        auto_solve=args.auto_captcha,
                        auto_solve_attempts=args.auto_captcha_attempts,
                        captcha_reader=args.captcha_reader,
                        captcha_agent_wait=args.captcha_agent_wait,
                        captcha_pending_dir=base_dir,
                    )
                    if not ok:
                        return 2
                    manual_captcha_count += 1
                    requests_since_captcha = 0
                    checkpoint["manual_captcha_count"] = manual_captcha_count
                    checkpoint["requests_since_captcha"] = requests_since_captcha
                    save_checkpoint(checkpoint_path, checkpoint)
                    log(
                        f"Manual captcha confirmed after estimate block. prompts_used={manual_captcha_count}",
                        log_fp,
                    )
                    continue
                if estimate_result.blocked and args.stop_on_blocked:
                    return 2
                return 1

        remaining_pages = (
            max(0, expected_pages - start_page + 1) if expected_pages > 0 else 0
        )
        estimate_seconds = remaining_pages * EST_SECONDS_PER_PAGE
        estimate_captchas = (
            math.ceil(remaining_pages / EST_PAGES_PER_CAPTCHA) if remaining_pages > 0 else 0
        )
        log(
            f"Estimate: total_count={expected_count}, total_pages={expected_pages}, "
            f"remaining_pages={remaining_pages}, estimated_active_time={format_duration(estimate_seconds)}, "
            f"estimated_captcha_inputs={estimate_captchas}",
            log_fp,
        )

        csv_fp = csv_path.open("a", encoding="utf-8", newline="")
        raw_fp = jsonl_path.open("a", encoding="utf-8")
        writer = csv.DictWriter(csv_fp, fieldnames=CSV_HEADERS)

        try:
            page = start_page
            while True:
                if args.max_pages > 0 and page > args.max_pages:
                    log("Reached max-pages limit, stopping early.", log_fp)
                    break
                if expected_pages > 0 and page > expected_pages:
                    break

                if (
                    args.interactive_captcha
                    and args.captcha_every > 0
                    and requests_since_captcha >= args.captcha_every
                ):
                    checkpoint["next_page"] = page
                    checkpoint["requests_since_captcha"] = requests_since_captcha
                    checkpoint["manual_captcha_count"] = manual_captcha_count
                    save_checkpoint(checkpoint_path, checkpoint)
                    if manual_captcha_count >= args.max_captcha_prompts:
                        log(
                            "Reached max-captcha-prompts before proactive captcha pause. Stop for manual decision.",
                            log_fp,
                        )
                        return 2
                    ok = prompt_manual_captcha(
                        query=query,
                        page=page,
                        log_fp=log_fp,
                        reason=(
                            f"requests_since_captcha={requests_since_captcha} "
                            f"reached captcha_every={args.captcha_every}"
                        ),
                        auto_open_browser=args.auto_open_browser,
                        alert_sound=args.alert_sound,
                        reminder_seconds=args.captcha_reminder_seconds,
                        signal_path=captcha_signal_path,
                        auto_solve=args.auto_captcha,
                        auto_solve_attempts=args.auto_captcha_attempts,
                        captcha_reader=args.captcha_reader,
                        captcha_agent_wait=args.captcha_agent_wait,
                        captcha_pending_dir=base_dir,
                    )
                    if not ok:
                        checkpoint["next_page"] = page
                        save_checkpoint(checkpoint_path, checkpoint)
                        return 2
                    manual_captcha_count += 1
                    requests_since_captcha = 0
                    checkpoint["next_page"] = page
                    checkpoint["manual_captcha_count"] = manual_captcha_count
                    checkpoint["requests_since_captcha"] = requests_since_captcha
                    save_checkpoint(checkpoint_path, checkpoint)
                    log(
                        f"Manual captcha confirmed. Resume from page {page}. prompts_used={manual_captcha_count}",
                        log_fp,
                    )

                payload = build_payload(
                    start=args.start,
                    end=args.end,
                    province=args.province,
                    city=args.city,
                    district=args.district,
                    pointname=args.pointname,
                    state=args.state,
                    page=page,
                    page_size=args.page_size,
                    sort_by=args.sort_by,
                    order_by=args.order_by,
                )
                if prefetched_page_1 is not None and page == 1:
                    result = prefetched_page_1
                    prefetched_page_1 = None
                    checkpoint["next_page"] = page
                    checkpoint["requests_since_captcha"] = requests_since_captcha
                    checkpoint["manual_captcha_count"] = manual_captcha_count
                    save_checkpoint(checkpoint_path, checkpoint)
                else:
                    result = fetch_page_with_retry(
                        payload=payload,
                        timeout=args.timeout,
                        max_retries=args.max_retries,
                        blocked_retry_limit=args.blocked_retry_limit,
                    )
                    requests_since_captcha += 1
                    checkpoint["next_page"] = page
                    checkpoint["requests_since_captcha"] = requests_since_captcha
                    checkpoint["manual_captcha_count"] = manual_captcha_count
                    save_checkpoint(checkpoint_path, checkpoint)
                if not result.ok:
                    failure = {
                        "page": page,
                        "attempts": result.attempts,
                        "status_code": result.status_code,
                        "api_code": result.api_code,
                        "error": result.error,
                        "blocked": result.blocked,
                        "time": now_utc_iso(),
                    }
                    failed_pages.append(failure)
                    checkpoint["failed_pages"] = failed_pages
                    checkpoint["next_page"] = page
                    checkpoint["requests_since_captcha"] = requests_since_captcha
                    checkpoint["manual_captcha_count"] = manual_captcha_count
                    save_checkpoint(checkpoint_path, checkpoint)
                    log(
                        f"Page {page} failed after {result.attempts} attempts: {result.error}",
                        log_fp,
                    )
                    if result.blocked and args.interactive_captcha:
                        if manual_captcha_count >= args.max_captcha_prompts:
                            log(
                                "Blocked response received but max-captcha-prompts reached. Stop for manual decision.",
                                log_fp,
                            )
                            return 2
                        ok = prompt_manual_captcha(
                            query=query,
                            page=page,
                            log_fp=log_fp,
                            reason=f"blocked response ({result.error})",
                            auto_open_browser=args.auto_open_browser,
                            alert_sound=args.alert_sound,
                            reminder_seconds=args.captcha_reminder_seconds,
                            signal_path=captcha_signal_path,
                            auto_solve=args.auto_captcha,
                            auto_solve_attempts=args.auto_captcha_attempts,
                            captcha_reader=args.captcha_reader,
                            captcha_agent_wait=args.captcha_agent_wait,
                            captcha_pending_dir=base_dir,
                        )
                        if not ok:
                            checkpoint["next_page"] = page
                            checkpoint["requests_since_captcha"] = requests_since_captcha
                            checkpoint["manual_captcha_count"] = manual_captcha_count
                            save_checkpoint(checkpoint_path, checkpoint)
                            return 2
                        manual_captcha_count += 1
                        requests_since_captcha = 0
                        checkpoint["next_page"] = page
                        checkpoint["requests_since_captcha"] = requests_since_captcha
                        checkpoint["manual_captcha_count"] = manual_captcha_count
                        save_checkpoint(checkpoint_path, checkpoint)
                        log(
                            f"Manual captcha confirmed after blocked response. Retry page {page}. prompts_used={manual_captcha_count}",
                            log_fp,
                        )
                        continue
                    if result.blocked and args.stop_on_blocked:
                        log(
                            "Stopping because blocked responses were detected repeatedly.",
                            log_fp,
                        )
                        return 2
                    return 1

                if expected_count == 0:
                    expected_count = result.total_count
                    expected_pages = math.ceil(expected_count / args.page_size) if expected_count else 0
                    checkpoint["expected_count"] = expected_count
                    checkpoint["expected_pages"] = expected_pages
                    log(
                        f"Total count={expected_count}, expected_pages={expected_pages}",
                        log_fp,
                    )

                rows = result.rows or []
                if not rows and expected_pages and page <= expected_pages:
                    failure = {
                        "page": page,
                        "attempts": result.attempts,
                        "status_code": result.status_code,
                        "api_code": result.api_code,
                        "error": "empty_rows_before_expected_end",
                        "blocked": False,
                        "time": now_utc_iso(),
                    }
                    failed_pages.append(failure)
                    checkpoint["failed_pages"] = failed_pages
                    checkpoint["next_page"] = page
                    save_checkpoint(checkpoint_path, checkpoint)
                    log(
                        f"Page {page} returned empty rows before expected end, stopping to avoid silent data loss.",
                        log_fp,
                    )
                    return 1

                fetched_at = now_utc_iso()
                page_new = 0
                page_dup = 0
                for row in rows:
                    rid = str(row.get("reportId") or "").strip()
                    if not rid:
                        continue
                    total_rows += 1
                    if rid in seen_ids:
                        duplicate_rows += 1
                        page_dup += 1
                        continue

                    seen_ids.add(rid)
                    new_rows += 1
                    page_new += 1

                    normalized = normalize_row(
                        row,
                        query=query,
                        page=page,
                        fetched_at=fetched_at,
                    )
                    writer.writerow(normalized)

                    raw_record = {
                        "fetched_at": fetched_at,
                        "fetched_page": page,
                        "query": query,
                        "data": row,
                    }
                    raw_fp.write(json.dumps(raw_record, ensure_ascii=False) + "\n")

                csv_fp.flush()
                raw_fp.flush()

                fetched_pages += 1
                checkpoint["next_page"] = page + 1
                checkpoint["fetched_pages"] = fetched_pages
                checkpoint["total_rows"] = total_rows
                checkpoint["new_rows"] = new_rows
                checkpoint["duplicate_rows"] = duplicate_rows
                checkpoint["failed_pages"] = failed_pages
                checkpoint["requests_since_captcha"] = requests_since_captcha
                checkpoint["manual_captcha_count"] = manual_captcha_count
                save_checkpoint(checkpoint_path, checkpoint)

                log(
                    "Page "
                    f"{page}/{expected_pages or '?'} done: rows={len(rows)}, "
                    f"new={page_new}, dup={page_dup}, unique_total={len(seen_ids)}, "
                    f"requests_since_captcha={requests_since_captcha}",
                    log_fp,
                )

                page += 1
                if expected_pages and page > expected_pages:
                    break

                if fetched_pages % args.batch_pages == 0:
                    cooldown = random.uniform(args.batch_cooldown_min, args.batch_cooldown_max)
                    log(f"Batch cooldown: {cooldown:.2f}s", log_fp)
                    time.sleep(cooldown)
                else:
                    sleep_s = random.uniform(args.min_sleep, args.max_sleep)
                    time.sleep(sleep_s)
        finally:
            csv_fp.close()
            raw_fp.close()

        report_num_payload = build_payload(
            start=args.start,
            end=args.end,
            province=args.province,
            city=args.city,
            district=args.district,
            pointname=args.pointname,
            state=args.state,
            page=1,
            page_size=args.page_size,
            sort_by=args.sort_by,
            order_by=args.order_by,
        )

        report_num = {}
        try:
            report_num = fetch_report_num(payload=report_num_payload, timeout=args.timeout)
            log(f"reportNum response: {report_num}", log_fp)
        except Exception as exc:
            log(f"reportNum fetch failed: {exc}", log_fp)

        summary = {
            "status": "completed",
            "query": query,
            "run_started_at": run_started_at,
            "run_finished_at": now_utc_iso(),
            "expected_count_from_search": expected_count,
            "expected_pages_from_search": expected_pages,
            "fetched_pages": fetched_pages,
            "total_rows_seen_in_pages": total_rows,
            "new_rows_written": new_rows,
            "duplicate_rows_skipped": duplicate_rows,
            "unique_report_ids_in_csv": len(seen_ids),
            "failed_pages": failed_pages,
            "manual_captcha_prompts_used": manual_captcha_count,
            "requests_since_last_captcha": requests_since_captcha,
            "report_num_endpoint": report_num,
            "paths": {
                "csv": str(csv_path),
                "jsonl": str(jsonl_path),
                "processed_csv": str(processed_path),
                "checkpoint": str(checkpoint_path),
                "log": str(log_path),
            },
        }
        if expected_count and len(seen_ids) < expected_count:
            summary["status"] = "completed_with_gap"
            summary["gap_vs_search_count"] = expected_count - len(seen_ids)
            log(
                "WARNING: unique_report_ids_in_csv is lower than expected_count_from_search.",
                log_fp,
            )

        atomic_write_json(summary_path, summary)
        log(f"Summary written to: {summary_path}", log_fp)
        if args.post_process:
            post_ok = run_post_process(
                project_dir=script_dir,
                input_csv=csv_path,
                output_csv=processed_path,
                place_name=place_name,
                log_fp=log_fp,
            )
            if not post_ok:
                return 1
        should_cleanup_runtime = (
            args.cleanup_runtime_artifacts and summary.get("status") == "completed"
        )
        log("Done.", log_fp)

    if should_cleanup_runtime:
        cleanup_runtime_artifacts(
            checkpoint_path=checkpoint_path,
            summary_path=summary_path,
            log_path=log_path,
            logs_dir=logs_dir,
        )
        print("Runtime artifacts cleaned: checkpoint/summary/log removed.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
