#!/usr/bin/env python3
"""Auto-solve BirdReport rate-limit captcha (4-char kaptcha).

Readers:
  - ocr: ddddocr only
  - agent: save image and wait for captcha_answer.txt (AI/agent looks at the image)
  - ocr_then_agent: try OCR first, then fall back to agent vision file protocol
"""

from __future__ import annotations

import io
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, TextIO

import requests

CAPTCHA_GENERATE_URL = "https://api.birdreport.cn/front/code/visited/generate"
CAPTCHA_VERIFY_URL = "https://api.birdreport.cn/front/code/visited/verify"
DEFAULT_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

DEFAULT_PENDING_DIR = Path(__file__).resolve().parent
PENDING_IMAGE_NAME = "captcha_pending.jpg"
PENDING_PREVIEW_NAME = "captcha_pending_red.jpg"
PENDING_META_NAME = "captcha_pending.json"
ANSWER_NAME = "captcha_answer.txt"


@dataclass
class CaptchaSolveResult:
    ok: bool
    code: str = ""
    attempts: int = 0
    message: str = ""
    method: str = ""


_OCR: Any = None


def _log(message: str, log_fp: Optional[TextIO] = None) -> None:
    line = f"[auto_captcha] {message}"
    print(line, flush=True)
    if log_fp is not None:
        log_fp.write(line + "\n")
        log_fp.flush()


def get_ocr() -> Any:
    global _OCR
    if _OCR is None:
        import ddddocr

        _OCR = ddddocr.DdddOcr(show_ad=False)
    return _OCR


def preprocess_red_digits(image_bytes: bytes) -> bytes:
    """Keep reddish digit pixels; drop the black strike-through line."""
    import numpy as np
    from PIL import Image

    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    arr = np.array(img)
    r, g, b = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2]
    mask = (r > 120) & (r > g + 20) & (r > b + 20)
    out = np.full_like(arr, 255)
    out[mask] = arr[mask]
    buf = io.BytesIO()
    Image.fromarray(out).save(buf, format="JPEG", quality=95)
    return buf.getvalue()


def ocr_captcha(image_bytes: bytes) -> str:
    ocr = get_ocr()
    candidates = []
    for _label, data in (
        ("red", preprocess_red_digits(image_bytes)),
        ("raw", image_bytes),
    ):
        try:
            text = (ocr.classification(data) or "").strip()
        except Exception:
            continue
        text = "".join(ch for ch in text if ch.isalnum())
        if not text:
            continue
        candidates.append(text)
        if len(text) == 4:
            return text
    for text in candidates:
        if len(text) == 5:
            if text[0] in "418":
                return text[1:]
            if text[-1] in "418":
                return text[:-1]
        if len(text) > 4:
            return text[:4]
    return candidates[0] if candidates else ""


def normalize_code(raw: str) -> str:
    text = "".join(ch for ch in (raw or "").strip() if ch.isalnum())
    return text[:4] if len(text) >= 4 else text


def new_captcha_session() -> requests.Session:
    session = requests.Session()
    session.verify = False
    session.headers.update(
        {
            "User-Agent": DEFAULT_UA,
            "Origin": "https://www.birdreport.cn",
            "Referer": "https://www.birdreport.cn/home/code/verify.html",
        }
    )
    return session


def fetch_captcha_image(
    session: requests.Session,
    *,
    timeout: int = 20,
) -> bytes:
    ts = str(int(time.time() * 1000))
    response = session.get(
        CAPTCHA_GENERATE_URL,
        params={"timestamp": ts},
        headers={"Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8"},
        timeout=timeout,
    )
    response.raise_for_status()
    content = response.content or b""
    content_type = (response.headers.get("Content-Type") or "").lower()
    if len(content) < 200 or "image" not in content_type:
        raise RuntimeError(
            f"empty/invalid captcha image: status={response.status_code}, "
            f"type={content_type}, len={len(content)}"
        )
    return content


def submit_captcha_code(
    session: requests.Session,
    code: str,
    *,
    timeout: int = 20,
) -> dict:
    response = session.post(
        CAPTCHA_VERIFY_URL,
        headers={
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Content-Type": "application/json;charset=UTF-8",
        },
        json={"code": code},
        timeout=timeout,
    )
    response.raise_for_status()
    body = response.json()
    if not isinstance(body, dict):
        raise RuntimeError(f"unexpected verify response: {body!r}")
    return body


def pending_paths(pending_dir: Path) -> dict:
    root = pending_dir.resolve()
    return {
        "dir": root,
        "image": root / PENDING_IMAGE_NAME,
        "preview": root / PENDING_PREVIEW_NAME,
        "meta": root / PENDING_META_NAME,
        "answer": root / ANSWER_NAME,
    }


def clear_pending(paths: dict) -> None:
    for key in ("image", "preview", "meta", "answer"):
        path: Path = paths[key]
        if path.exists():
            try:
                path.unlink()
            except FileNotFoundError:
                pass


def publish_pending_image(
    image_bytes: bytes,
    pending_dir: Path,
    *,
    attempt: int,
) -> dict:
    paths = pending_paths(pending_dir)
    paths["dir"].mkdir(parents=True, exist_ok=True)
    if paths["answer"].exists():
        paths["answer"].unlink()
    paths["image"].write_bytes(image_bytes)
    try:
        paths["preview"].write_bytes(preprocess_red_digits(image_bytes))
    except Exception:
        paths["preview"].write_bytes(image_bytes)
    meta = {
        "attempt": attempt,
        "created_at": time.time(),
        "image": str(paths["image"]),
        "preview": str(paths["preview"]),
        "answer": str(paths["answer"]),
        "instruction": (
            "Read captcha_pending.jpg (or captcha_pending_red.jpg), then write "
            "exactly 4 alphanumeric chars into captcha_answer.txt"
        ),
    }
    paths["meta"].write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return paths


def wait_for_agent_answer(
    paths: dict,
    *,
    timeout_seconds: float,
    log_fp: Optional[TextIO] = None,
    poll_seconds: float = 1.0,
) -> str:
    answer_path: Path = paths["answer"]
    image_path: Path = paths["image"]
    deadline = time.time() + timeout_seconds
    _log(
        "Waiting for agent vision answer. "
        f"Look at {image_path} then write 4 chars to {answer_path}",
        log_fp,
    )
    while time.time() < deadline:
        if answer_path.exists():
            raw = answer_path.read_text(encoding="utf-8", errors="ignore")
            code = normalize_code(raw)
            try:
                answer_path.unlink()
            except FileNotFoundError:
                pass
            if len(code) == 4:
                return code
            _log(f"Ignoring invalid agent answer {raw!r}", log_fp)
        time.sleep(poll_seconds)
    return ""


def solve_visited_captcha(
    *,
    max_attempts: int = 8,
    timeout: int = 20,
    log_fp: Optional[TextIO] = None,
    session: Optional[requests.Session] = None,
    reader: str = "ocr_then_agent",
    pending_dir: Optional[Path] = None,
    agent_wait_seconds: float = 180.0,
) -> CaptchaSolveResult:
    """Fetch image → OCR and/or agent vision → verify."""
    if reader not in {"ocr", "agent", "ocr_then_agent"}:
        raise ValueError(f"unsupported reader: {reader}")

    owns_session = session is None
    sess = session or new_captcha_session()
    pending_root = (pending_dir or DEFAULT_PENDING_DIR).resolve()
    last_message = ""
    try:
        for attempt in range(1, max_attempts + 1):
            try:
                image = fetch_captcha_image(sess, timeout=timeout)
            except Exception as exc:
                last_message = f"fetch failed: {exc}"
                _log(f"attempt {attempt}/{max_attempts}: {last_message}", log_fp)
                time.sleep(1.0)
                continue

            paths = publish_pending_image(image, pending_root, attempt=attempt)

            methods: list[tuple[str, str]] = []
            if reader in {"ocr", "ocr_then_agent"}:
                ocr_code = normalize_code(ocr_captcha(image))
                if len(ocr_code) == 4:
                    methods.append(("ocr", ocr_code))
                else:
                    _log(
                        f"attempt {attempt}/{max_attempts}: ocr rejected '{ocr_code}'",
                        log_fp,
                    )

            need_agent = reader == "agent" or (
                reader == "ocr_then_agent" and not methods
            )
            # Also used after OCR verify failure below.
            while True:
                if need_agent:
                    agent_code = wait_for_agent_answer(
                        paths,
                        timeout_seconds=agent_wait_seconds,
                        log_fp=log_fp,
                    )
                    if len(agent_code) == 4:
                        methods.append(("agent", agent_code))
                    else:
                        last_message = "agent answer timeout/invalid"
                        _log(
                            f"attempt {attempt}/{max_attempts}: {last_message}",
                            log_fp,
                        )
                        break

                if not methods:
                    last_message = "no candidate code"
                    break

                method, code = methods.pop(0)
                try:
                    body = submit_captcha_code(sess, code, timeout=timeout)
                except Exception as exc:
                    last_message = f"verify request failed: {exc}"
                    _log(
                        f"attempt {attempt}/{max_attempts}: method={method} {last_message}",
                        log_fp,
                    )
                    if method == "ocr" and reader == "ocr_then_agent":
                        need_agent = True
                        continue
                    break

                success = bool(body.get("success"))
                msg = str(body.get("msg") or "")
                last_message = msg or ("ok" if success else "verify failed")
                _log(
                    f"attempt {attempt}/{max_attempts}: method={method} "
                    f"code={code} success={success} msg={msg}",
                    log_fp,
                )
                if success:
                    clear_pending(paths)
                    return CaptchaSolveResult(
                        ok=True,
                        code=code,
                        attempts=attempt,
                        message=msg or "ok",
                        method=method,
                    )
                if method == "ocr" and reader == "ocr_then_agent":
                    need_agent = True
                    continue
                break

            time.sleep(0.4)

        clear_pending(pending_paths(pending_root))
        return CaptchaSolveResult(
            ok=False,
            attempts=max_attempts,
            message=last_message or "max attempts exceeded",
        )
    finally:
        if owns_session:
            sess.close()
