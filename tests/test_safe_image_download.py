#!/usr/bin/env python3
"""回归：失败下载不得覆盖已有有效本地图片。"""

import subprocess
import sys
import tempfile
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from threading import Thread
from unittest import mock

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TOOLS = PROJECT_ROOT / "tools"
sys.path.insert(0, str(TOOLS))

import safe_image_download


JPEG_BYTES = (
    b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    b"\xff\xdb\x00C\x00" + (b"\x08" * 64)
    + b"\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00"
    b"\xff\xc4\x00\x14\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00"
    b"\x00\x00\x00\x00\x00\x00\x00\x00\x00\xff\xda\x00\x08\x01\x01\x00\x00"
    b"\x3f\x00\x7f\xff\xd9"
)


class _Handler(BaseHTTPRequestHandler):
    mode = "ok"

    def log_message(self, format, *args):  # noqa: A003
        return

    def do_GET(self):  # noqa: N802
        if self.mode == "ok":
            body = JPEG_BYTES
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.mode == "empty404":
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        body = b"<html>" + (b"x" * 2048) + b"</html>"
        self.send_response(404)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def _serve(mode: str):
    _Handler.mode = mode
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    return server, f"http://{host}:{port}/img.jpg"


class SafeImageDownloadTests(unittest.TestCase):
    def test_skips_existing_valid_image(self):
        server, url = _serve("html404")
        try:
            with tempfile.TemporaryDirectory() as tmp:
                dest = Path(tmp) / "bird_1.jpg"
                dest.write_bytes(JPEG_BYTES)
                before = dest.read_bytes()
                # 真实 file(1) 可能不认极简 JPEG；强制视为有效以验证跳过路径
                with mock.patch.object(
                    safe_image_download,
                    "is_valid_image",
                    return_value=True,
                ):
                    status = safe_image_download.download_image_safely(url, dest)
                self.assertEqual(status, "skipped")
                self.assertEqual(dest.read_bytes(), before)
        finally:
            server.shutdown()

    def test_failed_download_does_not_clobber_when_forced_redownload(self):
        """即使跳过逻辑未命中，失败也只能动 .part，不得毁掉 dest。"""
        server, url = _serve("empty404")
        try:
            with tempfile.TemporaryDirectory() as tmp:
                dest = Path(tmp) / "bird_1.jpg"
                dest.write_bytes(JPEG_BYTES)
                before = dest.read_bytes()
                with mock.patch.object(
                    safe_image_download,
                    "is_valid_image",
                    return_value=False,
                ):
                    status = safe_image_download.download_image_safely(url, dest)
                self.assertEqual(status, "failed")
                self.assertEqual(dest.read_bytes(), before)
                self.assertFalse(dest.with_name(dest.name + ".part").exists())
        finally:
            server.shutdown()

    def test_http_error_without_existing_leaves_no_corrupt_file(self):
        server, url = _serve("html404")
        try:
            with tempfile.TemporaryDirectory() as tmp:
                dest = Path(tmp) / "bird_1.jpg"
                status = safe_image_download.download_image_safely(url, dest)
                self.assertEqual(status, "failed")
                self.assertFalse(dest.exists())
                self.assertFalse(dest.with_name(dest.name + ".part").exists())
        finally:
            server.shutdown()

    def test_successful_download_writes_image(self):
        server, url = _serve("ok")
        try:
            with tempfile.TemporaryDirectory() as tmp:
                dest = Path(tmp) / "bird_1.jpg"

                def valid_after_part(path: Path) -> bool:
                    path = Path(path)
                    if path.name.endswith(".part"):
                        return path.is_file() and path.stat().st_size > 0
                    return False

                with mock.patch.object(
                    safe_image_download,
                    "is_valid_image",
                    side_effect=valid_after_part,
                ):
                    status = safe_image_download.download_image_safely(url, dest)
                self.assertEqual(status, "downloaded")
                self.assertTrue(dest.exists())
                self.assertGreater(dest.stat().st_size, 0)
                self.assertFalse(dest.with_name(dest.name + ".part").exists())
        finally:
            server.shutdown()

    def test_plain_curl_overwrite_regression_baseline(self):
        """记录旧行为：curl -o 在 HTTP 错误时仍可能清空已有文件。"""
        server, url = _serve("empty404")
        try:
            with tempfile.TemporaryDirectory() as tmp:
                dest = Path(tmp) / "bird_1.jpg"
                dest.write_bytes(JPEG_BYTES)
                subprocess.run(
                    ["curl", "-s", "-o", str(dest), url],
                    check=False,
                    capture_output=True,
                )
                self.assertEqual(dest.stat().st_size, 0)
        finally:
            server.shutdown()


if __name__ == "__main__":
    unittest.main()
